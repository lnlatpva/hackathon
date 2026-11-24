"""Компактные функции расчёта KPI без побочных эффектов; каждая метрика самостоятельно обрабатывает пропущенные входные данные."""
from __future__ import annotations
from decimal import Decimal
from typing import Iterable

from .contracts import Amount, Metric, ResultKind, ResultStatus, SourceKind


def D(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def _unavailable(code: str, *reason: str) -> Metric:
    return Metric(code=code, value=None, unit=None, status=ResultStatus.UNAVAILABLE,
                  kind=ResultKind.UNKNOWN, reasons=tuple(reason))


def _result(code: str, value: Decimal, unit: str, inputs: Iterable[Amount], *,
            force_estimate: bool = False, force_projected: bool = False,
            reasons: Iterable[str] = ()) -> Metric:
    inputs = tuple(inputs)
    sources = tuple(sorted({x.source.reference for x in inputs}))
    if force_projected or any(x.source.kind == SourceKind.SYNTHETIC_SCENARIO for x in inputs):
        kind = ResultKind.PROJECTED
    elif inputs and all(x.source.kind == SourceKind.MEASURED for x in inputs):
        kind = ResultKind.OBSERVED
    elif inputs and all(x.source.kind == SourceKind.NORMATIVE for x in inputs):
        kind = ResultKind.NORMATIVE
    else:
        kind = ResultKind.ESTIMATED
    estimated = force_estimate or kind != ResultKind.OBSERVED or not all(x.source.confirmed for x in inputs)
    if force_estimate and kind == ResultKind.OBSERVED:
        kind = ResultKind.ESTIMATED
    return Metric(code=code, value=value, unit=unit, sources=sources,
                  kind=kind, status=ResultStatus.ESTIMATED if estimated else ResultStatus.CALCULATED,
                  reasons=tuple(reasons))


def _units(code: str, entries: list[tuple[Amount | None, str]]) -> Metric | None:
    for obj, unit in entries:
        if obj is None:
            return _unavailable(code, f"missing {unit} input")
        if obj.unit != unit:
            return _unavailable(code, f"expected {unit}, received {obj.unit}")
    return None


def takt(available_seconds: Amount | None, demand: int | None) -> Metric:
    code = "takt_seconds_per_finished"
    m = _units(code, [(available_seconds, "s")]);
    if m: return m
    if demand is None or demand == 0: return _unavailable(code, "demand must be positive")
    if demand < 0: raise ValueError("negative demand")
    if available_seconds.value == 0: return _unavailable(code, "available time must be positive")
    return _result(code, available_seconds.value / D(demand), "s/finished", [available_seconds],
                   force_estimate=True, reasons=["demand has no attached source in this simple KPI contract"])


def effective_cycle(batch_time: Amount | None, batch_quantity: int | None) -> Metric:
    code = "effective_cycle_seconds_per_output"
    m = _units(code, [(batch_time, "s")]);
    if m: return m
    if batch_quantity is None or batch_quantity <= 0: return _unavailable(code, "positive batch size required")
    return _result(code, batch_time.value / D(batch_quantity), "s/output", [batch_time],
                   reasons=["not the first-unit latency; batch may only be released when complete"])


def actual_throughput(accepted: int | None, period: Amount | None) -> Metric:
    code = "throughput_accepted_per_second"
    m = _units(code, [(period, "s")]);
    if m: return m
    if accepted is None: return _unavailable(code, "missing accepted quantity")
    if accepted < 0: raise ValueError("negative accepted quantity")
    if period.value == 0: return _unavailable(code, "period must be positive")
    return _result(code, D(accepted) / period.value, "finished/s", [period],
                   force_estimate=True, reasons=["accepted quantity has no attached source in this simple KPI contract"])


def actual_utilization(busy: Amount | None, available: Amount | None) -> Metric:
    code = "actual_utilization_percent"
    m = _units(code, [(busy, "s"), (available, "s")]);
    if m: return m
    if available.value == 0: return _unavailable(code, "available time must be positive")
    if busy.value > available.value: raise ValueError("busy time exceeds available time")
    return _result(code, busy.value / available.value * 100, "%", [busy, available])


def downtime_rate(downtime: Amount | None, scheduled: Amount | None) -> Metric:
    code = "downtime_percent"
    m = _units(code, [(downtime, "s"), (scheduled, "s")]);
    if m: return m
    if scheduled.value == 0: return _unavailable(code, "scheduled time must be positive")
    if downtime.value > scheduled.value: raise ValueError("downtime exceeds schedule")
    return _result(code, downtime.value / scheduled.value * 100, "%", [downtime, scheduled])


def availability(downtime: Amount | None, scheduled: Amount | None) -> Metric:
    code = "availability_percent"
    m = _units(code, [(downtime, "s"), (scheduled, "s")]);
    if m: return m
    if scheduled.value == 0: return _unavailable(code, "scheduled time must be positive")
    if downtime.value > scheduled.value: raise ValueError("downtime exceeds schedule")
    return _result(code, (scheduled.value - downtime.value) / scheduled.value * 100, "%", [downtime, scheduled])


def quality(accepted: int | None, presented: int | None) -> Metric:
    code = "customer_quality_percent"
    if accepted is None or presented is None: return _unavailable(code, "missing presented or accepted count")
    if accepted < 0 or presented < 0 or accepted > presented: raise ValueError("invalid accepted/presented counts")
    if presented == 0: return _unavailable(code, "no units presented to customer")
    return _result(code, D(accepted) / D(presented) * 100, "%", [], force_estimate=True,
                   reasons=["counts must be supplied from the same period and inspection stage"])


def inventory_change(begin: Amount | None, end: Amount | None) -> Metric:
    code = "inventory_change_currency"
    if begin is None or end is None: return _unavailable(code, "missing beginning or ending inventory")
    if begin.unit != end.unit: return _unavailable(code, "inventory currency or unit mismatch")
    return _result(code, end.value - begin.value, begin.unit, [begin, end])


def unit_cost(total_cost: Amount | None, accepted: int | None) -> Metric:
    code = "cost_per_accepted_unit"
    if total_cost is None: return _unavailable(code, "missing full period cost")
    if accepted is None or accepted == 0: return _unavailable(code, "positive accepted quantity required")
    if accepted < 0: raise ValueError("negative accepted quantity")
    return _result(code, total_cost.value / D(accepted), f"{total_cost.unit}/finished", [total_cost],
                   reasons=["cost completeness and same-period scope must be validated by caller"])


def profit(revenue: Amount | None, total_cost: Amount | None) -> Metric:
    code = "profit"
    if revenue is None or total_cost is None: return _unavailable(code, "missing revenue or costs")
    if revenue.unit != total_cost.unit: return _unavailable(code, "currency mismatch")
    return _result(code, revenue.value - total_cost.value, revenue.unit, [revenue, total_cost])


def value_added_share(value_added: Amount | None, full_lead_time: Amount | None) -> Metric:
    code = "value_added_share_percent"
    m = _units(code, [(value_added, "s"), (full_lead_time, "s")]);
    if m: return m
    if full_lead_time.value == 0: return _unavailable(code, "lead time must be positive")
    if value_added.value > full_lead_time.value: raise ValueError("value-added time exceeds lead time")
    return _result(code, value_added.value / full_lead_time.value * 100, "%", [value_added, full_lead_time])


def compare_metrics(base: Metric, new: Metric) -> Metric:
    """Comparison only when periods, method versions and units are explicit and equal."""
    code = f"delta_{base.code}"
    if base.code != new.code:
        return _unavailable(code, "metric codes differ")
    if base.value is None or new.value is None:
        return _unavailable(code, "one of the compared values is unavailable")
    if base.unit != new.unit:
        return _unavailable(code, "unit mismatch")
    if base.period_key is None or new.period_key is None or base.period_key != new.period_key:
        return _unavailable(code, "incompatible or unspecified period")
    if base.method_version is None or new.method_version is None or base.method_version != new.method_version:
        return _unavailable(code, "incompatible or unspecified KPI methodology")
    return Metric(code=code, value=new.value - base.value, unit=base.unit,
                  status=ResultStatus.ESTIMATED, kind=ResultKind.PROJECTED,
                  reasons=("new minus baseline",),
                  sources=tuple(sorted(set(base.sources + new.sources))),
                  period_key=base.period_key, method_version=base.method_version)