"""Небольшой бэкенд на FastAPI для одной организации (для направления «А» хакатона)."""

import hashlib
import json
import os
import re
import logging
from time import sleep
from typing import Annotated, Literal
from uuid import uuid4

import jwt
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, delete
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from udt_calc import Amount, Model, Override, Scenario as CoreScenario, apply_scenario, validate_graph
from udt_calc.scenarios import ScenarioError

from .calc import ALGORITHM_VERSION, CalculationRequest, calculate
from .db import Base, Calculation, ProductionModel, Scenario, User, connect
from .security import hash_password, token, user_id_from_token, verify_password

ROLE = Literal['administrator', 'technologist', 'manager', 'observer']
STATE = Literal['current', 'ideal', 'target']
bearer = HTTPBearer(auto_error=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SetupIn(Strict):
    login: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=12, max_length=256)

    @field_validator('login')
    @classmethod
    def validate_login(cls, value: str) -> str:

        # Имена пользователей нормализуем одинаково при создании и входе.
        normalized = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9_.-]{3,120}', normalized):
            raise ValueError('Логин: 3–120 символов, только латиница, цифры, _, . и -')
        return normalized

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Пароль не может состоять только из пробелов')
        return value


class UserIn(SetupIn):
    role: ROLE


class LoginIn(Strict):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)

    @field_validator('login')
    @classmethod
    def normalize_login(cls, value: str) -> str:
        return value.strip().lower()


class ModelIn(Strict):
    name: str = Field(min_length=1, max_length=220)
    state_type: STATE = 'current'
    graph: Model | None = None
    node_costs: dict[str, Amount] = Field(default_factory=dict)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value: str) -> str:

        # Pydantic min_length допускает строку из пробелов: это отдельная проверка.
        normalized = value.strip()
        if not normalized:
            raise ValueError('Название модели не может быть пустым')
        return normalized


class ModelUpdate(Strict):
    name: str = Field(min_length=1, max_length=220)
    state_type: STATE = 'current'
    graph: Model
    node_costs: dict[str, Amount] = Field(default_factory=dict)
    expected_revision: int = Field(ge=1)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('Название модели не может быть пустым')
        return normalized


class ModelDeleteConfirmation(Strict):
    confirm_name: str = Field(min_length=1, max_length=220)


class ScenarioIn(Strict):
    name: str = Field(min_length=1, max_length=220)
    overrides: list[Override] = Field(default_factory=list)
    cost_overrides: dict[str, Amount] = Field(default_factory=dict)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('Название сценария не может быть пустым')
        return normalized


def canonical_hash(snapshot: dict) -> str:
    raw = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def create_app(*, database_url: str | None = None, secret: str | None = None,
               allow_setup: bool | None = None) -> FastAPI:
    database_url = database_url or os.getenv('DATABASE_URL', 'sqlite:///./udt_demo.db')
    secret = secret or os.getenv('UDT_SECRET_KEY')
    if not secret or len(secret) < 32:
        raise RuntimeError('Set UDT_SECRET_KEY to a random secret of at least 32 characters')
    if allow_setup is None:
        allow_setup = os.getenv('UDT_ALLOW_SETUP', 'false').lower() == 'true'

    engine, session_factory = connect(database_url)

    # В MVP таблицы создаются при старте; полноценные миграции БД не предусмотрены.
    # При старте службы PostgreSQL соединение может быть ещё недоступно.
    # Повторяем только ошибки соединения, не скрывая ошибки схемы или валидации.
    for attempt in range(1, 13):
        try:
            Base.metadata.create_all(engine)
            break
        except OperationalError:
            if attempt == 12:
                raise
            logging.warning('Подключение к БД ещё не готово (%s/12); повтор через 2 с', attempt)
            sleep(2)
    app = FastAPI(title='UDT — Minimal API', version='0.9.3.2',
                  description='Production graph → analysis → what-if comparison. Direction A only.')
    origins = [origin.strip() for origin in os.getenv('UDT_CORS_ORIGINS', '').split(',') if origin.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins,
                           allow_credentials=False, allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
                           allow_headers=['Authorization', 'Content-Type'])
    app.state.engine = engine

    def db_session():
        with session_factory() as db:
            yield db

    DB = Annotated[Session, Depends(db_session)]

    def current_user(db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if credentials is None:
            raise HTTPException(401, 'Bearer token required')
        try:
            uid = user_id_from_token(credentials.credentials, secret)
        except (jwt.PyJWTError, ValueError, KeyError):
            raise HTTPException(401, 'Invalid or expired token')
        user = db.get(User, uid)
        if user is None:
            raise HTTPException(401, 'User not found')
        return user

    WHO = Annotated[User, Depends(current_user)]

    # Проверка прав выполняется на сервере, независимо от доступности кнопок в интерфейсе.
    def editor(user: WHO):
        if user.role not in {'administrator', 'technologist'}:
            raise HTTPException(403, 'Editing requires administrator or technologist')
        return user

    EDITOR = Annotated[User, Depends(editor)]

    def get_model(db: Session, mid: str) -> ProductionModel:
        row = db.get(ProductionModel, mid)
        if row is None:
            raise HTTPException(404, 'Model not found')
        return row

    def get_scenario(db: Session, sid: str) -> Scenario:
        row = db.get(Scenario, sid)
        if row is None:
            raise HTTPException(404, 'Scenario not found')
        return row

    def graph_of(row: ProductionModel) -> Model:
        return Model.model_validate(row.graph)

    def validate_costs(graph: Model, costs: dict[str, Amount]):
        allowed = {n.id for n in graph.nodes if n.kind in {'operation', 'inspection'}}
        for node_id, amount in costs.items():
            if node_id not in allowed:
                raise HTTPException(422, f'Unknown or unsupported cost node: {node_id}')
            if re.fullmatch(r'[A-Z]{3}/output', amount.unit) is None:
                raise HTTPException(422, 'Node costs must use an uppercase ISO-style currency/output, e.g. RUB/output')

    def model_out(row: ProductionModel) -> dict:
        return {'id': row.id, 'family_id': row.family_id, 'version': row.version,
                'name': row.name, 'status': row.status, 'state_type': row.state_type,
                'revision': row.revision, 'graph': row.graph, 'node_costs': row.node_costs}

    def scenario_out(row: Scenario) -> dict:
        return {'id': row.id, 'model_id': row.model_id, 'name': row.name,
                'overrides': row.overrides, 'cost_overrides': row.cost_overrides}

    def validate_scenario(db: Session, model: ProductionModel, overrides: list[Override], sid: str):
        
        # Проверяем существование целей изменений и запрещаем дубли одного параметра.
        try:
            apply_scenario(graph_of(model), CoreScenario(
                id=sid, base_model_id=model.id, overrides=tuple(overrides)))
        except (ScenarioError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    def save(db: Session):
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, 'Database constraint violation') from exc

    @app.get('/health')
    def health():
        return {'status': 'ok', 'version': '0.9.3.2'}

    @app.post('/api/auth/setup', status_code=201)
    def setup(body: SetupIn, db: DB):
        if not allow_setup:
            raise HTTPException(404, 'Setup is disabled')
        if db.scalar(select(func.count()).select_from(User)):
            raise HTTPException(409, 'Initial administrator already exists')
        user = User(login=body.login.strip().lower(), password_hash=hash_password(body.password), role='administrator')
        db.add(user)
        save(db)
        return {'access_token': token(user.id, secret), 'token_type': 'bearer'}

    @app.post('/api/auth/login')
    def login(body: LoginIn, db: DB):
        user = db.scalar(select(User).where(User.login == body.login.strip().lower()))
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, 'Invalid credentials')
        return {'access_token': token(user.id, secret), 'token_type': 'bearer'}

    @app.get('/api/auth/me')
    def me(user: WHO):
        return {'id': user.id, 'login': user.login, 'role': user.role}

    @app.post('/api/users', status_code=201)
    def add_user(body: UserIn, db: DB, user: WHO):
        if user.role != 'administrator':
            raise HTTPException(403, 'Only administrator can add users')
        created = User(login=body.login.strip().lower(), role=body.role,
                       password_hash=hash_password(body.password))
        db.add(created)
        save(db)
        return {'id': created.id, 'login': created.login, 'role': created.role}

    @app.get('/api/models')
    def list_models(db: DB, user: WHO):
        return [model_out(row) for row in db.scalars(select(ProductionModel).order_by(
            ProductionModel.created_at, ProductionModel.version)).all()]

    @app.post('/api/models', status_code=201)
    def create_model(body: ModelIn, db: DB, user: EDITOR):
        mid = str(uuid4())
        graph = (body.graph or Model(id=mid, nodes=(), edges=())).model_copy(update={'id': mid})
        validate_costs(graph, body.node_costs)
        row = ProductionModel(id=mid, family_id=mid, version=1, name=body.name.strip(),
                              state_type=body.state_type, graph=graph.model_dump(mode='json'),
                              node_costs={k:v.model_dump(mode='json') for k,v in body.node_costs.items()},
                              owner_id=user.id)
        db.add(row)
        save(db)
        return model_out(row)

    @app.get('/api/models/{model_id}')
    def read_model(model_id: str, db: DB, user: WHO):
        return model_out(get_model(db, model_id))

    @app.put('/api/models/{model_id}')
    def update_model(model_id: str, body: ModelUpdate, db: DB, user: EDITOR):
        row = get_model(db, model_id)
        if row.status != 'draft':
            raise HTTPException(409, 'Published models are immutable; create a new version')
        if row.revision != body.expected_revision:
            raise HTTPException(409, 'Model revision changed; reload before saving')
        new_graph = body.graph.model_copy(update={'id': row.id})
        validate_costs(new_graph, body.node_costs)
        row.name = body.name.strip()
        row.state_type = body.state_type
        row.graph = new_graph.model_dump(mode='json')
        row.node_costs = {k:v.model_dump(mode='json') for k,v in body.node_costs.items()}
        row.revision += 1
        save(db)
        return model_out(row)

    # Опубликованную версию нельзя редактировать: изменения вносятся в новый черновик.
    @app.post('/api/models/{model_id}/publish')
    def publish(model_id: str, db: DB, user: EDITOR):
        row = get_model(db, model_id)
        if row.status != 'draft':
            raise HTTPException(409, 'Model already published')
        result = validate_graph(graph_of(row))
        if not result.valid or not graph_of(row).nodes:
            raise HTTPException(422, {'message': 'Graph must be structurally valid',
                                      'issues': result.model_dump(mode='json')['issues']})
        row.status = 'published'
        save(db)
        return model_out(row)

    @app.delete('/api/models/{model_id}', status_code=204)
    def delete_model_family(model_id: str, body: ModelDeleteConfirmation, db: DB, user: WHO):
        """Permanently delete a model and ALL its versions, scenarios, and runs.

        There is intentionally no archive/soft-delete feature in this MVP.
        Only an administrator can perform this destructive operation.
        """
        if user.role != 'administrator':
            raise HTTPException(403, 'Only administrator can delete models')
        selected = get_model(db, model_id)
        if body.confirm_name != selected.name:
            raise HTTPException(422, 'Type the exact model name to confirm permanent deletion')
        ids = db.scalars(select(ProductionModel.id).where(
            ProductionModel.family_id == selected.family_id)).all()
        if not ids:
            raise HTTPException(404, 'Model family not found')
        
        # Удаляем расчёты, сценарии и версии в порядке внешних ключей одной транзакцией.
        db.execute(delete(Calculation).where(Calculation.model_id.in_(ids)))
        db.execute(delete(Scenario).where(Scenario.model_id.in_(ids)))
        db.execute(delete(ProductionModel).where(ProductionModel.id.in_(ids)))
        save(db)
        return Response(status_code=204)

    # Новая версия наследует данные исходной, но создаётся в статусе черновика.
    @app.post('/api/models/{model_id}/versions', status_code=201)
    def clone_version(model_id: str, db: DB, user: EDITOR):
        base = get_model(db, model_id)
        number = db.scalar(select(func.max(ProductionModel.version)).where(
            ProductionModel.family_id == base.family_id)) + 1
        vid = str(uuid4())
        new_graph = graph_of(base).model_copy(update={'id': vid})
        row = ProductionModel(id=vid, family_id=base.family_id, version=number,
            name=base.name, state_type=base.state_type, graph=new_graph.model_dump(mode='json'),
            node_costs=base.node_costs,
            owner_id=user.id, status='draft')
        db.add(row)
        save(db)
        return model_out(row)

    @app.get('/api/models/{model_id}/versions')
    def list_versions(model_id: str, db: DB, user: WHO):
        base = get_model(db, model_id)
        rows = db.scalars(select(ProductionModel).where(ProductionModel.family_id == base.family_id)
                          .order_by(ProductionModel.version)).all()
        return [model_out(row) for row in rows]

    @app.post('/api/models/{model_id}/scenarios', status_code=201)
    def create_scenario(model_id: str, body: ScenarioIn, db: DB, user: EDITOR):
        base = get_model(db, model_id)
        if base.status != 'published':
            raise HTTPException(409, 'Publish the base model before creating scenarios')
        sid = str(uuid4())
        validate_scenario(db, base, body.overrides, sid)
        validate_costs(graph_of(base), body.cost_overrides)
        row = Scenario(id=sid, model_id=model_id, name=body.name.strip(),
                       overrides=[o.model_dump(mode='json') for o in body.overrides],
                       cost_overrides={k:v.model_dump(mode='json') for k,v in body.cost_overrides.items()})
        db.add(row)
        save(db)
        return scenario_out(row)

    @app.get('/api/models/{model_id}/scenarios')
    def list_scenarios(model_id: str, db: DB, user: WHO):
        get_model(db, model_id)
        return [scenario_out(row) for row in db.scalars(select(Scenario).where(
            Scenario.model_id == model_id).order_by(Scenario.created_at)).all()]

    @app.get('/api/scenarios/{scenario_id}')
    def read_scenario(scenario_id: str, db: DB, user: WHO):
        return scenario_out(get_scenario(db, scenario_id))

    @app.put('/api/scenarios/{scenario_id}')
    def update_scenario(scenario_id: str, body: ScenarioIn, db: DB, user: EDITOR):
        row = get_scenario(db, scenario_id)
        base = get_model(db, row.model_id)
        validate_scenario(db, base, body.overrides, scenario_id)
        validate_costs(graph_of(base), body.cost_overrides)
        row.name = body.name.strip()
        row.overrides = [o.model_dump(mode='json') for o in body.overrides]
        row.cost_overrides = {k:v.model_dump(mode='json') for k,v in body.cost_overrides.items()}
        save(db)
        return scenario_out(row)

    def run(db: Session, row: ProductionModel, request: CalculationRequest, sid: str | None = None):
        graph = graph_of(row)
        check = validate_graph(graph)
        if not check.valid:
            raise HTTPException(422, {'message': 'Invalid production graph',
                                      'issues': check.model_dump(mode='json')['issues']})
        overrides = None
        cost_overrides = None
        if sid:
            scenario = get_scenario(db, sid)
            if scenario.model_id != row.id:
                raise HTTPException(422, 'Scenario does not belong to the selected version')
            overrides = [Override.model_validate(o) for o in scenario.overrides]
            cost_overrides = {k: Amount.model_validate(v) for k,v in scenario.cost_overrides.items()}
        try:
            result = calculate(graph, request, overrides, scenario_id=sid,
                               node_costs={k:Amount.model_validate(v) for k,v in row.node_costs.items()},
                               cost_overrides=cost_overrides)
        except (ValueError, ScenarioError) as exc:
            raise HTTPException(422, str(exc)) from exc
        
        # Сохраняем все входные данные и версию алгоритма для воспроизводимости расчёта.
        # При этом сценарий не изменяет исходную опубликованную модель.
        snapshot = {'graph': row.graph, 'node_costs': row.node_costs,
                    'cost_overrides': {k:v.model_dump(mode='json') for k,v in cost_overrides.items()} if cost_overrides is not None else None,
                    'request': request.model_dump(mode='json'),
                    'overrides': [o.model_dump(mode='json') for o in overrides] if overrides is not None else None,
                    'algorithm_version': ALGORITHM_VERSION}
        calculation = Calculation(model_id=row.id, scenario_id=sid, input_snapshot=snapshot,
                                 result_snapshot=result, input_hash=canonical_hash(snapshot))
        db.add(calculation)
        save(db)
        return run_out(calculation)

    def run_out(row: Calculation):
        return {'id': row.id, 'model_id': row.model_id, 'scenario_id': row.scenario_id,
                'created_at': row.created_at, 'input_hash': row.input_hash,
                'input_snapshot': row.input_snapshot, 'result': row.result_snapshot}

    @app.post('/api/models/{model_id}/calculate', status_code=201)
    def calculate_model(model_id: str, request: CalculationRequest, db: DB, user: WHO):
        if user.role == 'observer':
            raise HTTPException(403, 'Observer has read-only access')
        return run(db, get_model(db, model_id), request)

    @app.post('/api/scenarios/{scenario_id}/calculate', status_code=201)
    def calculate_scenario(scenario_id: str, request: CalculationRequest, db: DB, user: WHO):
        if user.role == 'observer':
            raise HTTPException(403, 'Observer has read-only access')
        row = get_scenario(db, scenario_id)
        return run(db, get_model(db, row.model_id), request, sid=scenario_id)

    @app.get('/api/models/{model_id}/runs')
    def list_runs(model_id: str, db: DB, user: WHO):
        get_model(db, model_id)
        return [run_out(r) for r in db.scalars(select(Calculation).where(
            Calculation.model_id == model_id).order_by(Calculation.created_at.desc())).all()]

    @app.get('/api/runs/{run_id}')
    def read_run(run_id: str, db: DB, user: WHO):
        row = db.get(Calculation, run_id)
        if row is None:
            raise HTTPException(404, 'Calculation not found')
        return run_out(row)

    return app