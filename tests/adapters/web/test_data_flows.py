from uuid import uuid4


def setup_two_apps(services):
    team_a = services.teams.create({"name": "Team A"})
    team_b = services.teams.create({"name": "Team B"})
    source = services.applications.create({"team_id": team_a.id, "name": "Billing"})
    target = services.applications.create({"team_id": team_b.id, "name": "Ledger"})
    data_type = services.data_types.create({"application_id": source.id, "name": "Invoice"})
    return source, target, data_type


def make_flow(services, source, target, data_type, **extra):
    return services.data_flows.create(
        {
            "source_application_id": source.id,
            "target_application_id": target.id,
            "data_type_id": data_type.id,
            **extra,
        }
    )


def test_data_flows_tab_splits_outgoing_and_incoming(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type, usage_mode="SOURCE")
    out = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert 'id="rows-outgoing"' in out and 'id="rows-incoming"' in out
    outgoing = out[out.index('id="rows-outgoing"') : out.index('id="rows-incoming"')]
    incoming = out[out.index('id="rows-incoming"') :]
    assert f'<tr id="data-flow-{flow.id}"' in outgoing
    assert "<tr id=" not in incoming
    assert "Ledger" in outgoing and "Billing › Invoice" in outgoing
    assert "<td>Source</td>" in outgoing
    inbound = client.get(f"/ui/applications/{target.id}/tabs/data-flows").text
    inbound_in = inbound[inbound.index('id="rows-incoming"') :]
    assert f'<tr id="data-flow-{flow.id}"' in inbound_in


def test_add_forms_prefill_this_application_as_source_or_target(client, services):
    source, target, _ = setup_two_apps(services)
    html = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert 'hx-post="/ui/data-flows?table=outgoing"' in html
    assert 'hx-post="/ui/data-flows?table=incoming"' in html
    assert f'name="source_application_id" value="{source.id}"' in html
    assert f'name="target_application_id" value="{source.id}"' in html


def test_other_application_options_are_grouped_by_team_and_data_types_by_application(
    client, services
):
    source, target, _ = setup_two_apps(services)
    html = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert '<optgroup label="Team A">' in html and '<optgroup label="Team B">' in html
    assert '<optgroup label="Billing">' in html
    assert ">Billing › Invoice</option>" in html


def test_add_an_outgoing_flow(client, services):
    source, target, data_type = setup_two_apps(services)
    response = client.post(
        "/ui/data-flows?table=outgoing",
        data={
            "source_application_id": str(source.id),
            "target_application_id": str(target.id),
            "data_type_id": str(data_type.id),
            "usage_mode": "PROXY",
            "usage_explanation": "nightly export",
        },
    )
    assert response.status_code == 201
    flow = services.data_flows.list()[0]
    assert (flow.usage_mode, flow.usage_explanation) == ("PROXY", "nightly export")
    assert "nightly export" in response.text and "Ledger" in response.text


def test_flow_form_problems_are_422(client, services):
    # Review Focus test (4)
    source, target, data_type = setup_two_apps(services)
    full = {
        "source_application_id": str(source.id),
        "target_application_id": str(target.id),
        "data_type_id": str(data_type.id),
    }
    url = "/ui/data-flows?table=outgoing"
    missing = client.post(url, data={**full, "target_application_id": ""})
    assert missing.status_code == 422 and "Target application: is required" in missing.text
    ghost_type = client.post(url, data={**full, "data_type_id": str(uuid4())})
    assert ghost_type.status_code == 422 and "does not exist" in ghost_type.text
    ghost_app = client.post(url, data={**full, "source_application_id": str(uuid4())})
    assert ghost_app.status_code == 422
    bad_mode = client.post(url, data={**full, "usage_mode": "NOPE"})
    assert bad_mode.status_code == 422 and "is not a valid usage_mode" in bad_mode.text
    assert services.data_flows.list() == []


def test_flow_edit_row_has_source_target_and_data_type_selects(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type)
    html = client.get(f"/ui/data-flows/{flow.id}/edit").text
    for name in ("source_application_id", "target_application_id", "data_type_id", "usage_mode"):
        assert f'name="{name}"' in html
    assert f'<option value="{target.id}" selected>' in html


def test_flow_save_and_delete(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type)
    saved = client.put(
        f"/ui/data-flows/{flow.id}",
        data={
            "source_application_id": str(source.id),
            "target_application_id": str(source.id),
            "data_type_id": str(data_type.id),
            "usage_mode": "CONSUMER",
            "usage_explanation": "internal",
        },
    )
    assert saved.status_code == 200
    stored = services.data_flows.get(flow.id)
    assert (stored.target_application_id, stored.usage_mode) == (source.id, "CONSUMER")
    assert client.delete(f"/ui/data-flows/{flow.id}").status_code == 200
    assert services.data_flows.list() == []


def test_overview_lists_every_flow_with_links_and_no_actions(client, services):
    source, target, data_type = setup_two_apps(services)
    make_flow(services, source, target, data_type, usage_mode="SOURCE", usage_explanation="export")
    response = client.get("/ui/data-flows")
    html = response.text
    assert response.status_code == 200 and "<html" in html
    assert f'href="/ui/applications/{source.id}"' in html and "Billing" in html
    assert f'href="/ui/applications/{target.id}"' in html and "Ledger" in html
    assert "Invoice" in html and "<td>Source</td>" in html and "export" in html
    assert "hx-delete" not in html and "hx-get" not in html and "hx-post" not in html


def test_overview_escapes_explanations(client, services):
    # Review Focus test (1)
    source, target, data_type = setup_two_apps(services)
    make_flow(services, source, target, data_type, usage_explanation="<img src=x onerror=alert(1)>")
    html = client.get("/ui/data-flows").text
    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_an_application_used_by_a_flow_cannot_be_deleted_in_the_ui(client, services, repos, hx):
    # Review Focus test (2): the fake repository does not model foreign keys, so mark it in use
    source, target, data_type = setup_two_apps(services)
    make_flow(services, source, target, data_type)
    repos.applications.mark_in_use(target.id)
    response = client.delete(f"/ui/applications/{target.id}", headers=hx)
    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == "#flash" and "still referenced" in response.text
    assert services.applications.get(target.id).name == "Ledger"


PLACEHOLDER = '<option value="" disabled selected>Choose…</option>'


def test_required_selects_of_the_add_forms_start_on_a_disabled_placeholder(client, services):
    source, _, _ = setup_two_apps(services)
    html = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert PLACEHOLDER in html
    for form in html.split("<form")[1:]:
        form = form[: form.index("</form>")]
        for name in ("source_application_id", "target_application_id", "data_type_id"):
            if f'<select name="{name}"' in form:
                select = form[form.index(f'<select name="{name}"') :]
                assert PLACEHOLDER in select[: select.index("</select>")]
        usage = form[form.index('<select name="usage_mode"') :]
        assert PLACEHOLDER not in usage[: usage.index("</select>")]
        assert '<option value="">—</option>' in usage


def test_edit_row_does_not_select_the_placeholder(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type)
    html = client.get(f"/ui/data-flows/{flow.id}/edit").text
    assert '<option value="" disabled selected>' not in html
