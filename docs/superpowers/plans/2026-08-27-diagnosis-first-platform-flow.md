# Diagnosis-First Platform Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform start at the learner diagnosis console and automatically launch the complete course path after the questionnaire and adaptive test produce a final learner profile.

**Architecture:** Keep the diagnosis Agent as the source of the final profile. After adaptive-test application, the diagnosis console fetches the profile, stores a short-lived handoff in same-origin session storage, and redirects to the platform console. The platform console consumes that handoff, adapts the profile through the existing API, and starts a run without a manual file upload. The platform root redirects to `/diagnosis/` so new users begin with diagnosis.

**Tech Stack:** FastAPI, vanilla browser JavaScript, sessionStorage, pytest, uvicorn.

## Global Constraints

- Preserve the existing `/api/v1/profiles/adapt` and `/api/v1/runs` contracts.
- The course planner must receive no target concept by default and must generate the full prerequisite-safe path.
- The adaptive test remains the required gate before profile handoff.
- Do not place API keys or raw profile data in URLs.
- Existing manual JSON upload remains available as a fallback.

---

### Task 1: Route the platform entry point to diagnosis

**Files:**
- Modify: `src/skillforge_kb/api/app.py`
- Test: `tests/unit/api/test_app.py`

**Interfaces:**
- `GET /` returns a redirect to `/diagnosis/`.
- Existing platform console remains available at `/platform` or through the diagnosis completion redirect target.

- [ ] **Step 1: Write the failing test**

```python
def test_root_starts_at_diagnosis_console(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/diagnosis/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_app.py -q`
Expected: FAIL because `/` currently returns the platform HTML directly.

- [ ] **Step 3: Write minimal implementation**

Move the existing platform console handler to `GET /platform`, add a redirect handler at `GET /`, and keep the diagnosis sub-application mounted at `/diagnosis`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/api/test_app.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/api/app.py tests/unit/api/test_app.py
git commit -m "feat: start platform at learner diagnosis"
```

### Task 2: Return the final profile from the diagnosis console

**Files:**
- Modify: `学情诊断Agent/static/index.html`
- Test: `学情诊断Agent/test_questionnaire_flow_contract.py`

**Interfaces:**
- `finishAdaptiveAndDiagnose()` calls `GET /api/learner/{learner_id}/profile` after applying the finished session.
- It stores JSON under `skillforge.pendingProfile.v1` with `{profile, learner_id, created_at}` and navigates to `/platform?from=diagnosis`.

- [ ] **Step 1: Write the failing test**

```python
def test_diagnosis_console_contains_profile_handoff_contract():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert "skillforge.pendingProfile.v1" in html
    assert "/api/learner/" in html and "/profile" in html
    assert "/platform?from=diagnosis" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project .. pytest test_questionnaire_flow_contract.py -q`
Expected: FAIL because the current page only diagnoses in its own dashboard.

- [ ] **Step 3: Write minimal implementation**

After `/apply` succeeds, fetch the profile, write the handoff object to `sessionStorage`, and redirect. On failure, keep the existing status message and re-enable the finish button.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project .. pytest test_questionnaire_flow_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 学情诊断Agent/static/index.html 学情诊断Agent/test_questionnaire_flow_contract.py
git commit -m "feat: hand off diagnosed profile to platform"
```

### Task 3: Consume the handoff and auto-run the full path

**Files:**
- Modify: `src/skillforge_kb/api/static/app.js`
- Modify: `src/skillforge_kb/api/static/index.html`
- Test: `tests/unit/api/test_frontend.py`

**Interfaces:**
- On page load, `consumeDiagnosisHandoff()` reads and validates `skillforge.pendingProfile.v1`.
- It clears the key before starting, calls `normalizeProfile`, assigns `state.profile`, clears `targetConceptId`, and invokes `runPlatform()`.
- Invalid or expired handoffs are discarded with a visible error; manual upload remains usable.

- [ ] **Step 1: Write the failing test**

```python
def test_platform_frontend_consumes_diagnosis_handoff():
    js = Path("src/skillforge_kb/api/static/app.js").read_text(encoding="utf-8")
    html = Path("src/skillforge_kb/api/static/index.html").read_text(encoding="utf-8")
    assert "skillforge.pendingProfile.v1" in js
    assert "consumeDiagnosisHandoff" in js
    assert 'href="/platform"' in html or "id=\"platform-console\"" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_frontend.py -q`
Expected: FAIL because the platform page has no session-storage consumer.

- [ ] **Step 3: Write minimal implementation**

Add a DOM-ready call that consumes the handoff asynchronously. Use a timestamp TTL of 15 minutes, require a profile object, set the summary, enable the run button, and call `runPlatform()` with no target concept.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/api/test_frontend.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/api/static/app.js src/skillforge_kb/api/static/index.html tests/unit/api/test_frontend.py
git commit -m "feat: auto-start course flow from diagnosis handoff"
```

### Task 4: Verify the complete browser-facing flow

**Files:**
- Test: `tests/unit/api/test_app.py`
- Test: `学情诊断Agent/test_questionnaire_flow_contract.py`

- [ ] **Step 1: Run focused backend and diagnosis tests**

Run: `uv run pytest tests/unit/api -q --disable-warnings`
Expected: all API tests pass.

Run: `uv run --project .. pytest "学情诊断Agent" -q --disable-warnings`
Expected: diagnosis tests pass with no failures.

- [ ] **Step 2: Start the platform on an unused port**

Run: `uv run skillforge-kb platform-serve --project-root . --host 127.0.0.1 --port 8124`
Expected: the server listens on `http://127.0.0.1:8124`.

- [ ] **Step 3: Verify HTTP entry points**

Run: `Invoke-WebRequest http://127.0.0.1:8124/ -MaximumRedirection 0`
Expected: redirect location `/diagnosis/`.

Run: `Invoke-WebRequest http://127.0.0.1:8124/diagnosis/`
Expected: diagnosis console HTML with questionnaire and adaptive-test tabs.

Run: `Invoke-WebRequest http://127.0.0.1:8124/platform`
Expected: platform console HTML.

- [ ] **Step 4: Run the full unit suite**

Run: `uv run pytest tests/unit -q --disable-warnings`
Expected: zero failures; integration service tests remain excluded by the repository default marker.
