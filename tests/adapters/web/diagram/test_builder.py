from uuid import uuid4

import pytest

from archimaid.adapters.web.diagram import build_diagram
from archimaid.application.services import build_services
from archimaid.domain.errors import NotFound
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def services():
    return build_services(fake_repositories(), default_catalog())


class World:
    """Small helper to build a scenario through the real services."""

    def __init__(self, services):
        self.s = services
        self.team = services.teams.create({"name": "Team"})

    def app(self, name):
        return self.s.applications.create({"team_id": self.team.id, "name": name})

    def dtype(self, app, name):
        return self.s.data_types.create({"application_id": app.id, "name": name})

    def flow(self, source, target, dtype, **extra):
        return self.s.data_flows.create(
            {
                "source_application_id": source.id,
                "target_application_id": target.id,
                "data_type_id": dtype.id,
                **extra,
            }
        )

    def function(self, app, name, persona=None):
        data = {"application_id": app.id, "name": name}
        if persona is not None:
            data["persona_id"] = persona.id
        return self.s.functions.create(data)


@pytest.fixture
def world(services):
    return World(services)


def test_unknown_application_is_not_found(services):
    with pytest.raises(NotFound):
        build_diagram(services, uuid4())


def test_an_application_with_nothing_gives_an_empty_model(services, world):
    app = world.app("Lonely")
    model = build_diagram(services, app.id)
    assert model.application == "Lonely"
    assert model.functions == () and model.targets == () and model.sources == ()
    assert model.self_flows == 0


def test_functions_are_sorted_and_carry_their_persona_name(services, world):
    app = world.app("Billing")
    accountant = services.personas.create({"name": "Accountant"})
    world.function(app, "send reminder", accountant)
    world.function(app, "Create invoice", accountant)
    world.function(app, "Archive")
    model = build_diagram(services, app.id)
    assert [(f.name, f.persona) for f in model.functions] == [
        ("Archive", None),
        ("Create invoice", "Accountant"),
        ("send reminder", "Accountant"),
    ]


def test_outgoing_flows_are_targets_and_incoming_flows_are_sources(services, world):
    billing, ledger, crm = world.app("Billing"), world.app("Ledger"), world.app("CRM")
    invoice = world.dtype(billing, "Invoice")
    customer = world.dtype(crm, "Customer")
    world.flow(billing, ledger, invoice, usage_mode="SOURCE", usage_explanation="nightly")
    world.flow(crm, billing, customer)
    model = build_diagram(services, billing.id)
    assert [n.name for n in model.targets] == ["Ledger"]
    assert [n.name for n in model.sources] == ["CRM"]
    flow = model.targets[0].flows[0]
    assert (flow.data_type, flow.usage_mode, flow.explanation) == ("Invoice", "Source", "nightly")
    incoming = model.sources[0].flows[0]
    assert (incoming.data_type, incoming.usage_mode, incoming.explanation) == (
        "Customer",
        None,
        None,
    )


def test_flows_to_the_same_application_are_grouped_and_sorted(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    for name in ("payment", "Invoice"):
        world.flow(billing, ledger, world.dtype(billing, name))
    model = build_diagram(services, billing.id)
    assert len(model.targets) == 1
    assert [f.data_type for f in model.targets[0].flows] == ["Invoice", "payment"]


def test_neighbours_are_sorted_case_insensitively_and_equal_names_stay_separate(services, world):
    billing = world.app("Billing")
    dtype = world.dtype(billing, "T")
    for name in ("zeta", "Alpha", "Alpha"):
        world.flow(billing, world.app(name), dtype)
    model = build_diagram(services, billing.id)
    assert [n.name for n in model.targets] == ["Alpha", "Alpha", "zeta"]


def test_a_neighbour_in_both_directions_appears_in_both_lists(services, world):
    # Review Focus test (2)
    a, b = world.app("A"), world.app("B")
    world.flow(a, b, world.dtype(a, "x"))
    world.flow(b, a, world.dtype(b, "y"))
    model = build_diagram(services, a.id)
    assert [n.name for n in model.targets] == ["B"] and [n.name for n in model.sources] == ["B"]


def test_self_flows_are_counted_and_not_drawn(services, world):
    # Review Focus test (2)
    a, b = world.app("A"), world.app("B")
    dtype = world.dtype(a, "x")
    world.flow(a, a, dtype)
    world.flow(a, a, dtype)
    world.flow(a, b, dtype)
    model = build_diagram(services, a.id)
    assert model.self_flows == 2
    assert [n.name for n in model.targets] == ["B"] and model.sources == ()


def test_only_self_flows_leave_empty_rows_and_a_count(services, world):
    a = world.app("A")
    world.flow(a, a, world.dtype(a, "x"))
    model = build_diagram(services, a.id)
    assert model.targets == () and model.sources == () and model.self_flows == 1


def test_the_usage_mode_shows_its_catalog_label_not_its_code(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    flow = world.flow(billing, ledger, world.dtype(billing, "T"), usage_mode="PROXY")
    model = build_diagram(services, billing.id)
    assert flow.usage_mode == "PROXY"
    assert model.targets[0].flows[0].usage_mode == "Proxy"


def test_flows_of_other_applications_are_not_included(services, world):
    a, b, c = world.app("A"), world.app("B"), world.app("C")
    world.flow(b, c, world.dtype(b, "x"))
    model = build_diagram(services, a.id)
    assert model.targets == () and model.sources == ()


def test_function_index_points_at_the_current_applications_function(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    dtype = world.dtype(billing, "x")
    world.function(billing, "send")
    create = world.function(billing, "Create")  # sorts before "send"
    world.flow(billing, ledger, dtype, source_function_id=create.id)
    plain = world.flow(ledger, billing, dtype)
    model = build_diagram(services, billing.id)
    assert plain.source_function_id is None
    assert model.targets[0].flows[0].function_index == 0
    assert model.sources[0].flows[0].function_index is None


def test_incoming_flow_uses_the_target_function(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    world.function(billing, "a")
    receive = world.function(billing, "b")
    world.flow(ledger, billing, world.dtype(ledger, "x"), target_function_id=receive.id)
    model = build_diagram(services, billing.id)
    assert model.sources[0].flows[0].function_index == 1


def test_functions_of_third_party_applications_stay_hidden_and_the_flow_goes_to_the_parent(
    services, world
):
    # Review Focus test (5)
    billing, ledger = world.app("Billing"), world.app("Ledger")
    post = world.function(ledger, "Post entry")
    world.flow(billing, ledger, world.dtype(billing, "x"), target_function_id=post.id)
    model = build_diagram(services, billing.id)
    assert [n.name for n in model.targets] == ["Ledger"]
    assert model.targets[0].flows[0].function_index is None
    assert "Post entry" not in repr(model)
    other_side = build_diagram(services, ledger.id)
    assert [n.name for n in other_side.sources] == ["Billing"]
    assert other_side.sources[0].flows[0].function_index == 0


def test_function_to_function_flow_inside_one_application_is_counted_not_drawn(services, world):
    # Review Focus test (5)
    a = world.app("A")
    send, receive = world.function(a, "send"), world.function(a, "receive")
    world.flow(
        a, a, world.dtype(a, "x"), source_function_id=send.id, target_function_id=receive.id
    )
    model = build_diagram(services, a.id)
    assert model.self_flows == 1
    assert model.targets == () and model.sources == ()


def test_a_persona_shared_by_two_functions_is_named_on_both(services, world):
    app = world.app("A")
    pat = services.personas.create({"name": "Pat"})
    world.function(app, "f1", pat)
    world.function(app, "f2", pat)
    model = build_diagram(services, app.id)
    assert [f.persona for f in model.functions] == ["Pat", "Pat"]
