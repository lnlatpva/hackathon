from uuid import UUID

from fastapi.testclient import TestClient

from app.main import canonical_hash, create_app
def credentials(client, admin, name, role):
    created = client.post('/api/users', json={'login':name,'password':'LongPassword123!','role':role}, headers=admin)
    assert created.status_code == 201, created.text
    login = client.post('/api/auth/login', json={'login':name,'password':'LongPassword123!'})
    assert login.status_code == 200
    return {'Authorization':'Bearer ' + login.json()['access_token']}


def scenario_data():
    return {'name': 'What if B=15 s', 'overrides':[{'target_type':'node','target_id':'B',
        'field':'processing_seconds','new_value':'15',
        'reason':'synthetic_test_fixture; not factory measurements'}]}


def calc_request():
    source={'kind':'synthetic_test_fixture','reference':'fixture:shift','confirmed':True}
    return {'facts':{'available_seconds':{'value':'1200','unit':'s','source':source},
                     'demand':{'value':10,'source':source}}}


def test_health(client):
    assert client.get('/health').json()['status'] == 'ok'


def test_auth_required(client):
    assert client.get('/api/models').status_code == 401


def test_one_time_setup(client, admin):
    again=client.post('/api/auth/setup', json={'login':'admin2','password':'LongPassword123!'})
    assert again.status_code == 409


def test_setup_disabled():
    from app.main import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(database_url='sqlite:///:memory:',secret='another-long-secret-1234567890987',allow_setup=False)) as c:
        assert c.post('/api/auth/setup', json={'login':'admin','password':'LongPassword123!'}).status_code == 404


def test_bad_login(client, admin):
    assert client.post('/api/auth/login', json={'login':'admin','password':'wrong'}).status_code == 401


def test_admin_me(client, admin):
    assert client.get('/api/auth/me',headers=admin).json()['role']=='administrator'


def test_admin_adds_users(client, admin):
    m=credentials(client,admin,'manager','manager')
    assert client.get('/api/auth/me',headers=m).json()['role']=='manager'


def test_non_admin_cannot_add_users(client, admin):
    tech=credentials(client,admin,'tech','technologist')
    assert client.post('/api/users',json={'login':'new','password':'LongPassword123!','role':'observer'},headers=tech).status_code == 403


def test_model_crud_and_draft(client, admin):
    r=client.post('/api/models',json={'name':'Draft'},headers=admin)
    assert r.status_code == 201
    obj=r.json()
    assert obj['status']=='draft' and obj['graph']['nodes']==[]
    assert client.get('/api/models',headers=admin).json()[0]['id']==obj['id']
    assert client.post(f"/api/models/{obj['id']}/publish",headers=admin).status_code == 422


def test_publish_and_immutable(client, admin, example, published):
    row=client.get(f'/api/models/{published}',headers=admin).json()
    assert row['status']=='published'
    r=client.put(f'/api/models/{published}',headers=admin,
        json={'name':'Edit','state_type':'current','expected_revision':row['revision'],'graph':example})
    assert r.status_code == 409


def test_revision_check(client, admin, example):
    mid=client.post('/api/models',json={'name':'Draft'},headers=admin).json()['id']
    payload={'name':'Draft','state_type':'current','expected_revision':2,'graph':example}
    assert client.put(f'/api/models/{mid}',json=payload,headers=admin).status_code==409
    payload['expected_revision']=1
    assert client.put(f'/api/models/{mid}',json=payload,headers=admin).json()['revision']==2


def test_clone_version(client, admin, published):
    a=client.post(f'/api/models/{published}/versions',headers=admin)
    assert a.status_code==201
    assert a.json()['version']==2 and a.json()['status']=='draft'
    assert a.json()['graph']['id']==a.json()['id']
    assert len(client.get(f'/api/models/{published}/versions',headers=admin).json())==2


def test_roles(client, admin, published, example):
    manager=credentials(client,admin,'manager','manager')
    observer=credentials(client,admin,'watch','observer')
    assert client.get(f'/api/models/{published}',headers=observer).status_code==200
    assert client.post('/api/models',json={'name':'X','graph':example},headers=manager).status_code==403
    assert client.post(f'/api/models/{published}/calculate',json={},headers=observer).status_code==403
    assert client.post(f'/api/models/{published}/calculate',json={},headers=manager).status_code==201


def test_scenario_create(client, admin, published):
    result=client.post(f'/api/models/{published}/scenarios',json=scenario_data(),headers=admin)
    assert result.status_code==201,result.text
    assert result.json()['overrides'][0]['target_id']=='B'
    assert len(client.get(f'/api/models/{published}/scenarios',headers=admin).json())==1


def test_scenario_not_on_draft(client, admin):
    mid=client.post('/api/models',json={'name':'Draft'},headers=admin).json()['id']
    assert client.post(f'/api/models/{mid}/scenarios',json=scenario_data(),headers=admin).status_code==409


def test_scenario_invalid_target(client, admin, published):
    bad=scenario_data()
    bad['overrides'][0]['target_id']='no-such-node'
    assert client.post(f'/api/models/{published}/scenarios',json=bad,headers=admin).status_code==422


def test_scenario_invalid_value(client, admin, published):
    bad=scenario_data()
    bad['overrides'][0]['new_value']='-4'
    assert client.post(f'/api/models/{published}/scenarios',json=bad,headers=admin).status_code==422


def test_takt_calc(client, admin, published):
    r=client.post(f'/api/models/{published}/calculate',json=calc_request(),headers=admin)
    assert r.status_code==201,r.text
    k=r.json()['result']['metrics']['takt_seconds_per_finished']
    assert k['value']=='120' and k['unit']=='s/finished'


def test_capacity_and_parallel_graph(client, admin, published):
    r=client.post(f'/api/models/{published}/calculate',json={},headers=admin)
    assert r.status_code==201,r.text
    result=r.json()['result']
    assert result['metrics']['capacity_upper_bound']['value']=='40'
    assert result['metrics']['first_unit_lead_seconds']['value']=='40'
    assert result['metrics']['actual_utilization_percent']['value'] is None


def test_scenario_change_does_not_mutate_base(client, admin, published):
    orig=client.get(f'/api/models/{published}',headers=admin).json()['graph']
    sid=client.post(f'/api/models/{published}/scenarios',json=scenario_data(),headers=admin).json()['id']
    r=client.post(f'/api/scenarios/{sid}/calculate',json={},headers=admin)
    assert r.status_code==201,r.text
    assert r.json()['result']['capacity_delta']=='20'
    assert client.get(f'/api/models/{published}',headers=admin).json()['graph']==orig
    assert r.json()['result']['baseline_analysis'] is not None


def test_missing_facts_are_null(client, admin, published):
    run=client.post(f'/api/models/{published}/calculate',json={},headers=admin).json()
    assert run['result']['metrics']['cost_per_accepted_unit']['value'] is None
    assert run['result']['metrics']['cost_per_accepted_unit']['status']=='unavailable'
    assert run['result']['metrics']['takt_seconds_per_finished']['value'] is None


def test_quality_and_finance(client, admin, published):
    source={'kind':'synthetic_test_fixture','reference':'fixture:finance','confirmed':True}
    data={'facts':{'accepted':{'value':4,'source':source},'presented':{'value':5,'source':source},
                   'total_cost':{'value':'573','unit':'RUB','source':source},
                   'revenue':{'value':'140','unit':'RUB','source':source}}}
    r=client.post(f'/api/models/{published}/calculate',json=data,headers=admin)
    assert r.status_code==201,r.text
    m=r.json()['result']['metrics']
    assert float(m['customer_quality_percent']['value'])==80.0
    assert m['profit']['value']=='-433'


def test_run_history_immutable(client, admin, published):
    first=client.post(f'/api/models/{published}/calculate',json={},headers=admin).json()
    second=client.post(f'/api/models/{published}/calculate',json=calc_request(),headers=admin).json()
    history=client.get(f'/api/models/{published}/runs',headers=admin).json()
    assert len(history)==2 and {r['id'] for r in history}=={first['id'],second['id']}
    assert first['input_hash'] != second['input_hash']
    assert client.get(f"/api/runs/{first['id']}",headers=admin).json()['input_hash']==first['input_hash']
    assert client.put(f"/api/runs/{first['id']}",headers=admin,json={}).status_code==405


def test_scenario_edit_preserves_old_run(client,admin,published):
    sid=client.post(f'/api/models/{published}/scenarios',json=scenario_data(),headers=admin).json()['id']
    old=client.post(f'/api/scenarios/{sid}/calculate',json={},headers=admin).json()
    updated=scenario_data()
    updated['overrides'][0]['new_value']='35'
    assert client.put(f'/api/scenarios/{sid}',json=updated,headers=admin).status_code==200
    new=client.post(f'/api/scenarios/{sid}/calculate',json={},headers=admin).json()
    assert old['input_hash'] != new['input_hash']
    assert client.get(f"/api/runs/{old['id']}",headers=admin).json()['input_hash']==old['input_hash']


def test_unknown_model(client,admin):
    assert client.get('/api/models/does-not-exist',headers=admin).status_code==404


def test_strict_schema(client,admin):
    assert client.post('/api/models',headers=admin,json={'name':'X','unexpected':1}).status_code==422


def test_hash_order_independent():
    assert canonical_hash({'a':1,'b':[3,4]})==canonical_hash({'b':[3,4],'a':1})


def test_pgddl_compiles():
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects.postgresql import dialect
    from app.db import Base
    for table in Base.metadata.sorted_tables:
        sql=str(CreateTable(table).compile(dialect=dialect()))
        assert 'CREATE TABLE' in sql
        if table.name=='models':
            assert 'JSONB' in sql


def test_cycle_rejected_on_publish(client, admin, example):
    example['edges'].append({'id':'C-A','source_id':'C','target_id':'A',
                             'kind':'material','verification':'confirmed'})
    mid=client.post('/api/models',json={'name':'Cyclic','graph':example},headers=admin).json()['id']
    r=client.post(f'/api/models/{mid}/publish',headers=admin)
    assert r.status_code == 422
    assert 'GRAPH_CYCLE' in r.text


def test_node_costs_and_cost_scenario(client, admin, example):
    source={'kind':'synthetic_test_fixture','reference':'fixture:node_costs','confirmed':True}
    def c(x):return {'value':str(x),'unit':'RUB/output','source':source}
    base_cost={'A':c(10),'B':c(20),'C':c(30)}
    r=client.post('/api/models',json={'name':'Cost graph','graph':example,'node_costs':base_cost},headers=admin)
    assert r.status_code==201,r.text
    mid=r.json()['id']
    assert client.post(f'/api/models/{mid}/publish',headers=admin).status_code==200
    base=client.post(f'/api/models/{mid}/calculate',json={},headers=admin).json()
    assert float(base['result']['metrics']['cost_per_finished_from_nodes']['value'])==60.0
    sc=client.post(f'/api/models/{mid}/scenarios',json={'name':'Cheaper B','cost_overrides':{'B':c(7)}},headers=admin)
    assert sc.status_code==201,sc.text
    result=client.post(f"/api/scenarios/{sc.json()['id']}/calculate",json={},headers=admin).json()['result']
    assert float(result['metrics']['cost_per_finished_from_nodes']['value'])==47.0
    assert float(result['node_cost_delta']) == -13.0
    assert float(result['baseline_node_cost']['value']) == 60.0
    persisted=client.get(f'/api/models/{mid}',headers=admin).json()['node_costs']
    assert {k:v['value'] for k,v in persisted.items()} == {'A':'10','B':'20','C':'30'}


def test_partial_node_costs_unavailable(client, admin, example):
    source={'kind':'synthetic_test_fixture','reference':'fixture:partial','confirmed':True}
    r=client.post('/api/models',json={'name':'Partial','graph':example,
        'node_costs':{'A':{'value':'10','unit':'RUB/output','source':source}}},headers=admin)
    mid=r.json()['id']
    output=client.post(f'/api/models/{mid}/calculate',json={},headers=admin).json()
    assert output['result']['metrics']['cost_per_finished_from_nodes']['status']=='unavailable'
    assert output['result']['metrics']['cost_per_finished_from_nodes']['value'] is None


def test_node_cost_invalid_target(client, admin, example):
    source={'kind':'synthetic_test_fixture','reference':'fixture:badcost','confirmed':True}
    r=client.post('/api/models',json={'name':'Bad','graph':example,
        'node_costs':{'MISSING':{'value':'10','unit':'RUB/output','source':source}}},headers=admin)
    assert r.status_code == 422


def test_factory_fixture_retains_unknowns():
    import json
    from pathlib import Path
    data=json.loads((Path(__file__).resolve().parents[1]/'examples'/'factory_confirmed.json').read_text())
    assert data['operation_8']['sum_of_raw_values']==171
    assert data['operation_8']['actual_cycle_seconds'] is None
    assert data['shift']['available_production_seconds'] is None


def test_cors_allows_configured_frontend(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('UDT_CORS_ORIGINS', 'http://localhost:5173')
    app = create_app(database_url='sqlite:///:memory:',
                     secret='a-long-random-test-secret-1234567890', allow_setup=False)
    with TestClient(app) as client:
        r = client.options('/api/models', headers={
            'Origin':'http://localhost:5173',
            'Access-Control-Request-Method':'GET',
            'Access-Control-Request-Headers':'authorization',
        })
        assert r.status_code == 200
        assert r.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_cors_denies_unconfigured_frontend(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('UDT_CORS_ORIGINS', 'http://localhost:5173')
    app = create_app(database_url='sqlite:///:memory:',
                     secret='a-long-random-test-secret-1234567890', allow_setup=False)
    with TestClient(app) as client:
        r = client.options('/api/models', headers={
            'Origin':'https://untrusted.example',
            'Access-Control-Request-Method':'GET',
        })
        assert r.status_code == 400
        assert 'access-control-allow-origin' not in r.headers


def test_delete_family_removes_all_versions_and_dependent_data(client, admin, published):
    """Administrator explicitly deletes the ENTIRE family, including its history."""
    extra = client.post(f'/api/models/{published}/versions', headers=admin).json()
    sid = client.post(f'/api/models/{published}/scenarios', json=scenario_data(), headers=admin).json()['id']
    run = client.post(f'/api/scenarios/{sid}/calculate', json={}, headers=admin).json()['id']
    another = client.post('/api/models', json={'name':'Unrelated'}, headers=admin).json()['id']

    # A bad confirmation must not remove anything.
    wrong = client.request('DELETE', f'/api/models/{published}', json={'confirm_name':'wrong'}, headers=admin)
    assert wrong.status_code == 422
    assert len(client.get(f'/api/models/{published}/versions', headers=admin).json()) == 2

    deleted = client.request('DELETE', f"/api/models/{extra['id']}",
                             json={'confirm_name':'Synthetic demo'}, headers=admin)
    assert deleted.status_code == 204 and not deleted.content
    assert client.get(f'/api/models/{published}', headers=admin).status_code == 404
    assert client.get(f"/api/models/{extra['id']}", headers=admin).status_code == 404
    assert client.get(f'/api/scenarios/{sid}', headers=admin).status_code == 404
    assert client.get(f'/api/runs/{run}', headers=admin).status_code == 404
    assert client.get(f'/api/models/{another}', headers=admin).status_code == 200


def test_delete_model_requires_administrator_and_confirmation(client, admin, published):
    tech = credentials(client, admin, 'tech_delete', 'technologist')
    observer = credentials(client, admin, 'observer_delete', 'observer')
    for headers in (tech, observer):
        res = client.request('DELETE', f'/api/models/{published}',
                             json={'confirm_name':'Synthetic demo'}, headers=headers)
        assert res.status_code == 403
    assert client.request('DELETE', f'/api/models/{published}', headers=admin).status_code == 422
    assert client.get(f'/api/models/{published}', headers=admin).status_code == 200


def test_scenario_can_override_resource_work_without_mutating_base(client, admin, example):
    source = {'kind':'synthetic_test_fixture','reference':'fixture:resource','confirmed':True}
    example['resources']=[{'id':'OP-B','name':'Synthetic B operator',
                           'available_seconds':{'value':'1200','unit':'s','source':source}}]
    example['resource_uses']=[{'node_id':'B','resource_id':'OP-B',
                               'work_seconds_per_output':{'value':'30','unit':'s','source':source}}]
    created = client.post('/api/models', json={'name':'Resource scenario demo','graph':example},headers=admin)
    assert created.status_code == 201, created.text
    mid = created.json()['id']
    assert client.post(f'/api/models/{mid}/publish',headers=admin).status_code == 200
    before = client.post(f'/api/models/{mid}/calculate',json={},headers=admin).json()['result']
    assert float(before['analysis']['capacity']['known_upper_bound']) == 40
    scenario = {'name':'B faster with reassigned labor', 'overrides':[
        {'target_type':'node','target_id':'B','field':'processing_seconds','new_value':'10','reason':'synthetic fixture'},
        {'target_type':'resource_use','target_id':'B::OP-B','field':'work_seconds_per_output','new_value':'10','reason':'synthetic fixture'}]}
    created_sc = client.post(f'/api/models/{mid}/scenarios',json=scenario,headers=admin)
    assert created_sc.status_code==201,created_sc.text
    out = client.post(f"/api/scenarios/{created_sc.json()['id']}/calculate",json={},headers=admin)
    assert out.status_code==201,out.text
    result = out.json()['result']
    assert float(result['analysis']['capacity']['known_upper_bound']) == 60
    assert float(result['capacity_delta']) == 20
    base = client.get(f'/api/models/{mid}',headers=admin).json()['graph']
    assert base['resource_uses'][0]['work_seconds_per_output']['value']=='30'
    assert base['nodes'][1]['processing_seconds']['value']=='30'
    assert out.json()['input_snapshot']['overrides'][1]['target_type'] == 'resource_use'


def test_existing_scenario_can_add_resource_override_by_put(client, admin, example):
    """The UI can upgrade an existing 'duration only' scenario without a new model version."""
    src={'kind':'synthetic_test_fixture','reference':'fixture:ui-workflow','confirmed':True}
    example['resources']=[{'id':'R-B','name':'Operator B','available_seconds':{'value':'1200','unit':'s','source':src}}]
    example['resource_uses']=[{'node_id':'B','resource_id':'R-B',
                               'work_seconds_per_output':{'value':'30','unit':'s','source':src}}]
    mid=client.post('/api/models',json={'name':'Workflow demo','graph':example},headers=admin).json()['id']
    assert client.post(f'/api/models/{mid}/publish',headers=admin).status_code==200
    node_only={'name':'Faster B', 'overrides':[{'target_type':'node','target_id':'B','field':'processing_seconds',
                                               'new_value':'10','reason':'test what-if'}]}
    sid=client.post(f'/api/models/{mid}/scenarios',json=node_only,headers=admin).json()['id']
    old=client.post(f'/api/scenarios/{sid}/calculate',json={},headers=admin).json()
    assert float(old['result']['analysis']['capacity']['known_upper_bound'])==40
    node_only['overrides'].append({'target_type':'resource_use','target_id':'B::R-B',
                                   'field':'work_seconds_per_output','new_value':'10','reason':'aligned operator hypothetical'})
    updated=client.put(f'/api/scenarios/{sid}',json=node_only,headers=admin)
    assert updated.status_code==200, updated.text
    new=client.post(f'/api/scenarios/{sid}/calculate',json={},headers=admin).json()
    assert float(new['result']['analysis']['capacity']['known_upper_bound'])==60
    assert client.get(f"/api/runs/{old['id']}",headers=admin).json()['input_hash']==old['input_hash']


def test_postgresql_keeps_models_scenarios_and_runs_after_restart(postgresql_url, example):
    secret = 'udt-postgresql-integration-test-secret'
    credentials = {'login': 'udt-test-admin', 'password': 'integration-test-password'}
    app = create_app(database_url=postgresql_url, secret=secret, allow_setup=True)
    try:
        with TestClient(app) as client:
            assert client.get('/api/models').status_code == 401
            setup = client.post('/api/auth/setup', json=credentials)
            assert setup.status_code == 201, setup.text
            headers = {'Authorization': f"Bearer {setup.json()['access_token']}"}

            model = client.post('/api/models', json={'name': 'Test graph', 'graph': example}, headers=headers)
            assert model.status_code == 201, model.text
            model_path = f"/api/models/{model.json()['id']}"
            assert client.post(f'{model_path}/publish', headers=headers).status_code == 200

            scenario = client.post(f'{model_path}/scenarios', json=scenario_data(), headers=headers)
            assert scenario.status_code == 201, scenario.text
            scenario_id = scenario.json()['id']
            run = client.post(f'/api/scenarios/{scenario_id}/calculate', json={}, headers=headers)
            assert run.status_code == 201, run.text
            assert run.json()['result']['capacity_delta'] == '20'
    finally:
        app.state.engine.dispose()

    restarted_app = create_app(database_url=postgresql_url, secret=secret, allow_setup=False)
    try:
        with TestClient(restarted_app) as client:
            assert client.post('/api/auth/setup', json=credentials).status_code == 404
            login = client.post('/api/auth/login', json=credentials)
            assert login.status_code == 200, login.text
            headers = {'Authorization': f"Bearer {login.json()['access_token']}"}

            model = client.get(model_path, headers=headers).raise_for_status().json()
            assert model['status'] == 'published'
            scenarios = client.get(f'{model_path}/scenarios', headers=headers).raise_for_status().json()
            assert [saved['id'] for saved in scenarios] == [scenario_id]
            runs = client.get(f'{model_path}/runs', headers=headers).raise_for_status().json()
            assert [saved['input_hash'] for saved in runs] == [run.json()['input_hash']]
    finally:
        restarted_app.state.engine.dispose()