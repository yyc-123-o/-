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
    assert "画像转换摘要" in javascript.text
    assert "target_concept_id" in javascript.text
    assert "run-overview" in javascript.text
    assert "chapter_id" in javascript.text
    assert "进入学习" in javascript.text
    assert "/complete-node" in javascript.text
    assert "完成并进入下一节点" in javascript.text
    assert "/start-node" in javascript.text
    assert "/assessment" in javascript.text
    assert "提交测验" in javascript.text
    assert "进入该节点" in javascript.text
    assert "candidate_preview" in html.text
    assert 'id="learning-workbench"' in html.text
    assert 'id="path-progress"' in html.text
    assert 'id="node-resource"' in html.text
    assert "学习演示模式" in html.text
    assert "正式资源模式" in html.text
    assert "每类候选证据数" in html.text
    assert 'data-tab="raw-view"' not in html.text
    assert 'id="raw-view"' not in html.text
    assert "resource-requirements" in javascript.text
    assert "resource-code-line" in javascript.text
    assert "项目实践要求" in javascript.text
    assert "start-node" in javascript.text
    assert "讲义" in javascript.text
    assert "实践" in javascript.text
    assert "测验" in javascript.text
    assert "practice-review" in javascript.text
    assert "code-editor" in javascript.text
    assert "buildFormalLearningTabs" in javascript.text
    assert "画像转换摘要" in javascript.text
    assert "演示学习资源已生成" in javascript.text
    assert "个性化计算" in javascript.text
    assert "const rawJson" not in javascript.text
