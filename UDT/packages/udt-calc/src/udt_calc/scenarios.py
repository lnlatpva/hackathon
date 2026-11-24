"""вная ручная корректировка числовых значений с сохранением истории изменений (аудитом). Без изменения исходной модели."""
from __future__ import annotations
import hashlib
import json
from decimal import Decimal

from .contracts import (Amount, Model, Scenario, ScenarioComparison, Source, SourceKind, Override)
from .engine import analyze


class ScenarioError(ValueError):
    pass


_ALLOWED: dict[str, dict[str, str]] = {
    "node": {
        "processing_seconds": "amount", "available_seconds": "amount",
        "batch_size": "positive_integer", "parallel_channels": "positive_integer",
        "units_per_finished": "positive_decimal",
    },
    "edge": {"transit_seconds": "amount", "waiting_seconds": "amount"},
    "resource": {"available_seconds": "amount"},
    "resource_use": {"work_seconds_per_output": "amount"},
}


def hash_model(model: Model) -> str:
    payload = json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_scenario(model: Model, scenario: Scenario) -> Model:
    if scenario.base_model_id != model.id:
        raise ScenarioError("scenario belongs to another model/version")
    # Изменения вносятся в отдельное представление; опубликованная версия остаётся прежней.
    raw = model.model_dump(mode="python")
    categories = {"node": "nodes", "edge": "edges", "resource": "resources", "resource_use": "resource_uses"}
    # Один параметр может быть изменён в сценарии только один раз.
    touched: set[tuple[str, str, str]] = set()
    for change in scenario.overrides:
        rule = _ALLOWED.get(change.target_type, {}).get(change.field)
        if rule is None:
            raise ScenarioError(f"field {change.field} cannot be overridden on {change.target_type}")
        identity = (change.target_type, change.target_id, change.field)
        if identity in touched:
            raise ScenarioError("duplicate scenario override")
        touched.add(identity)
        candidates = raw[categories[change.target_type]]
        # Назначение ресурса однозначно определяется парой «операция::ресурс».
        if change.target_type == "resource_use":
            matches = [x for x in candidates if f"{x['node_id']}::{x['resource_id']}" == change.target_id]
        else:
            matches = [x for x in candidates if x['id'] == change.target_id]
        if len(matches) != 1:
            raise ScenarioError(f"target {change.target_type}/{change.target_id} not found or ambiguous")
        if rule == "positive_integer":
            if change.new_value <= 0 or change.new_value != change.new_value.to_integral_value():
                raise ScenarioError(f"{change.field} must be a positive integer")
            new = int(change.new_value)
        elif rule == "positive_decimal":
            if change.new_value <= 0:
                raise ScenarioError(f"{change.field} must be positive")
            new = change.new_value
        else:
            if change.field == "processing_seconds" and change.new_value <= 0:
                raise ScenarioError("processing_seconds must be positive")
            new = Amount(value=change.new_value, unit="s", source=Source(
                kind=SourceKind.SYNTHETIC_SCENARIO, reference=f"scenario:{scenario.id}",
                confirmed=False, note=change.reason)).model_dump(mode="python")
        matches[0][change.field] = new
    return Model.model_validate(raw)


def compare_scenario(model: Model, scenario: Scenario, *,
                     takt_seconds: Amount | None = None, demand: int | None = None) -> ScenarioComparison:
    before = hash_model(model)
    changed = apply_scenario(model, scenario)
    base = analyze(model, takt_seconds=takt_seconds, demand=demand)
    projected = analyze(changed, takt_seconds=takt_seconds, demand=demand)
    base_cap = base.capacity.known_upper_bound if base.capacity.complete else None
    new_cap = projected.capacity.known_upper_bound if projected.capacity.complete else None
    delta = new_cap - base_cap if base_cap is not None and new_cap is not None else None
    if hash_model(model) != before:
        raise RuntimeError("scenario mutated the source model")
    return ScenarioComparison(scenario_id=scenario.id, base_model_id=model.id,
                              model_hash_before=before, model_hash_after=hash_model(changed),
                              baseline=base, projected=projected, capacity_delta=delta,
                              warnings=("continuous capacity bounds are not a short-shift production forecast",))