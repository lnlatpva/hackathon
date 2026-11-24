from decimal import Decimal
import pytest
from udt_calc import Amount, Source, SourceKind, Model, Node, Edge, ResourcePool, ResourceUse


@pytest.fixture
def amount():
    def make(value, unit="s", kind=SourceKind.SYNTHETIC_TEST, reference="test:synthetic", confirmed=True):
        return Amount(value=Decimal(str(value)), unit=unit,
                      source=Source(kind=kind, reference=reference, confirmed=confirmed))
    return make


@pytest.fixture
def parallel_model(amount):
    # SYNTHETIC_TEST_FIXTURE: two independent branches feed the final assembly C.
    a = Node(id="A", name="branch A", processing_seconds=amount(20), batch_size=1,
             units_per_finished=Decimal(1), parallel_channels=1, available_seconds=amount(1200))
    b = Node(id="B", name="branch B", processing_seconds=amount(30), batch_size=1,
             units_per_finished=Decimal(1), parallel_channels=1, available_seconds=amount(1200))
    c = Node(id="C", name="join", processing_seconds=amount(10), batch_size=1,
             units_per_finished=Decimal(1), parallel_channels=1, available_seconds=amount(1200))
    edges = [Edge(id="A-C", source_id="A", target_id="C", verification="confirmed",
                  transit_seconds=amount(0), waiting_seconds=amount(0)),
             Edge(id="B-C", source_id="B", target_id="C", verification="confirmed",
                  transit_seconds=amount(0), waiting_seconds=amount(0))]
    return Model(id="synthetic-parallel-v1", nodes=[a,b,c], edges=edges, target_id="C",
                 assume_independent_resources=True)