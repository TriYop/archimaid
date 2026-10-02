from uuid import uuid4


def make_team(services, name="Payments"):
    return services.teams.create({"name": name})


def make_app(services, team, **extra):
    return services.applications.create({"team_id": team.id, "name": "Billing", **extra})


# ------------------------------------------------------------------ team page


def test_team_page_shows_header_members_and_applications(client, services):
    team = make_team(services)
    member = services.members.create({"team_id": team.id, "user_id": "u1", "name": "Ann"})
    app = make_app(services, team, availability_level="SERIOUS", shortname="bil")
    html = client.get(f"/ui/teams/{team.id}").text
    assert "<html" in html
    assert 'href="/ui/teams"' in html
    assert f'<tr id="team-{team.id}"' in html
    assert f'<tr id="member-{member.id}"' in html and "Ann" in html
    assert f'<tr id="application-{app.id}"' in html
    assert f'href="/ui/applications/{app.id}"' in html
    assert "bil" in html and "4 h / 0 h" in html
    assert f'hx-post="/ui/teams/{team.id}/members?table=members"' in html
    assert 'hx-post="/ui/applications?table=applications"' in html
    assert f'name="team_id" value="{team.id}"' in html


def test_the_team_header_has_no_add_form(client, services):
    team = make_team(services)
    html = client.get(f"/ui/teams/{team.id}").text
    assert 'hx-post="/ui/teams?table=team"' not in html


def test_application_add_form_offers_levels_in_rank_order(client, services):
    team = make_team(services)
    html = client.get(f"/ui/teams/{team.id}").text
    assert html.index('<option value="EXTREME"') < html.index('<option value="LOW"')
    assert '<option value="SERIOUS"' in html


def test_missing_team_page_is_a_404_page(client):
    response = client.get(f"/ui/teams/{uuid4()}")
    assert response.status_code == 404 and "<html" in response.text


# ------------------------------------------------------------------ members


def test_add_member_under_a_team(client, services):
    team = make_team(services)
    response = client.post(
        f"/ui/teams/{team.id}/members?table=members", data={"user_id": "u1", "name": "Ann"}
    )
    assert response.status_code == 201
    member = services.members.list()[0]
    assert member.team_id == team.id
    assert f'<tr id="member-{member.id}"' in response.text
    assert f'hx-get="/ui/teams/{team.id}/members/{member.id}/edit"' in response.text


def test_member_blank_user_id_is_422(client, services):
    team = make_team(services)
    response = client.post(
        f"/ui/teams/{team.id}/members?table=members", data={"user_id": " ", "name": "Ann"}
    )
    assert response.status_code == 422
    assert "user_id must not be blank" in response.text
    assert services.members.list() == []


def test_member_save_and_delete(client, services):
    team = make_team(services)
    member = services.members.create({"team_id": team.id, "user_id": "u1", "name": "Ann"})
    base = f"/ui/teams/{team.id}/members/{member.id}"
    saved = client.put(base, data={"user_id": "u2", "name": "Ann B"})
    assert saved.status_code == 200
    updated = services.members.get(member.id)
    assert (updated.user_id, updated.name, updated.team_id) == ("u2", "Ann B", team.id)
    assert client.delete(base).status_code == 200
    assert services.members.list() == []


def test_member_through_the_wrong_team_is_a_404_flash(client, services, hx):
    # Review Focus test (2)
    team_a, team_b = make_team(services, "A"), make_team(services, "B")
    member = services.members.create({"team_id": team_a.id, "user_id": "u1", "name": "Ann"})
    wrong = f"/ui/teams/{team_b.id}/members/{member.id}"
    for method, url in (("get", wrong + "/row"), ("get", wrong + "/edit"), ("delete", wrong)):
        response = getattr(client, method)(url, headers=hx)
        assert response.status_code == 404, url
        assert response.headers["HX-Retarget"] == "#flash"
    assert client.put(wrong, data={"user_id": "x", "name": "x"}, headers=hx).status_code == 404
    assert services.members.get(member.id).user_id == "u1"


def test_member_under_a_missing_team_is_a_404_flash(client, hx):
    response = client.post(
        f"/ui/teams/{uuid4()}/members?table=members", data={"user_id": "u", "name": "n"}, headers=hx
    )
    assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash"


# ------------------------------------------------------------------ applications


def test_add_application_from_the_team_page(client, services):
    team = make_team(services)
    response = client.post(
        "/ui/applications?table=applications",
        data={
            "team_id": str(team.id),
            "name": "Billing",
            "shortname": "bil",
            "availability_level": "SERIOUS",
        },
    )
    assert response.status_code == 201
    app = services.applications.list()[0]
    assert app.team_id == team.id and app.availability_level == "SERIOUS"
    assert f'href="/ui/applications/{app.id}"' in response.text
    assert "4 h / 0 h" in response.text


def test_add_application_without_or_with_an_unknown_team_is_422(client, services):
    # Review Focus test (4)
    missing = client.post("/ui/applications?table=applications", data={"name": "A"})
    assert missing.status_code == 422 and "team_id" in missing.text
    ghost = client.post(
        "/ui/applications?table=applications", data={"team_id": str(uuid4()), "name": "A"}
    )
    assert ghost.status_code == 422 and "does not exist" in ghost.text
    bad = client.post(
        "/ui/applications?table=applications", data={"team_id": "nope", "name": "A"}
    )
    assert bad.status_code == 422
    assert services.applications.list() == []


def test_add_application_with_an_unknown_level_is_422(client, services):
    team = make_team(services)
    response = client.post(
        "/ui/applications?table=applications",
        data={"team_id": str(team.id), "name": "A", "availability_level": "NOPE"},
    )
    assert response.status_code == 422
    assert "is not a valid availability_level" in response.text


def test_editing_a_row_does_not_wipe_the_fields_it_hides(client, services):
    # Review Focus test (3)
    team = make_team(services)
    app = make_app(services, team, description="keep me", golden_app_id="G1", auid="A1")
    response = client.put(
        f"/ui/applications/{app.id}",
        data={
            "name": "Renamed",
            "shortname": "",
            "confidentiality_level": "",
            "integrity_level": "LOW",
            "availability_level": "SERIOUS",
            "traceability_level": "",
        },
    )
    assert response.status_code == 200
    saved = services.applications.get(app.id)
    assert (saved.name, saved.shortname, saved.integrity_level) == ("Renamed", None, "LOW")
    assert saved.description == "keep me"
    assert (saved.golden_app_id, saved.auid, saved.team_id) == ("G1", "A1", team.id)
    assert "4 h / 0 h" in response.text


def test_application_edit_row_preselects_the_current_levels(client, services):
    team = make_team(services)
    app = make_app(services, team, integrity_level="MODERATE")
    html = client.get(f"/ui/applications/{app.id}/edit").text
    assert '<option value="MODERATE" selected>' in html
    assert "4 h" not in html and "—" in html  # the RPO/RTO cell is shown read-only


def test_application_save_with_a_blank_name_is_422(client, services):
    team = make_team(services)
    app = make_app(services, team)
    response = client.put(f"/ui/applications/{app.id}", data={"name": " "})
    assert response.status_code == 422 and "name must not be blank" in response.text
    assert services.applications.get(app.id).name == "Billing"


# ------------------------------------------------------------------ delete from own page


def test_deleting_an_application_from_its_own_page_redirects_to_its_team(client, services):
    # Review Focus test (6)
    team = make_team(services)
    app = make_app(services, team)
    own_page = f"http://testserver/ui/applications/{app.id}?tab=details"
    response = client.delete(f"/ui/applications/{app.id}", headers={"HX-Current-URL": own_page})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == f"/ui/teams/{team.id}"
    assert services.applications.list() == []


def test_deleting_an_application_from_the_team_page_just_removes_the_row(client, services):
    team = make_team(services)
    app = make_app(services, team)
    team_page = f"http://testserver/ui/teams/{team.id}"
    response = client.delete(f"/ui/applications/{app.id}", headers={"HX-Current-URL": team_page})
    assert response.status_code == 200 and response.text == ""
    assert "HX-Redirect" not in response.headers


def test_deleting_a_team_from_its_own_page_redirects_to_the_teams_list(client, services):
    # Review Focus test (6)
    team = make_team(services)
    own_page = f"http://testserver/ui/teams/{team.id}"
    response = client.delete(f"/ui/teams/{team.id}", headers={"HX-Current-URL": own_page})
    assert response.headers["HX-Redirect"] == "/ui/teams"


def test_a_failed_save_keeps_the_derived_rpo_rto_in_the_edit_row(client, services):
    team = make_team(services)
    app = make_app(services, team, availability_level="SERIOUS")
    response = client.put(
        f"/ui/applications/{app.id}",
        data={"name": " ", "availability_level": "SERIOUS"},
    )
    assert response.status_code == 422
    assert "name must not be blank" in response.text
    assert "4 h / 0 h" in response.text
    assert f'hx-put="/ui/applications/{app.id}"' in response.text
