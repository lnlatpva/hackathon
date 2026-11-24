"""Строго типизированные контракты. 
Отсутствующие показания [данных/метрик] передаются как None, а не как неявный ноль
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceKind(str, Enum):
    MEASURED = "measured"
    NORMATIVE = "normative"
    SYNTHETIC_TEST = "synthetic_test_fixture"
    SYNTHETIC_SCENARIO = "synthetic_scenario"
    DOCUMENT = "document"
    DERIVED = "derived"
    USER_INPUT = "user_input"  # provenance for manually entered, unverified values


class ResultStatus(str, Enum):
    CALCULATED = "calculated"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class ResultKind(str, Enum):
    OBSERVED = "observed"
    NORMATIVE = "normative"
    PROJECTED = "projected"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class Source(FrozenModel):
    kind: SourceKind
    reference: str = Field(min_length=1, max_length=500)
    confirmed: bool = True
    note: str | None = None

    @field_validator('reference')
    @classmethod
    def valid_reference(cls, value: str) -> str:
        # Происхождение данных обязательно: пробелы не считаются указанием источника.
        normalized = value.strip()
        if not normalized:
            raise ValueError('Укажите источник исходного значения')
        return normalized


class Amount(FrozenModel):
    value: Decimal = Field(ge=0)
    unit: str = Field(min_length=1, max_length=64)
    source: Source

    @field_validator('unit')
    @classmethod
    def nonempty_unit(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('Укажите единицу измерения')
        return normalized

    @field_validator("value")
    @classmethod
    def finite(cls, v: Decimal) -> Decimal:
        if not v.is_finite():
            raise ValueError("measurement must be finite")
        return v


class RawStandard(FrozenModel):
    value: Decimal = Field(ge=0)
    unit: str | None = None  # None означает, что в первоисточнике единица не задана.
    source: Source

    @field_validator('value')
    @classmethod
    def finite_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError('Норматив должен быть конечным числом')
        return value


class Node(FrozenModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["operation", "inspection", "transport", "storage", "source", "sink"] = "operation"
    processing_seconds: Amount | None = None  # time for an entire batch; also first batch latency
    batch_size: int | None = Field(default=None, gt=0)
    units_per_finished: Decimal | None = Field(default=None, gt=0)
    parallel_channels: int | None = Field(default=None, gt=0)
    available_seconds: Amount | None = None  # per channel, unless modeled as a shared ResourcePool
    output_item: str | None = None

    @model_validator(mode='after')
    def check_time_units(self) -> 'Node':
        # Время обработки и фонд времени нормируем в секундах, не смешивая минуты/часы.
        for name in ('processing_seconds', 'available_seconds'):
            amount = getattr(self, name)
            if amount is not None and amount.unit != 's':
                raise ValueError(f'{name}: ожидаются секунды (s)')
        return self

    @field_validator("units_per_finished")
    @classmethod
    def finite_ratio(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and not v.is_finite():
            raise ValueError("ratio must be finite")
        return v


class Edge(FrozenModel):
    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    kind: Literal["material", "information"] = "material"
    item_id: str | None = None
    transit_seconds: Amount | None = None
    waiting_seconds: Amount | None = None
    verification: Literal["confirmed", "inferred", "unresolved"] = "unresolved"
    source: Source | None = None

    @model_validator(mode='after')
    def check_time_units(self) -> 'Edge':
        for name in ('transit_seconds', 'waiting_seconds'):
            amount = getattr(self, name)
            if amount is not None and amount.unit != 's':
                raise ValueError(f'{name}: ожидаются секунды (s)')
        return self


class ResourcePool(FrozenModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    available_seconds: Amount | None = None  # Общий фонд времени взаимозаменяемых ресурсов.

    @field_validator('available_seconds')
    @classmethod
    def check_time_unit(cls, value: Amount | None) -> Amount | None:
        if value is not None and value.unit != 's':
            raise ValueError('Фонд ресурса должен задаваться в секундах (s)')
        return value


class ResourceUse(FrozenModel):
    node_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    work_seconds_per_output: Amount | None = None

    @field_validator('work_seconds_per_output')
    @classmethod
    def check_work_unit(cls, value: Amount | None) -> Amount | None:
        if value is not None and value.unit != 's':
            raise ValueError('Занятость ресурса должна задаваться в секундах (s)')
        return value


class Model(FrozenModel):
    id: str = Field(min_length=1)
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    resources: tuple[ResourcePool, ...] = ()
    resource_uses: tuple[ResourceUse, ...] = ()
    target_id: str | None = None
    assume_independent_resources: bool = False


class Metric(FrozenModel):
    code: str
    value: Decimal | None
    unit: str | None
    status: ResultStatus
    kind: ResultKind
    reasons: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    period_key: str | None = None
    method_version: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> "Metric":
        if self.status == ResultStatus.UNAVAILABLE:
            if self.value is not None or not self.reasons:
                raise ValueError("unavailable metric requires NULL value and reason")
        elif self.value is None or self.unit is None:
            raise ValueError("available metric requires value and unit")
        return self


class Issue(FrozenModel):
    code: str
    message: str
    node_id: str | None = None
    blocking: bool = False


class GraphCheck(FrozenModel):
    valid: bool
    issues: tuple[Issue, ...]
    order: tuple[str, ...] = ()


class Constraint(FrozenModel):
    owner_type: Literal["operation", "resource"]
    owner_id: str
    finished_equivalent_capacity: Decimal  # continuous upper bound, NOT actual finished units
    sources: tuple[str, ...] = ()


class CapacityReport(FrozenModel):
    status: ResultStatus
    known_upper_bound: Decimal | None
    complete: bool
    constraints: tuple[Constraint, ...]
    missing: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()


class PathReport(FrozenModel):
    metric: Metric
    critical_nodes: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()


class Bottleneck(FrozenModel):
    code: str
    owner_type: Literal["operation", "resource"]
    owner_id: str
    explanation: str
    calculated_value: Decimal
    threshold_value: Decimal | None = None


class Analysis(FrozenModel):
    graph: GraphCheck
    capacity: CapacityReport
    lead_time: PathReport
    bottlenecks: tuple[Bottleneck, ...]


class Override(FrozenModel):
    target_type: Literal["node", "edge", "resource", "resource_use"]
    target_id: str  # for resource_use: "node_id::resource_id"
    field: Literal["processing_seconds", "batch_size", "units_per_finished", "parallel_channels", "available_seconds", "transit_seconds", "waiting_seconds", "work_seconds_per_output"]
    new_value: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('Укажите обоснование изменения')
        return normalized

    @field_validator("new_value")
    @classmethod
    def finite_override(cls, v: Decimal) -> Decimal:
        if not v.is_finite():
            raise ValueError("override must be finite")
        return v


class Scenario(FrozenModel):
    id: str = Field(min_length=1)
    base_model_id: str = Field(min_length=1)
    overrides: tuple[Override, ...]


class ScenarioComparison(FrozenModel):
    scenario_id: str
    base_model_id: str
    model_hash_before: str
    model_hash_after: str
    baseline: Analysis
    projected: Analysis
    capacity_delta: Decimal | None
    warnings: tuple[str, ...] = ()