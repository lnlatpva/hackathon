"""Четыре таблицы для MVP хакатона одной организации; PostgreSQL/SQLite."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


# В PostgreSQL сохраняем JSONB; стандартный JSON используется в SQLite-тестах.
Json = JSON().with_variant(JSONB(), 'postgresql')


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    login: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default='observer')


class ProductionModel(Base):
    __tablename__ = 'models'
    __table_args__ = (UniqueConstraint('family_id', 'version', name='uq_model_family_version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    state_type: Mapped[str] = mapped_column(String(20), nullable=False, default='current')
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Граф включает операции, связи, ресурсы и их назначения в пределах одной версии.
    graph: Mapped[dict] = mapped_column(Json, nullable=False)
    node_costs: Mapped[dict] = mapped_column(Json, nullable=False, default=dict)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Scenario(Base):
    __tablename__ = 'scenarios'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    model_id: Mapped[str] = mapped_column(ForeignKey('models.id', ondelete='RESTRICT'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    overrides: Mapped[list] = mapped_column(Json, nullable=False)
    cost_overrides: Mapped[dict] = mapped_column(Json, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Calculation(Base):
    __tablename__ = 'calculations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    model_id: Mapped[str] = mapped_column(ForeignKey('models.id', ondelete='RESTRICT'), nullable=False, index=True)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey('scenarios.id', ondelete='RESTRICT'), index=True)
    input_snapshot: Mapped[dict] = mapped_column(Json, nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(Json, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


def connect(url: str):
    opts = {'pool_pre_ping': True}
    if url.startswith('sqlite:'):
        opts['connect_args'] = {'check_same_thread': False}
        if ':memory:' in url:
            opts['poolclass'] = StaticPool
    engine = create_engine(url, **opts)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def fk_on(conn, _):
            conn.execute('PRAGMA foreign_keys=ON')
    return engine, sessionmaker(engine, expire_on_commit=False)