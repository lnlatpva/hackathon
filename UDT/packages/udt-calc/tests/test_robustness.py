from decimal import Decimal
import pytest
from pydantic import ValidationError
from udt_calc import (Amount, Edge, Model, Node, ResourcePool, ResourceUse, Scenario, Override,
                      SourceKind, ResultKind, ResultStatus, validate_graph, critical_path,
                      capacity_analysis, compare_scenario, apply_scenario, ScenarioError,
                      takt, actual_utilization, availability, downtime_rate, value_added_share)


def test_source_status_preserved(amount):
    a = amount(1200, kind=SourceKind.MEASURED, reference="observed:shift1")
    b = amount(600, kind=SourceKind.MEASURED, reference="observed:shift1:busy")
    r = actual_utilization(b, a)
    assert r.kind == ResultKind.OBSERVED and r.status == ResultStatus.CALCULATED
    assert "observed:shift1" in r.sources


def test_no_zero_substitution_for_missing_edge_wait(parallel_model):
    new_edge = parallel_model.edges[1].model_copy(update={"waiting_seconds": None})
    m = parallel_model.model_copy(update={"edges": [parallel_model.edges[0], new_edge]})
    assert critical_path(m).metric.status == ResultStatus.UNAVAILABLE


def test_unverified_edge_does_not_fake_confirmed(parallel_model):
    edge = parallel_model.edges[0].model_copy(update={"verification": "unresolved"})
    m = parallel_model.model_copy(update={"edges": [edge, parallel_model.edges[1]]})
    assert critical_path(m).metric.status == ResultStatus.UNAVAILABLE
    assert any(i.code == "UNVERIFIED_LINK" for i in validate_graph(m).issues)


def test_inferred_edge_keeps_estimated_status(parallel_model):
    edge = parallel_model.edges[0].model_copy(update={"verification": "inferred"})
    m = parallel_model.model_copy(update={"edges": [edge, parallel_model.edges[1]]})
    assert critical_path(m).metric.status == ResultStatus.ESTIMATED
    assert "inferred" in " ".join(critical_path(m).assumptions)


def test_information_cycle_does_not_invalidate_material_dag(parallel_model):
    e = Edge(id="info", source_id="C", target_id="A", kind="information")
    m = parallel_model.model_copy(update={"edges": parallel_model.edges + (e,)})
    assert validate_graph(m).valid
    assert critical_path(m).metric.value == 40


def test_unknown_node_rejected(parallel_model):
    e = Edge(id="invalid", source_id="XYZ", target_id="A")
    m = parallel_model.model_copy(update={"edges": parallel_model.edges + (e,)})
    assert not validate_graph(m).valid


def test_bad_batch_override_rejected(parallel_model):
    scenario = Scenario(id="s", base_model_id=parallel_model.id,
                        overrides=[Override(target_type="node", target_id="A", field="batch_size", new_value=Decimal("1.5"), reason="bad test")])
    with pytest.raises(ScenarioError): apply_scenario(parallel_model, scenario)


def test_scenario_wrong_target_type_rejected(parallel_model):
    scenario = Scenario(id="s", base_model_id=parallel_model.id,
                        overrides=[Override(target_type="edge", target_id="A-C", field="parallel_channels", new_value=2, reason="bad test")])
    with pytest.raises(ScenarioError): apply_scenario(parallel_model, scenario)


def test_resource_use_missing_data_avoids_complete_capacity(parallel_model, amount):
    m = parallel_model.model_copy(update={
        "resources": [ResourcePool(id="R", name="R", available_seconds=amount(1200))],
        "resource_uses": [ResourceUse(node_id="A", resource_id="R")],
    })
    r = capacity_analysis(m)
    assert r.status == ResultStatus.UNAVAILABLE
    assert r.known_upper_bound == 40  # known stage-only bound remains valid as bound
    assert any("resource R/A" in t for t in r.missing)


def test_resource_capacity_requirement_detected(parallel_model, amount):
    r = ResourcePool(id="R", name="R", available_seconds=amount(1200))
    uses = [ResourceUse(node_id="A", resource_id="R", work_seconds_per_output=amount(20)),
            ResourceUse(node_id="B", resource_id="R", work_seconds_per_output=amount(30))]
    m = parallel_model.model_copy(update={"resources": [r], "resource_uses": uses})
    bot = [b for b in __import__('udt_calc').analyze(m, demand=30).bottlenecks if b.code == "BOT-04"]
    assert len(bot) == 1 and bot[0].owner_id == "R" and bot[0].threshold_value == 30


def test_measured_busy_cannot_exceed_available(amount):
    with pytest.raises(ValueError): actual_utilization(amount(11), amount(10))


def test_downtime_not_confused_with_availability(amount):
    assert downtime_rate(amount(2), amount(10)).value == 20
    assert availability(amount(2), amount(10)).value == 80


def test_value_added_exceeds_total_invalid(amount):
    with pytest.raises(ValueError): value_added_share(amount(11), amount(10))


def test_scenario_compare_delta(parallel_model):
    s = Scenario(id="s", base_model_id=parallel_model.id,
                 overrides=[Override(target_type="node", target_id="B", field="processing_seconds", new_value=10, reason="synthetic")])
    c = compare_scenario(parallel_model, s)
    assert c.baseline.capacity.known_upper_bound == 40
    assert c.projected.capacity.known_upper_bound == 60
    assert c.capacity_delta == 20


def test_fastapi_router_smoke(parallel_model):
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from udt_calc.api import create_router
    except ImportError:
        pytest.skip("FastAPI optional dependencies unavailable")
    app = FastAPI()
    app.include_router(create_router())
    response = TestClient(app).post("/api/v1/calculation/analyze", json={"model": parallel_model.model_dump(mode="json")})
    assert response.status_code == 200
    assert response.json()["graph"]["valid"] is True


def test_calc_026_real_scenario_metric_comparison_rejects_period_and_unit(amount):
    from udt_calc import compare_metrics, Metric, ResultKind
    def result(value, unit="s", period="shift-1", method="v1"):
        return Metric(code="cycle", value=value, unit=unit, status=ResultStatus.ESTIMATED,
                      kind=ResultKind.NORMATIVE, period_key=period, method_version=method)
    assert compare_metrics(result(20), result(10, period="shift-2")).status == ResultStatus.UNAVAILABLE
    assert compare_metrics(result(20), result(10, unit="min")).status == ResultStatus.UNAVAILABLE
    assert compare_metrics(result(20), result(10, method="v2")).status == ResultStatus.UNAVAILABLE
    assert compare_metrics(result(20), result(10)).value == -10


def test_original_frozen_model_sequence_cannot_be_mutated(parallel_model):
    with pytest.raises((AttributeError, TypeError)):
        parallel_model.nodes.append(Node(id="illegal", name="illegal"))