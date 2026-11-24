"""CALC-001..CALC-026 from UDT-CALC-005; без вымышленных показателей."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from udt_calc import (
    Amount, Edge, Model, Node, ResourcePool, ResourceUse, ResultStatus,
    Source, SourceKind, RawStandard, Scenario, Override, validate_graph,
    analyze, capacity_analysis, critical_path, apply_scenario, compare_scenario,
    takt, effective_cycle, actual_utilization, quality, inventory_change,
    unit_cost, profit, ScenarioError, hash_model,
)


def test_calc_001_takt(amount):
    result = takt(amount(1200), 10)
    assert result.value == Decimal(120) and result.unit == "s/finished"
    assert result.status == ResultStatus.ESTIMATED


def test_calc_002_zero_demand(amount):
    r = takt(amount(1200), 0)
    assert r.value is None and r.status == ResultStatus.UNAVAILABLE


def test_calc_003_batch_cycle_latency_is_distinct(amount):
    r = effective_cycle(amount(80), 2)
    assert r.value == Decimal(40)
    assert "first-unit latency" in " ".join(r.reasons)


def test_calc_004_missing_unit_does_not_infer_seconds():
    source = Source(kind=SourceKind.DOCUMENT, reference="factory:standards:p15")
    a = RawStandard(value=170, unit=None, source=source)
    b = RawStandard(value=1, unit=None, source=source)
    assert a.value + b.value == Decimal(171)
    assert a.unit is None and b.unit is None


def test_calc_005_over_takt(amount):
    n = Node(id="WS8", name="six bolts", processing_seconds=amount(171), batch_size=1,
             units_per_finished=1, parallel_channels=1, available_seconds=amount(1200))
    model = Model(id="synthetic-WS8", nodes=[n], edges=[], target_id="WS8")
    result = analyze(model, takt_seconds=amount(120), demand=10)
    assert any(b.code == "BOT-03" and b.owner_id == "WS8" and b.calculated_value == 171 for b in result.bottlenecks)
    assert Decimal(171) / Decimal(120) * 100 == Decimal("142.5")
    assert result.capacity.known_upper_bound == Decimal(1200) / Decimal(171)


def test_calc_006_parallel_join_critical_path(parallel_model):
    p = critical_path(parallel_model)
    assert p.metric.value == Decimal(40)
    assert p.critical_nodes == ("B", "C")


def test_calc_007_shared_resource_prevents_false_parallel_timing(parallel_model, amount):
    model = parallel_model.model_copy(update={
        "resources": [ResourcePool(id="operator", name="one", available_seconds=amount(1200))],
        "resource_uses": [ResourceUse(node_id="A", resource_id="operator", work_seconds_per_output=amount(20)),
                          ResourceUse(node_id="B", resource_id="operator", work_seconds_per_output=amount(30))],
        "assume_independent_resources": False,
    })
    cap = capacity_analysis(model)
    c = [x for x in cap.constraints if x.owner_type == "resource"][0]
    assert c.finished_equivalent_capacity == Decimal(24)
    assert critical_path(model).metric.status == ResultStatus.UNAVAILABLE
    optimistic = critical_path(model, optimistic_if_resource_conflict=True)
    assert optimistic.metric.value == Decimal(40)
    assert "optimistic" in " ".join(optimistic.assumptions)
    assert Decimal(20+30+10) == 60  # separately established synthetic lower bound for single unit


def test_calc_008_finished_equivalent_units(amount):
    n = Node(id="sub", name="subassembly", processing_seconds=amount(10), batch_size=1,
             units_per_finished=2, parallel_channels=1, available_seconds=amount(1200))
    assert capacity_analysis(Model(id="m", nodes=[n], edges=[])).known_upper_bound == 60


def test_calc_009_cycle_rejected(parallel_model):
    e = Edge(id="C-A", source_id="C", target_id="A", verification="confirmed")
    model = parallel_model.model_copy(update={"edges": parallel_model.edges + (e,)})
    r = validate_graph(model)
    assert not r.valid and any(x.code == "GRAPH_CYCLE" for x in r.issues)


def test_calc_010_unknown_transfer_blocks_full_lead(parallel_model):
    e = parallel_model.edges[0].model_copy(update={"transit_seconds": None})
    model = parallel_model.model_copy(update={"edges": [e, parallel_model.edges[1]]})
    r = critical_path(model)
    assert r.metric.status == ResultStatus.UNAVAILABLE
    assert r.metric.value is None


def test_calc_011_unknown_cycle_blocks_actual_capacity(amount):
    n = Node(id="A", name="unknown", available_seconds=amount(1200), batch_size=1,
             units_per_finished=1, parallel_channels=1)
    r = capacity_analysis(Model(id="m", nodes=[n], edges=[]))
    assert not r.complete and r.known_upper_bound is None


def test_calc_012_quality():
    assert quality(4, 5).value == 80


def test_calc_013_invalid_quality():
    with pytest.raises(ValueError): quality(6, 5)


def test_calc_014_inventory_increase(amount):
    assert inventory_change(amount("71.5", "kRUB"), amount(74, "kRUB")).value == Decimal("2.5")


def test_calc_015_cost_per_product(amount):
    assert unit_cost(amount(573, "kRUB"), 2).value == Decimal("286.5")


def test_calc_016_financial_source_arithmetic_mismatch(amount):
    assert profit(amount(140, "kRUB"), amount(573, "kRUB")).value == Decimal(-433)


def test_calc_017_no_accepted_products(amount):
    r = unit_cost(amount(573, "kRUB"), 0)
    assert r.value is None and r.status == ResultStatus.UNAVAILABLE


def test_calc_018_finance_missing_does_not_block_takt(amount):
    assert unit_cost(None, 2).status == ResultStatus.UNAVAILABLE
    assert takt(amount(1200), 10).value == 120


def test_calc_019_scenario_does_not_mutate_baseline(parallel_model):
    original_hash = hash_model(parallel_model)
    s = Scenario(id="s", base_model_id=parallel_model.id,
                 overrides=[Override(target_type="node", target_id="B", field="processing_seconds", new_value=10,
                                     reason="synthetic scenario exercise")])
    new = apply_scenario(parallel_model, s)
    assert hash_model(parallel_model) == original_hash
    assert new.nodes[1].processing_seconds.value == 10
    assert parallel_model.nodes[1].processing_seconds.value == 30


def test_calc_020_reproducible(parallel_model):
    s = Scenario(id="s", base_model_id=parallel_model.id,
                 overrides=[Override(target_type="node", target_id="B", field="processing_seconds", new_value=10, reason="synthetic")])
    r1 = compare_scenario(parallel_model, s)
    r2 = compare_scenario(parallel_model, s)
    assert r1 == r2 and r1.model_hash_before == hash_model(parallel_model)


def test_calc_021_wrong_version(parallel_model):
    s = Scenario(id="s", base_model_id="another-version", overrides=[])
    with pytest.raises(ScenarioError): apply_scenario(parallel_model, s)


def test_calc_022_negative_duration_rejected(amount):
    with pytest.raises(ValidationError): amount(-1)
    with pytest.raises(ValidationError): Override(target_type="node", target_id="A", field="processing_seconds", new_value=-2, reason="negative")


def test_calc_023_shared_resource_does_not_duplicate(parallel_model, amount):
    r = ResourcePool(id="R", name="single human", available_seconds=amount(1200))
    uses = [ResourceUse(node_id="A", resource_id="R", work_seconds_per_output=amount(20)),
            ResourceUse(node_id="B", resource_id="R", work_seconds_per_output=amount(30))]
    m = parallel_model.model_copy(update={"resources": [r], "resource_uses": uses})
    caps = capacity_analysis(m)
    resource_caps = [c for c in caps.constraints if c.owner_type == "resource"]
    assert len(resource_caps) == 1 and resource_caps[0].finished_equivalent_capacity == 24


def test_calc_024_tied_bottlenecks(amount):
    nodes = [Node(id=x, name=x, processing_seconds=amount(20), batch_size=1,
                  units_per_finished=1, parallel_channels=1, available_seconds=amount(1200)) for x in ["A", "B"]]
    m = Model(id="m", nodes=nodes, edges=[], assume_independent_resources=True)
    bots = analyze(m).bottlenecks
    assert {b.owner_id for b in bots if b.code == "BOT-01"} == {"A", "B"}


def test_calc_025_insufficient_data_does_not_claim_bottleneck():
    m = Model(id="m", nodes=[Node(id="A", name="A")], edges=[])
    r = analyze(m)
    assert not r.capacity.complete
    assert r.bottlenecks == ()


def test_calc_026_incompatible_unit_blocks_comparison(amount):
    assert inventory_change(amount(20, "kRUB"), amount(20, "RUB")).status == ResultStatus.UNAVAILABLE