from uuid import uuid4


def make_app(services, **extra):
    team = services.teams.create({"name": "Payments"})
    app = services.applications.create({"team_id": team.id, "name": "Billing", **extra})
    return team, app


# ------------------------------------------------------------------ page and tabs


def test_application_page_has_breadcrumbs_tabs_and_the_details_tab(client, services):
    team, app = make_app(services, availability_level="SERIOUS", golden_app_id="G1")
    html = client.get(f"/ui/applications/{app.id}").text
    assert "<html" in html
    assert f'href="/ui/teams/{team.id}"' in html and "Payments" in html
    assert 'id="tab-panel"' in html
    for key in ("details", "functions", "data-types", "technologies", "data-flows"):
        assert f'hx-get="/ui/applications/{app.id}/tabs/{key}"' in html
        assert f'hx-push-url="/ui/applications/{app.id}?tab={key}"' in html
    assert 'aria-current="page"' in html
    assert 'value="G1"' in html and "4 h / 0 h" in html


def test_tab_query_selects_the_tab_and_marks_it_current(client, services):
    _, app = make_app(services)
    html = client.get(f"/ui/applications/{app.id}?tab=functions").text
    assert f'hx-post="/ui/applications/{app.id}/functions?table=functions"' in html
    current = html.index('aria-current="page"')
    assert "tabs/functions" in html[html.rfind("<a", 0, current):current]


def test_unknown_tab_is_a_404_page(client, services):
    _, app = make_app(services)
    assert client.get(f"/ui/applications/{app.id}?tab=nope").status_code == 404
    assert client.get(f"/ui/applications/{app.id}/tabs/nope").status_code == 404


def test_missing_application_page_is_a_404_page(client):
    response = client.get(f"/ui/applications/{uuid4()}")
    assert response.status_code == 404 and "<html" in response.text


def test_tab_fragment_is_not_a_full_page(client, services):
    _, app = make_app(services)
    response = client.get(f"/ui/applications/{app.id}/tabs/technologies")
    assert response.status_code == 200
    assert "<html" not in response.text
    assert f'hx-post="/ui/applications/{app.id}/technologies?table=technologies"' in response.text
    assert 'aria-current="page"' in response.text


# ------------------------------------------------------------------ details form


def test_details_save_updates_the_application_and_reports_saved(client, services):
    _, app = make_app(services)
    response = client.put(
        f"/ui/applications/{app.id}/details",
        data={
            "name": "Billing v2",
            "shortname": "bil",
            "golden_app_id": "G9",
            "auid": "A9",
            "asset_cmdb": "C9",
            "owner_uid": "u9",
            "description": "now described",
            "confidentiality_level": "LOW",
            "integrity_level": "MODERATE",
            "availability_level": "EXTREME",
            "traceability_level": "",
        },
    )
    assert response.status_code == 200
    assert "Saved." in response.text and "2 h / 0 h" in response.text
    saved = services.applications.get(app.id)
    assert (saved.name, saved.golden_app_id, saved.owner_uid) == ("Billing v2", "G9", "u9")
    assert saved.description == "now described" and saved.traceability_level is None
    assert saved.availability_level == "EXTREME"


def test_details_save_with_a_blank_name_is_422_and_keeps_what_was_typed(client, services):
    _, app = make_app(services)
    response = client.put(
        f"/ui/applications/{app.id}/details", data={"name": " ", "description": "typed text"}
    )
    assert response.status_code == 422
    assert "name must not be blank" in response.text
    assert "typed text" in response.text and "Saved." not in response.text
    assert services.applications.get(app.id).name == "Billing"


def test_details_save_with_an_unknown_level_is_422(client, services):
    _, app = make_app(services)
    response = client.put(
        f"/ui/applications/{app.id}/details", data={"name": "A", "integrity_level": "NOPE"}
    )
    assert response.status_code == 422 and "is not a valid integrity_level" in response.text


def test_details_tab_has_a_delete_button_that_confirms(client, services):
    _, app = make_app(services)
    html = client.get(f"/ui/applications/{app.id}/tabs/details").text
    assert f'hx-delete="/ui/applications/{app.id}"' in html
    assert "functions, data types and technologies" in html


def test_details_values_are_escaped(client, services):
    # Review Focus test (1)
    _, app = make_app(services, description='</textarea><script>alert(1)</script>')
    html = client.get(f"/ui/applications/{app.id}/tabs/details").text
    assert "<script>alert(1)" not in html and "&lt;/textarea&gt;" in html


# ------------------------------------------------------------------ functions


def test_functions_tab_lists_only_this_applications_functions(client, services):
    _, app_a = make_app(services)
    _, app_b = make_app(services)
    services.functions.create({"application_id": app_a.id, "name": "Invoice"})
    services.functions.create({"application_id": app_b.id, "name": "Refund"})
    html = client.get(f"/ui/applications/{app_a.id}/tabs/functions").text
    assert "Invoice" in html and "Refund" not in html


def test_add_function_with_category_and_persona(client, services):
    _, app = make_app(services)
    persona = services.personas.create({"name": "Accountant"})
    page = client.get(f"/ui/applications/{app.id}/tabs/functions").text
    assert f'<option value="{persona.id}"' in page and '<option value="BUSINESS"' in page
    response = client.post(
        f"/ui/applications/{app.id}/functions?table=functions",
        data={
            "name": "Invoice",
            "description": "",
            "category": "BUSINESS",
            "persona_id": str(persona.id),
        },
    )
    assert response.status_code == 201
    fn = services.functions.list()[0]
    assert (fn.application_id, fn.persona_id, fn.category) == (app.id, persona.id, "BUSINESS")
    assert "Accountant" in response.text and "Business" in response.text


def test_function_with_an_unknown_persona_or_category_is_422(client, services):
    # Review Focus test (4)
    _, app = make_app(services)
    base = f"/ui/applications/{app.id}/functions?table=functions"
    ghost = client.post(base, data={"name": "F", "persona_id": str(uuid4())})
    assert ghost.status_code == 422 and "does not exist" in ghost.text
    garbage = client.post(base, data={"name": "F", "persona_id": "nope"})
    assert garbage.status_code == 422
    category = client.post(base, data={"name": "F", "category": "NOPE"})
    assert category.status_code == 422 and "is not a valid function_category" in category.text
    assert services.functions.list() == []


def test_function_save_keeps_its_application(client, services):
    _, app = make_app(services)
    fn = services.functions.create({"application_id": app.id, "name": "Invoice"})
    other = services.applications.create({"team_id": app.team_id, "name": "Other"})
    base = f"/ui/applications/{app.id}/functions/{fn.id}"
    response = client.put(
        base, data={"name": "Invoice v2", "application_id": str(other.id), "category": "DATA"}
    )
    assert response.status_code == 200
    saved = services.functions.get(fn.id)
    assert (saved.name, saved.category, saved.application_id) == ("Invoice v2", "DATA", app.id)


def test_function_through_the_wrong_application_is_404(client, services, hx):
    # Review Focus test (2)
    _, app_a = make_app(services)
    _, app_b = make_app(services)
    fn = services.functions.create({"application_id": app_a.id, "name": "Invoice"})
    wrong = f"/ui/applications/{app_b.id}/functions/{fn.id}"
    assert client.get(wrong + "/row", headers=hx).status_code == 404
    assert client.delete(wrong, headers=hx).status_code == 404
    assert services.functions.get(fn.id).name == "Invoice"


def test_functions_under_a_missing_application_are_404(client, hx):
    response = client.post(
        f"/ui/applications/{uuid4()}/functions?table=functions", data={"name": "F"}, headers=hx
    )
    assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash"


# ------------------------------------------------------------------ data types, technologies


def test_add_data_type_and_technology(client, services):
    _, app = make_app(services)
    dt = client.post(
        f"/ui/applications/{app.id}/data-types?table=data-types",
        data={
            "name": "Invoice",
            "confidentiality_level": "LOW",
            "golden_source": "ERP",
            "golden_replica": "DWH",
        },
    )
    assert dt.status_code == 201
    stored = services.data_types.list()[0]
    assert (stored.golden_source, stored.golden_replica) == ("ERP", "DWH")
    tech = client.post(
        f"/ui/applications/{app.id}/technologies?table=technologies",
        data={
            "name": "PostgreSQL",
            "version": "16",
            "type": "DATABASE",
            "standard_status": "REFERENCE",
            "tech_standards_link": "http://standards/pg",
        },
    )
    assert tech.status_code == 201
    assert services.technologies.list()[0].type == "DATABASE"


def test_technology_with_unknown_codes_is_422(client, services):
    _, app = make_app(services)
    base = f"/ui/applications/{app.id}/technologies?table=technologies"
    assert client.post(base, data={"name": "T", "type": "NOPE"}).status_code == 422
    assert client.post(base, data={"name": "T", "standard_status": "NOPE"}).status_code == 422
    assert services.technologies.list() == []


def test_data_type_and_technology_tabs_list_rows(client, services):
    _, app = make_app(services)
    services.data_types.create({"application_id": app.id, "name": "Invoice"})
    services.technologies.create({"application_id": app.id, "name": "PostgreSQL"})
    assert "Invoice" in client.get(f"/ui/applications/{app.id}/tabs/data-types").text
    assert "PostgreSQL" in client.get(f"/ui/applications/{app.id}/tabs/technologies").text


def test_deleting_an_application_deletes_through_the_details_button(client, services):
    team, app = make_app(services)
    response = client.delete(
        f"/ui/applications/{app.id}",
        headers={"HX-Current-URL": f"http://testserver/ui/applications/{app.id}?tab=functions"},
    )
    assert response.headers["HX-Redirect"] == f"/ui/teams/{team.id}"
