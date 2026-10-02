from uuid import uuid4


def make_team(services, name="Payments", description=""):
    return services.teams.create({"name": name, "description": description})


# ------------------------------------------------------------------ pages


def test_teams_page_is_a_full_page_with_table_and_add_form(client, services):
    team = make_team(services)
    response = client.get("/ui/teams")
    assert response.status_code == 200
    html = response.text
    assert "<html" in html
    assert "/ui/static/htmx.min.js" in html and "/ui/static/pico.min.css" in html
    assert "htmx-config" in html and "responseHandling" in html
    assert 'id="flash"' in html
    assert 'id="rows-teams"' in html
    assert f'<tr id="team-{team.id}"' in html
    assert f'href="/ui/teams/{team.id}"' in html
    assert 'hx-post="/ui/teams?table=teams"' in html
    assert 'id="add-errors-teams"' in html


def test_personas_page_lists_personas(client, services):
    services.personas.create({"name": "Accountant", "category": "finance"})
    html = client.get("/ui/personas").text
    assert "Accountant" in html and "finance" in html
    assert 'hx-post="/ui/personas?table=personas"' in html


# ------------------------------------------------------------------ add


def test_add_returns_the_new_row_and_clears_the_error_area(client, services):
    response = client.post("/ui/teams?table=teams", data={"name": " Payments ", "description": "d"})
    assert response.status_code == 201
    team = services.teams.list()[0]
    assert team.name == "Payments"
    html = response.text
    assert f'<tr id="team-{team.id}"' in html
    assert "<html" not in html
    assert 'id="add-errors-teams"' in html and "hx-swap-oob" in html


def test_add_with_a_blank_name_is_422_and_stores_nothing(client, services):
    response = client.post("/ui/teams?table=teams", data={"name": "  "})
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#add-errors-teams"
    assert response.headers["HX-Reswap"] == "innerHTML"
    assert "name must not be blank" in response.text
    assert services.teams.list() == []


def test_add_retargets_to_the_table_named_in_the_query(client):
    response = client.post("/ui/personas?table=people", data={"name": ""})
    assert response.headers["HX-Retarget"] == "#add-errors-people"


def test_html_in_values_is_escaped_in_rows_inputs_and_confirm(client, services):
    # Review Focus test (1)
    nasty = '<script>alert(1)</script> "q"'
    team = make_team(services, name=nasty)
    row = client.get(f"/ui/teams/{team.id}/row").text
    assert "<script>alert(1)" not in row
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in row
    edit = client.get(f"/ui/teams/{team.id}/edit").text
    assert "<script>alert(1)" not in edit
    assert "&lt;script&gt;" in edit and "&#34;q&#34;" in edit
    page = client.post("/ui/teams?table=teams", data={"name": nasty}).text
    assert "<script>alert(1)" not in page


# ------------------------------------------------------------------ rows


def test_display_row_and_edit_row_are_fragments(client, services):
    team = make_team(services)
    row = client.get(f"/ui/teams/{team.id}/row")
    assert row.status_code == 200 and "<html" not in row.text
    assert f'hx-get="/ui/teams/{team.id}/edit"' in row.text
    assert f'hx-delete="/ui/teams/{team.id}"' in row.text
    edit = client.get(f"/ui/teams/{team.id}/edit")
    assert edit.status_code == 200 and "<html" not in edit.text
    assert 'name="name"' in edit.text and 'value="Payments"' in edit.text
    assert f'hx-put="/ui/teams/{team.id}"' in edit.text
    assert f'hx-get="/ui/teams/{team.id}/row"' in edit.text


def test_save_updates_and_returns_the_display_row(client, services):
    team = make_team(services)
    response = client.put(f"/ui/teams/{team.id}", data={"name": "Billing", "description": "x"})
    assert response.status_code == 200
    assert "Billing" in response.text and "hx-put" not in response.text
    assert services.teams.get(team.id).name == "Billing"


def test_save_with_a_blank_name_rerenders_the_edit_row_with_the_typed_values(client, services):
    team = make_team(services)
    response = client.put(f"/ui/teams/{team.id}", data={"name": " ", "description": "typed"})
    assert response.status_code == 422
    assert "name must not be blank" in response.text
    assert 'role="alert"' in response.text
    assert ">typed</textarea>" in response.text
    assert f'hx-put="/ui/teams/{team.id}"' in response.text
    assert services.teams.get(team.id).name == "Payments"


# ------------------------------------------------------------------ delete and failures


def test_delete_returns_an_empty_body_and_removes_the_record(client, services):
    team = make_team(services)
    response = client.delete(f"/ui/teams/{team.id}")
    assert response.status_code == 200 and response.text == ""
    assert services.teams.list() == []


def test_blocked_delete_is_a_409_flash_message(client, services, repos, hx):
    # Review Focus test (2)
    team = make_team(services)
    repos.teams.mark_in_use(team.id)
    response = client.delete(f"/ui/teams/{team.id}", headers=hx)
    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == "#flash"
    assert response.headers["HX-Reswap"] == "innerHTML"
    assert "still referenced" in response.text
    assert "<html" not in response.text
    assert services.teams.get(team.id).name == "Payments"


def test_missing_record_is_a_404_flash_for_every_row_action(client, hx):
    # Review Focus test (2)
    ghost = uuid4()
    for method, url in (
        ("get", f"/ui/teams/{ghost}/row"),
        ("get", f"/ui/teams/{ghost}/edit"),
        ("put", f"/ui/teams/{ghost}"),
        ("delete", f"/ui/teams/{ghost}"),
    ):
        response = getattr(client, method)(url, headers=hx)
        assert response.status_code == 404, (method, url)
        assert response.headers["HX-Retarget"] == "#flash"


def test_the_same_error_without_htmx_is_a_full_error_page(client):
    response = client.get(f"/ui/teams/{uuid4()}/row")
    assert response.status_code == 404
    assert "<html" in response.text and "not found" in response.text


def test_persona_add_edit_save_delete(client, services):
    added = client.post("/ui/personas?table=personas", data={"name": "Accountant", "category": "finance"})
    assert added.status_code == 201
    persona = services.personas.list()[0]
    assert persona.category == "finance"
    saved = client.put(f"/ui/personas/{persona.id}", data={"name": "Auditor", "description": "", "category": ""})
    assert saved.status_code == 200
    assert services.personas.get(persona.id).category is None
    assert client.delete(f"/ui/personas/{persona.id}").status_code == 200
