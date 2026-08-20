from fastapi.testclient import TestClient


def test_console_is_the_root_screen(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="profile-file"' in response.text
    assert 'id="run-platform"' in response.text
    assert 'id="path-view"' in response.text
    assert 'id="evidence-view"' in response.text
    assert 'id="resource-view"' in response.text


def test_console_declares_an_inline_favicon(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'rel="icon" href="data:,' in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    html = client.get("/")
    css = client.get("/static/app.css")
    javascript = client.get("/static/app.js")

    assert html.status_code == 200
    assert css.status_code == 200
    assert javascript.status_code == 200
    assert "#002fa7" in css.text.casefold()
    assert "/api/v1/runs" in javascript.text
    assert "/api/v1/profiles/adapt" in javascript.text
    assert "profileWarnings" in javascript.text
    assert "适配警告" in javascript.text
    assert "target_concept_id" in javascript.text
    assert "run-overview" in javascript.text
    assert "chapter_id" in javascript.text
    assert "进入学习" in javascript.text
    assert "candidate_preview" in html.text
