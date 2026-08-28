import re

from fastapi.testclient import TestClient


def test_root_serves_landing_page(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "知径 | AI 个性化学习平台" in response.text
    assert '<div id="app"></div>' in response.text


def test_frontend_routes_serve_spa(client: TestClient) -> None:
    for route in ("/dashboard", "/diagnosis", "/learning-path", "/profile"):
        response = client.get(route)

        assert response.status_code == 200
        assert '<div id="app"></div>' in response.text or "知径 | AI 个性化学习平台" in response.text


def test_vite_build_asset_is_served(client: TestClient) -> None:
    html = client.get("/")
    script_match = re.search(r'<script type="module" crossorigin src="([^"]+)"', html.text)

    assert html.status_code == 200
    assert script_match is not None

    javascript = client.get(script_match.group(1))
    assert javascript.status_code == 200
    assert "createApp" in javascript.text


def test_diagnosis_api_remains_available(client: TestClient) -> None:
    response = client.get("/diagnosis/api/learners")

    assert response.status_code == 200
    assert "learners" in response.json()
