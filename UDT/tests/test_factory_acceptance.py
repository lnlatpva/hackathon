"""Контрольный расчёт «Фабрики процессов» по ТЗ UDT v0.9.3.2."""

import json
from decimal import Decimal
from pathlib import Path


def factory_control_case():
    source_file = Path(__file__).resolve().parents[1] / 'examples' / 'factory_confirmed.json'
    documentary = json.loads(source_file.read_text())
    shift = documentary['shift']
    assert shift['available_production_seconds'] is None
    assert documentary['operation_8']['normalized_cycle_seconds'] is None

    assumption = {
        'kind': 'normative',
        'reference': 'ТЗ UDT v0.9.3.2, контрольный расчёт демонстрационного процесса',
        'confirmed': False,
    }

    def seconds(value):
        return {'value': str(value), 'unit': 's', 'source': assumption}

    period = shift['duration_seconds']
    standard_8 = documentary['operation_8']['sum_of_raw_values']
    graph = {
        'id': 'factory-control-case',
        'target_id': 'WS8',
        'nodes': [
            {
                'id': station, 'name': name, 'kind': 'operation',
                'processing_seconds': seconds(cycle),
                'batch_size': 1, 'units_per_finished': '1', 'parallel_channels': 1,
                'available_seconds': seconds(period),
            }
            for station, name, cycle in (
                ('WS7', 'РМ7 · Сборка пульта управления', 102),
                ('WS8', 'РМ8 · Установка шести болтов', standard_8),
            )
        ],
        'edges': [{
            'id': 'ws7-to-ws8', 'source_id': 'WS7', 'target_id': 'WS8',
            'kind': 'material', 'verification': 'inferred', 'source': assumption,
        }],
        'resources': [{'id': 'OP8', 'name': 'Оператор РМ8', 'available_seconds': seconds(period)}],
        'resource_uses': [{'node_id': 'WS8', 'resource_id': 'OP8',
                           'work_seconds_per_output': seconds(standard_8)}],
    }
    demand = shift['target_finished_units']
    request = {
        'period_key': 'factory-round-1',
        'facts': {
            'available_seconds': seconds(period),
            'demand': {'value': demand, 'source': {
                'kind': 'document', 'reference': shift['source'], 'confirmed': True,
            }},
        },
    }
    scenario = {
        'name': 'РМ8 и оператор · 100 с',
        'overrides': [
            {'target_type': 'node', 'target_id': 'WS8', 'field': 'processing_seconds',
             'new_value': '100', 'reason': 'Сценарная гипотеза по ТЗ'},
            {'target_type': 'resource_use', 'target_id': 'WS8::OP8', 'field': 'work_seconds_per_output',
             'new_value': '100', 'reason': 'Сценарная гипотеза по ТЗ'},
        ],
    }
    return graph, request, scenario


def test_factory_control_case_matches_specification(client, admin):
    graph, request, scenario = factory_control_case()
    model = client.post('/api/models', json={'name': 'Контрольный расчёт Фабрики процессов',
                                            'graph': graph}, headers=admin)
    assert model.status_code == 201, model.text
    model_path = f"/api/models/{model.json()['id']}"
    published = client.post(f'{model_path}/publish', headers=admin)
    assert published.status_code == 200, published.text

    base = client.post(f'{model_path}/calculate', json=request, headers=admin)
    assert base.status_code == 201, base.text
    saved = client.post(f'{model_path}/scenarios', json=scenario, headers=admin)
    assert saved.status_code == 201, saved.text
    scenario_run = client.post(f"/api/scenarios/{saved.json()['id']}/calculate", json=request, headers=admin)
    assert scenario_run.status_code == 201, scenario_run.text
    base_result = base.json()['result']
    scenario_result = scenario_run.json()['result']

    for result in (base_result, scenario_result):
        metrics = result['metrics']
        assert Decimal(metrics['takt_seconds_per_finished']['value']) == Decimal('120')
        assert metrics['capacity_upper_bound']['status'] == 'estimated'
        for name in ('first_unit_lead_seconds', 'throughput_accepted_per_second',
                     'actual_utilization_percent', 'cost_per_accepted_unit'):
            assert metrics[name]['status'] == 'unavailable'
            assert metrics[name]['value'] is None

    base_capacity = Decimal(1200) / Decimal(171)
    scenario_capacity = Decimal(1200) / Decimal(102)
    tolerance = Decimal('0.000001')
    assert abs(Decimal(base_result['metrics']['capacity_upper_bound']['value']) - base_capacity) <= tolerance
    assert abs(Decimal(scenario_result['metrics']['capacity_upper_bound']['value']) - scenario_capacity) <= tolerance
    assert abs(Decimal(scenario_result['capacity_delta']) - (scenario_capacity - base_capacity)) <= tolerance

    base_bottlenecks = {(item['code'], item['owner_id']) for item in base_result['analysis']['bottlenecks']}
    scenario_bottlenecks = {(item['code'], item['owner_id']) for item in scenario_result['analysis']['bottlenecks']}
    assert {owner for code, owner in base_bottlenecks if code == 'BOT-01'} == {'WS8', 'OP8'}
    assert ('BOT-03', 'WS8') in base_bottlenecks
    assert ('BOT-04', 'OP8') in base_bottlenecks
    assert {owner for code, owner in scenario_bottlenecks if code == 'BOT-01'} == {'WS7'}
    assert ('BOT-04', 'OP8') not in scenario_bottlenecks

    demand = request['facts']['demand']['value']
    workload = demand * Decimal(graph['resource_uses'][0]['work_seconds_per_output']['value'])
    assert workload == 1710
    assert workload - Decimal(graph['resources'][0]['available_seconds']['value']) == 510
    assert demand * Decimal(scenario['overrides'][1]['new_value']) == 1000

    unchanged = client.get(model_path, headers=admin).raise_for_status().json()
    assert unchanged['graph'] == published.json()['graph']
    history = client.get(f'{model_path}/runs', headers=admin).raise_for_status().json()
    assert {run['input_hash'] for run in history} == {base.json()['input_hash'], scenario_run.json()['input_hash']}