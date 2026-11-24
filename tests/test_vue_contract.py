"""Backend/typed Vue frontend compatibility"""
from udt_calc import Amount, Model, Node, Source
from udt_calc.graph import validate_graph


def test_manual_frontend_source_is_not_a_measurement():
    src = Source.model_validate({
        "kind": "user_input", "reference": "user:frontend-input", "confirmed": False,
    })
    assert src.kind.value == "user_input"
    assert src.confirmed is False


def test_empty_editor_model_is_valid_draft_contract():
    model = Model.model_validate({
        "id": "draft-1", "nodes": [], "edges": [],
        "resources": [], "resource_uses": [],
        "target_id": None, "assume_independent_resources": False,
    })
    assert model.nodes == ()
    assert validate_graph(model).valid is True


def test_frontend_node_time_requires_explicit_source():
    amount = Amount.model_validate({
        "value": "171", "unit": "s",
        "source": {"kind": "user_input", "reference": "user:frontend", "confirmed": False},
    })
    node = Node(id="WS8", name="РМ 8", kind="operation", processing_seconds=amount)
    assert node.processing_seconds is not None
    assert node.processing_seconds.value == 171
    assert node.processing_seconds.source.confirmed is False