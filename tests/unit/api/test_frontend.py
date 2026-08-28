import re

from fastapi.testclient import TestClient


def test_root_starts_at_dashboard(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard"


def test_vite_spa_is_available_for_frontend_routes(client: TestClient) -> None:
    for route in ("/platform", "/dashboard", "/diagnosis", "/learning-path"):
        response = client.get(route)

        assert response.status_code == 200
        assert '<div id="app"></div>' in response.text
        assert "知径 | AI 个性化学习平台" in response.text


def test_vite_build_assets_are_served(client: TestClient) -> None:
    html = client.get("/dashboard")
    script_match = re.search(r'<script type="module" crossorigin src="([^"]+)"', html.text)

    assert html.status_code == 200
    assert script_match is not None

    javascript = client.get(script_match.group(1))
    assert javascript.status_code == 200
    assert "createApp" in javascript.text


def test_old_static_frontend_is_no_longer_served(client: TestClient) -> None:
    assert client.get("/static/platform/assets/styles/app.css").status_code == 404
    assert client.get("/static/platform/assets/scripts/app.js").status_code == 404
    assert client.get("/static/index.html").status_code == 404


def test_diagnosis_api_remains_available(client: TestClient) -> None:
    response = client.get("/diagnosis/api/learners")

    assert response.status_code == 200
    assert "learners" in response.json()
