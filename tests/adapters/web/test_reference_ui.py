def test_index_lists_the_eight_catalogs(client):
    html = client.get("/ui/reference").text
    assert "<html" in html
    for kind in (
        "confidentiality_level", "integrity_level", "availability_level", "traceability_level",
        "function_category", "usage_mode", "technology_type", "tech_standard_status",
    ):
        assert f'href="/ui/reference/{kind}"' in html


def test_ranked_kind_page_lists_values_by_rank_with_a_rank_column(client):
    html = client.get("/ui/reference/integrity_level").text
    assert "<html" in html and "<th scope=\"col\">Rank</th>" in html
    positions = [
        html.index(f'id="ref-integrity_level-{code}"')
        for code in ("EXTREME", "SERIOUS", "MODERATE", "LOW")
    ]
    assert positions == sorted(positions)
    assert 'hx-post="/ui/reference/integrity_level?table=reference"' in html
    assert "renames it everywhere" in html


def test_plain_kind_has_no_rank_and_availability_has_hours(client):
    plain = client.get("/ui/reference/usage_mode").text
    assert "Rank" not in plain
    avail = client.get("/ui/reference/availability_level").text
    assert "RPO (hours)" in avail and "RTO (hours)" in avail


def test_unknown_kind_is_a_404_page_and_a_404_flash(client, hx):
    assert client.get("/ui/reference/nope").status_code == 404
    response = client.post("/ui/reference/nope?table=reference", data={"code": "X"}, headers=hx)
    assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash"


def test_add_a_plain_value(client, catalog):
    response = client.post(
        "/ui/reference/function_category?table=reference",
        data={"code": "EXTRA", "label": "Extra", "description": ""},
    )
    assert response.status_code == 201
    assert catalog.exists("function_category", "EXTRA")
    assert '<tr id="ref-function_category-EXTRA"' in response.text
    assert 'hx-get="/ui/reference/function_category/EXTRA/edit"' in response.text


def test_add_a_ranked_and_an_availability_value(client, catalog):
    ranked = client.post(
        "/ui/reference/integrity_level?table=reference",
        data={"code": "TINY", "label": "Tiny", "rank": "0"},
    )
    assert ranked.status_code == 201 and catalog.get("integrity_level", "TINY").rank == 0
    avail = client.post(
        "/ui/reference/availability_level?table=reference",
        data={"code": "MINI", "label": "Mini", "rank": "0", "rpo_hours": "1", "rto_hours": "2"},
    )
    assert avail.status_code == 201
    assert catalog.get("availability_level", "MINI").rto_hours == 2


def test_add_problems_are_422_or_409(client, catalog):
    # Review Focus test (4) and (5)
    url = "/ui/reference/integrity_level?table=reference"
    for code in ("a/b", "lower", "A B", "É"):
        response = client.post(url, data={"code": code, "label": "x", "rank": "1"})
        assert response.status_code == 422, code
        assert "code must contain only" in response.text
    # surrounding whitespace is stripped by the form, so " PAD " is accepted as "PAD"
    padded = client.post(url, data={"code": " PAD ", "label": "Pad", "rank": "1"})
    assert padded.status_code == 201 and catalog.exists("integrity_level", "PAD")
    not_a_number = client.post(url, data={"code": "NUM", "label": "x", "rank": "1.5"})
    assert not_a_number.status_code == 422 and "Rank: must be a whole number" in not_a_number.text
    no_rank = client.post(url, data={"code": "NUM", "label": "x", "rank": ""})
    assert no_rank.status_code == 422 and "Rank: is required" in no_rank.text
    blank_label = client.post(url, data={"code": "NUM", "label": " ", "rank": "1"})
    assert blank_label.status_code == 422 and "label must not be blank" in blank_label.text
    duplicate = client.post(url, data={"code": "LOW", "label": "again", "rank": "1"})
    assert duplicate.status_code == 409 and "already exists" in duplicate.text
    assert duplicate.headers["HX-Retarget"] == "#add-errors-reference"
    assert not catalog.exists("integrity_level", "NUM")


def test_hostile_text_in_a_label_is_escaped(client, catalog):
    # Review Focus test (1)
    client.post(
        "/ui/reference/usage_mode?table=reference",
        data={"code": "XSS", "label": '<script>alert(1)</script>"'},
    )
    html = client.get("/ui/reference/usage_mode").text
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_edit_row_and_save(client, catalog):
    edit = client.get("/ui/reference/availability_level/SERIOUS/edit")
    assert edit.status_code == 200 and "<html" not in edit.text
    assert 'name="code"' in edit.text and 'value="SERIOUS"' in edit.text
    assert 'name="rpo_hours"' in edit.text and 'value="4"' in edit.text
    assert 'hx-put="/ui/reference/availability_level/SERIOUS"' in edit.text
    saved = client.put(
        "/ui/reference/availability_level/SERIOUS",
        data={"code": "SERIOUS", "label": "Serious", "description": "", "rank": "3",
              "rpo_hours": "1", "rto_hours": "1"},
    )
    assert saved.status_code == 200
    assert catalog.get("availability_level", "SERIOUS").rpo_hours == 1


def test_rename_changes_the_row_id_and_the_stored_code(client, catalog):
    # Review Focus test (5)
    client.post(
        "/ui/reference/function_category?table=reference",
        data={"code": "EXTRA", "label": "Extra"},
    )
    response = client.put(
        "/ui/reference/function_category/EXTRA",
        data={"code": "EXTRA2", "label": "Extra", "description": ""},
    )
    assert response.status_code == 200
    assert '<tr id="ref-function_category-EXTRA2"' in response.text
    assert catalog.exists("function_category", "EXTRA2")
    assert not catalog.exists("function_category", "EXTRA")


def test_rename_onto_an_existing_code_is_409_and_keeps_the_edit_row(client, catalog):
    response = client.put(
        "/ui/reference/function_category/DATA",
        data={"code": "COMMON", "label": "x", "description": ""},
    )
    assert response.status_code == 409 and "already exists" in response.text
    assert 'hx-put="/ui/reference/function_category/DATA"' in response.text
    assert catalog.exists("function_category", "DATA")


def test_save_with_a_bad_code_or_number_is_422(client, catalog):
    bad_code = client.put(
        "/ui/reference/function_category/DATA", data={"code": "a/b", "label": "x"}
    )
    assert bad_code.status_code == 422
    bad_number = client.put(
        "/ui/reference/integrity_level/LOW", data={"code": "LOW", "label": "Low", "rank": "x"}
    )
    assert bad_number.status_code == 422 and "Rank: must be a whole number" in bad_number.text
    assert catalog.exists("function_category", "DATA")


def test_delete_a_value_and_a_blocked_delete(client, catalog, hx):
    client.post(
        "/ui/reference/function_category?table=reference",
        data={"code": "EXTRA", "label": "Extra"},
    )
    ok = client.delete("/ui/reference/function_category/EXTRA")
    assert ok.status_code == 200 and ok.text == ""
    assert not catalog.exists("function_category", "EXTRA")
    catalog.mark_in_use("usage_mode", "PROXY")
    blocked = client.delete("/ui/reference/usage_mode/PROXY", headers=hx)
    assert blocked.status_code == 409 and blocked.headers["HX-Retarget"] == "#flash"
    assert "still referenced" in blocked.text and catalog.exists("usage_mode", "PROXY")


def test_missing_value_is_a_404_flash(client, hx):
    for method, url in (
        ("get", "/ui/reference/usage_mode/NOPE/row"),
        ("get", "/ui/reference/usage_mode/NOPE/edit"),
        ("delete", "/ui/reference/usage_mode/NOPE"),
    ):
        response = getattr(client, method)(url, headers=hx)
        assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash", url


def test_a_renamed_level_shows_up_in_application_forms(client, services, catalog):
    # Review Focus test (5): the dropdowns read the catalog on every render
    client.put(
        "/ui/reference/integrity_level/LOW",
        data={"code": "TRIVIAL", "label": "Trivial", "description": "", "rank": "1"},
    )
    team = services.teams.create({"name": "T"})
    html = client.get(f"/ui/teams/{team.id}").text
    integrity = html[html.index('name="integrity_level"') :]
    integrity = integrity[: integrity.index("</select>")]
    assert '<option value="TRIVIAL"' in integrity and '<option value="LOW"' not in integrity


def test_table_value_is_sanitized_in_the_retarget(client):
    response = client.post("/ui/reference/usage_mode?table=a%0Ab", data={"code": "", "label": "x"})
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#add-errors-reference"
