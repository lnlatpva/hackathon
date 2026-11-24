import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def postgresql_url():
    database_url = os.getenv('UDT_TEST_DATABASE_URL')
    if not database_url:
        pytest.skip('Set UDT_TEST_DATABASE_URL to run the PostgreSQL integration test')

    url = make_url(database_url)
    if url.drivername != 'postgresql+psycopg':
        pytest.fail('UDT_TEST_DATABASE_URL must use postgresql+psycopg')

    schema = f'udt_test_{uuid4().hex}'
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            scoped_url = url.update_query_dict({'options': f'-csearch_path={schema}'})
            yield scoped_url.render_as_string(hide_password=False)
        finally:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
    finally:
        engine.dispose()


@pytest.fixture
def client():
    app = create_app(database_url='sqlite:///:memory:', secret='a-long-random-test-secret-1234567890', allow_setup=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    res = client.post('/api/auth/setup', json={'login':'admin','password':'LongPassword123!'})
    assert res.status_code == 201, res.text
    return {'Authorization': 'Bearer ' + res.json()['access_token']}


@pytest.fixture
def example():
    return json.loads((ROOT / 'examples' / 'demo_graph.json').read_text())


@pytest.fixture
def published(client, admin, example):
    res = client.post('/api/models', json={'name':'Synthetic demo', 'graph':example}, headers=admin)
    assert res.status_code == 201, res.text
    mid = res.json()['id']
    assert client.post(f'/api/models/{mid}/publish', headers=admin).status_code == 200
    return mid


def credentials(client, admin, name, role):
    created = client.post('/api/users', json={'login':name,'password':'LongPassword123!','role':role}, headers=admin)
    assert created.status_code == 201, created.text
    login = client.post('/api/auth/login', json={'login':name,'password':'LongPassword123!'})
    assert login.status_code == 200
    return {'Authorization':'Bearer ' + login.json()['access_token']}