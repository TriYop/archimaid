from archimaid.adapters.web import resources as r
from archimaid.adapters.web.render import Lookups, present_rows


def test_ref_choices_follow_catalog_order(services):
    groups = Lookups(services).choices(r.APPLICATION.field("integrity_level"))
    assert len(groups) == 1 and groups[0][0] is None
    assert [o.value for o in groups[0][1]] == ["EXTREME", "SERIOUS", "MODERATE", "LOW"]


def test_application_choices_are_grouped_by_team_and_sorted(services):
    team_b = services.teams.create({"name": "B team"})
    team_a = services.teams.create({"name": "A team"})
    services.applications.create({"team_id": team_b.id, "name": "Zeta"})
    services.applications.create({"team_id": team_a.id, "name": "Beta"})
    services.applications.create({"team_id": team_a.id, "name": "Alpha"})
    groups = Lookups(services).choices(r.DATA_FLOW.field("source_application_id"))
    assert [(g, [o.label for o in opts]) for g, opts in groups] == [
        ("A team", ["Alpha", "Beta"]),
        ("B team", ["Zeta"]),
    ]


def test_data_type_choices_are_labelled_with_their_application(services):
    team = services.teams.create({"name": "T"})
    app = services.applications.create({"team_id": team.id, "name": "Billing"})
    services.data_types.create({"application_id": app.id, "name": "Invoice"})
    groups = Lookups(services).choices(r.DATA_FLOW.field("data_type_id"))
    assert groups[0][0] == "Billing"
    assert groups[0][1][0].label == "Billing › Invoice"


def test_persona_choices_are_sorted_by_name(services):
    services.personas.create({"name": "zed"})
    services.personas.create({"name": "Alice"})
    groups = Lookups(services).choices(r.FUNCTION.field("persona_id"))
    assert [o.label for o in groups[0][1]] == ["Alice", "zed"]


def test_display_formats(services):
    lookups = Lookups(services)
    level = r.APPLICATION.field("availability_level")
    assert lookups.display(level, {"availability_level": "SERIOUS"}) == "Serious"
    assert lookups.display(level, {"availability_level": None}) == "—"
    assert lookups.display(r.TEAM.field("name"), {"name": ""}) == "—"
    rpo = r.APPLICATION.field("rpo_rto")
    assert lookups.display(rpo, {"rpo": 4, "rto": 0}) == "4 h / 0 h"
    assert lookups.display(rpo, {"rpo": None, "rto": None}) == "—"


def test_present_rows_adds_derived_values_for_applications(services):
    team = services.teams.create({"name": "T"})
    app = services.applications.create(
        {"team_id": team.id, "name": "A", "availability_level": "SERIOUS"}
    )
    [row] = present_rows(services.applications, [app])
    assert (row["rpo"], row["rto"]) == (4, 0) and row["id"] == app.id
    [team_row] = present_rows(services.teams, [team])
    assert team_row["name"] == "T"
