"""Небольшой адаптер: сохранить независимо протестированное ядро udt-calc без изменений."""
from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from udt_calc import (
    Model, Source, SourceKind, Amount, Metric, ResultKind, ResultStatus, Override,
    Scenario as CoreScenario, analyze, apply_scenario,
    takt, actual_throughput, actual_utilization, quality,
    downtime_rate, availability, inventory_change, unit_cost, profit,
)
from udt_calc.metrics import _unavailable
from udt_calc.scenarios import hash_model
from udt_calc.graph import contributing_nodes

ALGORITHM_VERSION = 'udt-calc/0.6.1'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Count(Strict):
    value: int = Field(ge=0)
    source: Source


class Facts(Strict):
    available_seconds: Amount | None = None
    demand: Count | None = None
    accepted: Count | None = None
    presented: Count | None = None
    period_seconds: Amount | None = None
    busy_seconds: Amount | None = None
    resource_available_seconds: Amount | None = None
    downtime_seconds: Amount | None = None
    scheduled_seconds: Amount | None = None
    inventory_begin: Amount | None = None
    inventory_end: Amount | None = None
    total_cost: Amount | None = None
    revenue: Amount | None = None

    @model_validator(mode='after')
    def check_consistency(self) -> 'Facts':
        # Даже прямой вызов API не должен принимать несовместимые замеры.
        time_fields = (
            'available_seconds', 'period_seconds', 'busy_seconds',
            'resource_available_seconds', 'downtime_seconds', 'scheduled_seconds',
        )
        for name in time_fields:
            amount = getattr(self, name)
            if amount is not None and amount.unit != 's':
                raise ValueError(f'{name}: ожидается единица измерения s (секунды)')
        if self.accepted is not None and self.presented is not None:
            if self.accepted.value > self.presented.value:
                raise ValueError('Принятых изделий не может быть больше предъявленных')
        if self.busy_seconds is not None and self.resource_available_seconds is not None:
            if self.busy_seconds.value > self.resource_available_seconds.value:
                raise ValueError('Занятость ресурса не может превышать его доступное время')
        if self.downtime_seconds is not None and self.scheduled_seconds is not None:
            if self.downtime_seconds.value > self.scheduled_seconds.value:
                raise ValueError('Простой не может превышать плановое время')
        for left, right in (('inventory_begin', 'inventory_end'), ('revenue', 'total_cost')):
            a, b = getattr(self, left), getattr(self, right)
            if a is not None and b is not None and a.unit != b.unit:
                raise ValueError(f'{left} и {right}: единицы измерения должны совпадать')
        return self


class CalculationRequest(Strict):
    facts: Facts = Field(default_factory=Facts)
    takt_seconds: Amount | None = None
    optimistic_lead_time: bool = False
    period_key: str | None = Field(default=None, max_length=120)

    @field_validator('takt_seconds')
    @classmethod
    def validate_takt(cls, value: Amount | None) -> Amount | None:
        if value is not None and (value.unit != 's' or value.value <= 0):
            raise ValueError('Заданный такт должен быть положительным числом секунд')
        return value

    @field_validator('period_key')
    @classmethod
    def normalize_period(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Ключ периода не может состоять из пробелов')
        return cleaned


def node_cost_metric(model: Model, costs: dict[str, Amount], *, projected: bool) -> Metric:
    """Estimated currency per finished product, only with full sourced node costs."""
    relevant = contributing_nodes(model)
    nodes = [n for n in model.nodes if n.id in relevant and n.kind in ('operation', 'inspection')]
    missing = [n.id for n in nodes if n.id not in costs or n.units_per_finished is None]
    currencies = {costs[n.id].unit.split('/')[0] for n in nodes if n.id in costs}
    if not nodes or missing or len(currencies) != 1:
        why = f'missing costs or material coefficients: {missing}' if missing else 'no complete comparable node costs'
        return _unavailable('cost_per_finished_from_nodes', why)
    total = sum((costs[n.id].value * n.units_per_finished for n in nodes), Decimal(0))
    return Metric(code='cost_per_finished_from_nodes', value=total,
        unit=f'{next(iter(currencies))}/finished', status=ResultStatus.ESTIMATED,
        kind=ResultKind.PROJECTED if projected else ResultKind.ESTIMATED,
        reasons=('sum of sourced per-output costs × number of outputs required per finished unit',),
        sources=tuple(sorted({costs[n.id].source.reference for n in nodes})))


def calculate(model: Model, request: CalculationRequest, overrides: list[Override] | None = None,
              scenario_id: str | None = None, *, node_costs: dict[str, Amount] | None = None,
              cost_overrides: dict[str, Amount] | None = None) -> dict:
    """Produces stored KPI statuses, graph analysis, and optional baseline comparison."""
    f = request.facts
    accepted = f.accepted.value if f.accepted is not None else None
    presented = f.presented.value if f.presented is not None else None
    demand = f.demand.value if f.demand is not None else None
    derived_takt = takt(f.available_seconds, demand)
    effective_takt = request.takt_seconds
    if effective_takt is None and derived_takt.value is not None:
        effective_takt = Amount(value=derived_takt.value, unit='s', source=Source(
            kind=SourceKind.DERIVED, reference='calc:takt', confirmed=False,
            note='Derived from sourced available time and demand'))

    metrics = {
        'takt_seconds_per_finished': derived_takt,
        'throughput_accepted_per_second': actual_throughput(accepted, f.period_seconds),
        'actual_utilization_percent': actual_utilization(f.busy_seconds, f.resource_available_seconds),
        'downtime_percent': downtime_rate(f.downtime_seconds, f.scheduled_seconds),
        'availability_percent': availability(f.downtime_seconds, f.scheduled_seconds),
        'customer_quality_percent': quality(accepted, presented),
        'inventory_change_currency': inventory_change(f.inventory_begin, f.inventory_end),
        'cost_per_accepted_unit': unit_cost(f.total_cost, accepted),
        'profit': profit(f.revenue, f.total_cost),
    }
    if request.takt_seconds is not None:
        metrics['input_takt_seconds'] = (
            Metric(code='input_takt_seconds', value=request.takt_seconds.value, unit='s',
                   status=ResultStatus.ESTIMATED, kind=ResultKind.ESTIMATED,
                   reasons=('user-provided takt',), sources=(request.takt_seconds.source.reference,))
            if request.takt_seconds.unit == 's'
            else _unavailable('input_takt_seconds', 'takt unit must be s')
        )

    # Сначала рассчитываем базовую модель; сценарий применяется только к копии.
    before = analyze(model, takt_seconds=effective_takt, demand=demand,
                     optimistic_lead_time=request.optimistic_lead_time)
    active_model = model
    if overrides is not None:
        active_model = apply_scenario(model, CoreScenario(
            id=scenario_id or 'scenario', base_model_id=model.id, overrides=tuple(overrides)))
    analysis = analyze(active_model, takt_seconds=effective_takt, demand=demand,
                       optimistic_lead_time=request.optimistic_lead_time)
    
    # Стоимость задаётся отдельными исходными данными, не выводится из длительности операции.
    baseline_cost = node_cost_metric(model, node_costs or {}, projected=False)
    costs = dict(node_costs or {})
    costs.update(cost_overrides or {})
    projected_cost = node_cost_metric(active_model, costs, projected=overrides is not None)
    metrics['cost_per_finished_from_nodes'] = projected_cost
    metrics['first_unit_lead_seconds'] = analysis.lead_time.metric
    cap = analysis.capacity
    metrics['capacity_upper_bound'] = (
        Metric(code='capacity_upper_bound', value=cap.known_upper_bound,
               unit='finished/period', status=ResultStatus.ESTIMATED,
               kind=ResultKind.PROJECTED if overrides is not None else ResultKind.ESTIMATED,
               reasons=cap.assumptions,
               sources=tuple(sorted({s for c in cap.constraints for s in c.sources})))
        if cap.complete and cap.known_upper_bound is not None
        else _unavailable('capacity_upper_bound', *(cap.missing or ('insufficient input data',)))
    )

    # Сохраняем идентификатор периода и версию метода для сопоставимых KPI.
    if request.period_key:
        metrics = {k: m.model_copy(update={'period_key': request.period_key,
                   'method_version': ALGORITHM_VERSION}) for k, m in metrics.items()}
    base_cap = before.capacity.known_upper_bound if before.capacity.complete else None
    new_cap = cap.known_upper_bound if cap.complete else None
    return {
        'model_hash': hash_model(active_model),
        'metrics': {k: v.model_dump(mode='json') for k, v in metrics.items()},
        'analysis': analysis.model_dump(mode='json'),
        'baseline_analysis': before.model_dump(mode='json') if overrides is not None else None,
        'capacity_delta': str(new_cap - base_cap)
            if overrides is not None and base_cap is not None and new_cap is not None else None,
        'baseline_node_cost': baseline_cost.model_dump(mode='json') if overrides is not None else None,
        'node_cost_delta': str(projected_cost.value - baseline_cost.value)
            if overrides is not None and baseline_cost.value is not None
               and projected_cost.value is not None and baseline_cost.unit == projected_cost.unit else None,
    }