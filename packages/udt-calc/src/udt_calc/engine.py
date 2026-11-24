"""Ограничения пропускной способности детерминированного графа, анализ предшествования, правила выявления узких мест."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
import networkx as nx

from .contracts import (
    Analysis, Amount, Bottleneck, CapacityReport, Constraint, GraphCheck,
    Metric, Model, PathReport, ResultKind, ResultStatus,
)
from .graph import validate_graph, material_dag, contributing_nodes
from .metrics import D, _unavailable, _result


def _seconds(sample: Amount | None) -> bool:
    return sample is not None and sample.unit == "s"


def capacity_analysis(model: Model, check: GraphCheck | None = None) -> CapacityReport:
    check = check or validate_graph(model)
    if not check.valid:
        return CapacityReport(status=ResultStatus.UNAVAILABLE, known_upper_bound=None, complete=False,
                              constraints=(), missing=tuple(i.message for i in check.issues if i.blocking))
    relevant = contributing_nodes(model)
    nodes = {n.id: n for n in model.nodes if n.id in relevant}
    missing: list[str] = []
    assumptions = ["steady-state continuous upper bound, not achievable finished units in a short shift",
                   "initial inventory, queueing, startup delay and line scheduling not simulated"]
    constraints: list[Constraint] = []
    active = [n for n in nodes.values() if n.kind in ("operation", "inspection")]
    if not active:
        missing.append("no operation or inspection node")
    for n in active:
        absent = []
        if not _seconds(n.processing_seconds): absent.append("processing_seconds[s]")
        if n.batch_size is None: absent.append("batch_size")
        if n.units_per_finished is None: absent.append("units_per_finished")
        if n.parallel_channels is None: absent.append("parallel_channels")
        if not _seconds(n.available_seconds): absent.append("available_seconds[s]")
        if absent:
            missing.append(f"node {n.id}: missing/invalid {', '.join(absent)}")
            continue
        if n.processing_seconds.value == 0:
            missing.append(f"node {n.id}: processing time must exceed zero for capacity")
            continue
        # Верхняя граница мощности учитывает фонд времени, партию и параллельные каналы.
        value = (n.available_seconds.value * D(n.parallel_channels) * D(n.batch_size)
                 / n.processing_seconds.value / n.units_per_finished)
        constraints.append(Constraint(owner_type="operation", owner_id=n.id,
                                      finished_equivalent_capacity=value,
                                      sources=(n.processing_seconds.source.reference, n.available_seconds.source.reference)))
    uses_by_resource: dict[str, list] = defaultdict(list)
    for use in model.resource_uses:
        if use.node_id in relevant:
            uses_by_resource[use.resource_id].append(use)
    pool_by_id = {r.id: r for r in model.resources}
    for resource_id, uses in uses_by_resource.items():
        resource = pool_by_id[resource_id]
        if not _seconds(resource.available_seconds):
            missing.append(f"resource {resource_id}: missing available_seconds[s]")
            continue
        # Для общего ресурса суммируем трудозатраты всех назначенных операций.
        work = D(0)
        references = [resource.available_seconds.source.reference]
        broken = False
        for u in uses:
            coefficient = nodes[u.node_id].units_per_finished
            if not _seconds(u.work_seconds_per_output) or coefficient is None:
                missing.append(f"resource {resource_id}/{u.node_id}: missing work_seconds_per_output[s] or units_per_finished")
                broken = True
                continue
            work += u.work_seconds_per_output.value * coefficient
            references.append(u.work_seconds_per_output.source.reference)
        if broken: continue
        if work == 0:
            missing.append(f"resource {resource_id}: workload must exceed zero for capacity")
            continue
        constraints.append(Constraint(owner_type="resource", owner_id=resource_id,
                                      finished_equivalent_capacity=resource.available_seconds.value / work,
                                      sources=tuple(references)))
    # Отсутствие назначения ресурса не означает, что операция независима от остальных.
    for n in active:
        if n.id not in {u.node_id for u in model.resource_uses}:
            assumptions.append(f"node {n.id}: no explicit resource assignment; stage-channel capacity is an optimistic bound")
    known = min((c.finished_equivalent_capacity for c in constraints), default=None)
    return CapacityReport(status=ResultStatus.ESTIMATED if not missing else ResultStatus.UNAVAILABLE,
                          known_upper_bound=known, complete=not missing, constraints=tuple(constraints),
                          missing=tuple(missing), assumptions=tuple(dict.fromkeys(assumptions)))


def _parallel_pairs(g: nx.DiGraph, ids: set[str]) -> list[tuple[str, str]]:
    arr = sorted(ids)
    return [(a, b) for i, a in enumerate(arr) for b in arr[i+1:]
            if not nx.has_path(g, a, b) and not nx.has_path(g, b, a)]


def critical_path(model: Model, check: GraphCheck | None = None,
                  *, optimistic_if_resource_conflict: bool = False) -> PathReport:
    check = check or validate_graph(model)
    if not check.valid:
        return PathReport(metric=_unavailable("first_unit_lead_seconds", "invalid material DAG"))
    if model.target_id is None:
        return PathReport(metric=_unavailable("first_unit_lead_seconds", "target_id required"))
    graph = material_dag(model)
    relevant = contributing_nodes(model)
    nodes = {n.id: n for n in model.nodes if n.id in relevant}
    relevant_edges = [e for e in model.edges if e.kind == "material"
                      and e.source_id in relevant and e.target_id in relevant]
    missing: list[str] = []
    inputs: list[Amount] = []
    for n in nodes.values():
        if not _seconds(n.processing_seconds):
            missing.append(f"node {n.id}: missing first-batch processing latency in seconds")
        else:
            inputs.append(n.processing_seconds)
    for e in relevant_edges:
        if e.verification == "unresolved":
            missing.append(f"edge {e.id}: material dependency unresolved")
        if not _seconds(e.transit_seconds): missing.append(f"edge {e.id}: transit time unknown")
        if not _seconds(e.waiting_seconds): missing.append(f"edge {e.id}: waiting time unknown")
        if _seconds(e.transit_seconds): inputs.append(e.transit_seconds)
        if _seconds(e.waiting_seconds): inputs.append(e.waiting_seconds)
    if missing:
        return PathReport(metric=_unavailable("first_unit_lead_seconds", *missing))
    incomparable = _parallel_pairs(graph, relevant)
    used_by_node = defaultdict(set)
    for u in model.resource_uses:
        if u.node_id in relevant:
            used_by_node[u.node_id].add(u.resource_id)
    conflict = [(a, b) for a,b in incomparable if used_by_node[a] & used_by_node[b]]
    unknown = [(a, b) for a,b in incomparable if
               (not used_by_node[a] or not used_by_node[b]) and not model.assume_independent_resources]
    # Без подтверждения независимости ресурсов точное ВПП по критическому пути недоступно.
    if (conflict or unknown) and not optimistic_if_resource_conflict:
        msg = "parallel branches share a resource; scheduling required" if conflict else "parallel resource independence not confirmed"
        return PathReport(metric=_unavailable("first_unit_lead_seconds", msg))
    predecessors = defaultdict(list)
    for e in relevant_edges:
        predecessors[e.target_id].append(e)
    finish: dict[str, Decimal] = {}
    path: dict[str, tuple[str, ...]] = {}
    for node_id in check.order:
        if node_id not in relevant: continue
        parents = predecessors[node_id]
        if parents:
            best = max(parents, key=lambda e: finish[e.source_id] + e.transit_seconds.value + e.waiting_seconds.value)
            ready = finish[best.source_id] + best.transit_seconds.value + best.waiting_seconds.value
            path[node_id] = path[best.source_id] + (node_id,)
        else:
            ready = D(0)  # Допущение: исходные материалы доступны с начала периода.
            path[node_id] = (node_id,)
        finish[node_id] = ready + nodes[node_id].processing_seconds.value
    assumptions = ["initial inputs are available at t=0",
                   "processing_seconds is latency to the first completed batch, not per-output interval"]
    if conflict or unknown:
        assumptions.append("optimistic precedence lower bound; shared/unverified resource scheduling omitted")
    if any(e.verification == "inferred" for e in relevant_edges):
        assumptions.append("one or more material dependencies inferred")
    metric = _result("first_unit_lead_seconds", finish[model.target_id], "s", inputs,
                     force_estimate=True, reasons=assumptions)
    return PathReport(metric=metric, critical_nodes=path[model.target_id], assumptions=tuple(assumptions))


def detect_bottlenecks(model: Model, capacity: CapacityReport, *,
                       takt_seconds: Amount | None = None,
                       demand: int | None = None) -> tuple[Bottleneck, ...]:
    found: list[Bottleneck] = []
    if capacity.complete and capacity.known_upper_bound is not None:
        minimum = capacity.known_upper_bound
        for c in capacity.constraints:
            if c.finished_equivalent_capacity == minimum:
                found.append(Bottleneck(code="BOT-01", owner_type=c.owner_type, owner_id=c.owner_id,
                                        explanation="minimum known theoretical capacity; ties retained",
                                        calculated_value=minimum))
    if _seconds(takt_seconds) and takt_seconds.value > 0:
        for n in model.nodes:
            if n.kind not in ("operation", "inspection"):
                continue
            if not _seconds(n.processing_seconds) or not n.batch_size or not n.units_per_finished or not n.parallel_channels:
                continue
            required = (n.processing_seconds.value * n.units_per_finished / D(n.batch_size)
                        / D(n.parallel_channels))
            ratio = required / takt_seconds.value * 100
            if ratio > 100:
                found.append(Bottleneck(code="BOT-03", owner_type="operation", owner_id=n.id,
                                        explanation="required cycle exceeds takt under parallel-channel assumption",
                                        calculated_value=required, threshold_value=takt_seconds.value))
    if demand is not None and demand < 0:
        raise ValueError("negative demand")
    if demand is not None and demand > 0:
        for c in capacity.constraints:
            if c.owner_type == "resource" and c.finished_equivalent_capacity < D(demand):
                found.append(Bottleneck(code="BOT-04", owner_type="resource", owner_id=c.owner_id,
                                        explanation="resource cannot provide required workload for requested demand",
                                        calculated_value=c.finished_equivalent_capacity,
                                        threshold_value=D(demand)))
    return tuple(found)


def analyze(model: Model, *, takt_seconds: Amount | None = None,
            demand: int | None = None, optimistic_lead_time: bool = False) -> Analysis:
    graph = validate_graph(model)
    cap = capacity_analysis(model, graph)
    lead = critical_path(model, graph, optimistic_if_resource_conflict=optimistic_lead_time)
    bots = detect_bottlenecks(model, cap, takt_seconds=takt_seconds, demand=demand) if graph.valid else ()
    return Analysis(graph=graph, capacity=cap, lead_time=lead, bottlenecks=bots)