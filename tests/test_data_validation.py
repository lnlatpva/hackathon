"""Негативные проверки пользовательского ввода: сервер не доверяет HTML-формам."""
from copy import deepcopy

import pytest


SRC = {'kind': 'synthetic_test_fixture', 'reference': 'fixture:validation', 'confirmed': True}


def amount(value, unit='s', source=None):
    return {'value': str(value), 'unit': unit, 'source': source or SRC}


@pytest.mark.parametrize('name', [' ', '  \t  ', '\n'])
def test_model_name_cannot_be_only_whitespace(client, admin, name):
    response = client.post('/api/models', headers=admin, json={'name': name})
    assert response.status_code == 422


def test_model_name_is_trimmed(client, admin):
    response = client.post('/api/models', headers=admin, json={'name': '  Модель A  '})
    assert response.status_code == 201, response.text
    assert response.json()['name'] == 'Модель A'


def test_invalid_user_login_rejected(client, admin):
    for login in ['  ', 'a b c', 'a@b', 'a/b']:
        response = client.post('/api/users', headers=admin, json={
            'login': login, 'password': 'LongPassword123!', 'role': 'observer'})
        assert response.status_code == 422, (login, response.text)


def test_model_rejects_missing_source_reference(client, admin, example):
    graph = deepcopy(example)
    graph['nodes'][0]['processing_seconds']['source']['reference'] = '   '
    response = client.post('/api/models', headers=admin, json={'name': 'Test', 'graph': graph})
    assert response.status_code == 422


def test_wrong_time_unit_rejected(client, admin, example):
    graph = deepcopy(example)
    graph['nodes'][0]['processing_seconds']['unit'] = 'min'
    response = client.post('/api/models', headers=admin, json={'name': 'Test', 'graph': graph})
    assert response.status_code == 422


@pytest.mark.parametrize('facts', [
    {'available_seconds': amount(1200, 'min')},
    {'accepted': {'value': 6, 'source': SRC}, 'presented': {'value': 5, 'source': SRC}},
    {'busy_seconds': amount(1300), 'resource_available_seconds': amount(1200)},
    {'downtime_seconds': amount(300), 'scheduled_seconds': amount(200)},
    {'inventory_begin': amount(100, 'RUB'), 'inventory_end': amount(100, 'USD')},
    {'revenue': amount(500, 'USD'), 'total_cost': amount(200, 'RUB')},
])
def test_contradictory_facts_rejected_without_run(client, admin, published, facts):
    response = client.post(f'/api/models/{published}/calculate', headers=admin,
                           json={'facts': facts})
    assert response.status_code == 422, response.text
    assert client.get(f'/api/models/{published}/runs', headers=admin).json() == []


def test_zero_or_invalid_takt_rejected(client, admin, published):
    for datum in (amount(0), amount(15, 'min')):
        response = client.post(f'/api/models/{published}/calculate', headers=admin,
                               json={'takt_seconds': datum})
        assert response.status_code == 422, response.text


def test_scenario_name_and_reason_not_whitespace(client, admin, published):
    example = {'target_type': 'node', 'target_id': 'B', 'field': 'processing_seconds',
               'new_value': '20', 'reason': ' '} 
    response = client.post(f'/api/models/{published}/scenarios', headers=admin,
                           json={'name': 'Scenario', 'overrides': [example]})
    assert response.status_code == 422
    example['reason'] = 'Гипотетическое изменение'
    response = client.post(f'/api/models/{published}/scenarios', headers=admin,
                           json={'name': '   ', 'overrides': [example]})
    assert response.status_code == 422


def test_cost_unit_must_be_uppercase_currency(client, admin, example):
    response = client.post('/api/models', headers=admin, json={
        'name': 'Cost test', 'graph': example,
        'node_costs': {'A': amount('5', 'rub/output')}})
    assert response.status_code == 422


def test_valid_scenario_still_computes(client, admin, published):
    data = {'name': 'Validated scenario', 'overrides': [{
        'target_type': 'node', 'target_id': 'B', 'field': 'processing_seconds',
        'new_value': '15', 'reason': '  Тест корректного изменения  '} ]}
    response = client.post(f'/api/models/{published}/scenarios', headers=admin, json=data)
    assert response.status_code == 201, response.text
    assert response.json()['overrides'][0]['reason'] == 'Тест корректного изменения'
    run = client.post(f"/api/scenarios/{response.json()['id']}/calculate", headers=admin, json={})
    assert run.status_code == 201, run.text