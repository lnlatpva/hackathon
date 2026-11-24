"""Выполните валидацию материального DAG; информационные связи (ребра) не должны определять материальный порядок предшествования."""
from __future__ import annotations
import networkx as nx
from .contracts import GraphCheck, Issue, Model


def material_dag(model: Model) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(n.id for n in model.nodes)
    # Последовательность задают материальные связи; информационные не влияют на DAG.
    graph.add_edges_from((e.source_id, e.target_id) for e in model.edges if e.kind == "material")
    return graph


def validate_graph(model: Model) -> GraphCheck:
    issues: list[Issue] = []
    node_ids = [n.id for n in model.nodes]
    edge_ids = [e.id for e in model.edges]
    resources = [r.id for r in model.resources]
    if len(set(node_ids)) != len(node_ids):
        issues.append(Issue(code="DUPLICATE_NODE", message="Duplicate node IDs", blocking=True))
    if len(set(edge_ids)) != len(edge_ids):
        issues.append(Issue(code="DUPLICATE_EDGE", message="Duplicate edge IDs", blocking=True))
    if len(set(resources)) != len(resources):
        issues.append(Issue(code="DUPLICATE_RESOURCE", message="Duplicate resource IDs", blocking=True))
    known, pool = set(node_ids), set(resources)
    seen: set[tuple] = set()
    for e in model.edges:
        if e.source_id not in known or e.target_id not in known:
            issues.append(Issue(code="UNKNOWN_NODE", message=f"Edge {e.id} points to an unknown node", blocking=True))
        if e.source_id == e.target_id:
            issues.append(Issue(code="SELF_EDGE", message=f"Self edge: {e.id}", blocking=True))
        key = (e.source_id, e.target_id, e.kind, e.item_id)
        if key in seen:
            issues.append(Issue(code="DUPLICATE_LINK", message=f"Duplicate link: {e.id}", blocking=True))
        seen.add(key)
        if e.kind == "material" and e.verification != "confirmed":
            issues.append(Issue(code="UNVERIFIED_LINK", message=f"{e.id}: {e.verification}", blocking=False))
    if model.target_id is not None and model.target_id not in known:
        issues.append(Issue(code="UNKNOWN_TARGET", message="Unknown target node", blocking=True))
    uses = set()
    for u in model.resource_uses:
        if u.node_id not in known or u.resource_id not in pool:
            issues.append(Issue(code="UNKNOWN_RESOURCE_ASSIGNMENT", message=f"{u.node_id}/{u.resource_id}", blocking=True))
        key = (u.node_id, u.resource_id)
        if key in uses:
            issues.append(Issue(code="DUPLICATE_RESOURCE_USE", message=str(key), blocking=True))
        uses.add(key)
    if any(x.blocking for x in issues):
        return GraphCheck(valid=False, issues=tuple(issues))
    g = material_dag(model)
    # Материальный поток не должен содержать циклов.
    if not nx.is_directed_acyclic_graph(g):
        cycles = list(nx.simple_cycles(g))
        issues.append(Issue(code="GRAPH_CYCLE", message=f"Material cycle: {cycles[0]}", blocking=True))
        return GraphCheck(valid=False, issues=tuple(issues))
    if model.target_id:
        relevant = nx.ancestors(g, model.target_id) | {model.target_id}
        for n in node_ids:
            if n not in relevant:
                issues.append(Issue(code="ORPHAN_NODE", message=f"Node {n} does not contribute to target", node_id=n))
    return GraphCheck(valid=True, issues=tuple(issues), order=tuple(nx.topological_sort(g)))


def contributing_nodes(model: Model) -> set[str]:
    g = material_dag(model)
    return (nx.ancestors(g, model.target_id) | {model.target_id}) if model.target_id else set(g.nodes)