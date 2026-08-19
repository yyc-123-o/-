const state = {
  profile: null,
  profileWarnings: [],
  result: null,
};

const profileFile = document.getElementById("profile-file");
const profileSummary = document.getElementById("profile-summary");
const profileError = document.getElementById("profile-error");
const runButton = document.getElementById("run-platform");
const topKInput = document.getElementById("top-k");
const runStatus = document.getElementById("run-status");
const runId = document.getElementById("run-id");
const publicationStatus = document.getElementById("publication-status");
const rawJson = document.getElementById("raw-json");

profileFile.addEventListener("change", handleProfileFile);
runButton.addEventListener("click", runPlatform);
document.querySelectorAll('[role="tab"]').forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

async function handleProfileFile(event) {
  resetProfileError();
  const file = event.target.files?.[0];
  if (!file) {
    state.profile = null;
    state.profileWarnings = [];
    runButton.disabled = true;
    renderProfileSummary();
    return;
  }
  try {
    const uploadedProfile = JSON.parse(await file.text());
    const normalized = await normalizeProfile(uploadedProfile);
    state.profile = normalized.snapshot;
    state.profileWarnings = normalized.warnings;
    validateProfile(state.profile);
    runButton.disabled = false;
    renderProfileSummary();
  } catch (error) {
    state.profile = null;
    state.profileWarnings = [];
    runButton.disabled = true;
    profileError.textContent = error instanceof Error ? error.message : "画像文件无效";
    renderProfileSummary();
  }
}

async function normalizeProfile(profile) {
  if (profile?.schema_version && profile?.graph_version) {
    return { snapshot: profile, warnings: [] };
  }
  if (profile?.profile_version !== "2.1") {
    throw new Error("画像必须是平台快照或学情诊断 Agent v2.1 输出");
  }
  const response = await fetch("/api/v1/profiles/adapt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail?.message || "学情画像适配失败");
  }
  return { snapshot: payload.snapshot, warnings: payload.warnings || [] };
}

function validateProfile(profile) {
  if (!profile || typeof profile !== "object") {
    throw new Error("画像必须是 JSON 对象");
  }
  for (const field of ["profile_id", "graph_version", "schema_version"]) {
    if (typeof profile[field] !== "string" || profile[field].trim() === "") {
      throw new Error(`画像缺少 ${field}`);
    }
  }
}

function renderProfileSummary() {
  profileSummary.replaceChildren();
  if (!state.profile) {
    profileSummary.append(textElement("span", "尚未选择画像"));
    return;
  }
  profileSummary.append(
    textElement("strong", state.profile.profile_id),
    textElement("span", `图谱版本 ${state.profile.graph_version}`),
    textElement("span", `画像版本 ${state.profile.schema_version}`),
  );
  if (state.profileWarnings.length > 0) {
    const details = document.createElement("details");
    details.className = "profile-warnings";
    details.append(
      textElement("summary", `适配警告 ${state.profileWarnings.length} 条`),
    );
    const list = document.createElement("ul");
    state.profileWarnings.forEach((warning) => {
      list.append(textElement("li", `${warning.legacy_id}: ${warning.reason}`));
    });
    details.append(list);
    profileSummary.append(details);
  }
}

function resetProfileError() {
  profileError.textContent = "";
}

async function runPlatform() {
  if (!state.profile) return;
  resetProfileError();
  setRunning(true);
  resetPipeline();
  try {
    const executionMode = document.querySelector(
      'input[name="execution-mode"]:checked',
    ).value;
    const topK = Number.parseInt(topKInput.value, 10);
    const idempotencyKey = await buildIdempotencyKey(
      state.profile,
      executionMode,
      topK,
    );
    const response = await fetch("/api/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile: state.profile,
        idempotency_key: idempotencyKey,
        execution_mode: executionMode,
        top_k: topK,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const message = payload.detail?.message || "平台运行失败";
      throw new Error(message);
    }
    state.result = payload;
    renderResult(payload);
  } catch (error) {
    renderClientError(error instanceof Error ? error.message : "平台运行失败");
  } finally {
    setRunning(false);
  }
}

function setRunning(running) {
  runButton.disabled = running || !state.profile;
  runButton.textContent = running ? "正在运行" : "运行课程流程";
  if (running) {
    runStatus.textContent = "执行中";
    document.querySelector('[data-stage="plan_course"]').dataset.state = "active";
    document.querySelector('[data-stage="plan_course"] small').textContent = "执行中";
  }
}

function renderResult(result) {
  runStatus.textContent = statusLabel(result.status);
  runId.textContent = result.run_id;
  renderPipeline(result.steps || [], result.status);
  renderPublicationStatus(result.resources);
  renderPath(result);
  renderEvidence(result);
  renderResources(result);
  rawJson.textContent = JSON.stringify(result, null, 2);
}

function renderPipeline(steps, terminalStatus) {
  resetPipeline();
  const stageState = new Map(steps.map((step) => [step.stage, step.status]));
  document.querySelectorAll(".pipeline-step").forEach((item) => {
    const stage = item.dataset.stage;
    const value = stageState.get(stage);
    if (value) {
      item.dataset.state = value === "failed" ? "failed" : "completed";
      item.querySelector("small").textContent = statusLabel(value);
    }
  });
  if (terminalStatus === "blocked") {
    const generation = document.querySelector('[data-stage="generate_resource"]');
    generation.dataset.state = "failed";
    generation.querySelector("small").textContent = "已阻塞";
  }
}

function resetPipeline() {
  document.querySelectorAll(".pipeline-step").forEach((item) => {
    delete item.dataset.state;
    item.querySelector("small").textContent = "等待";
  });
}

function renderPublicationStatus(resources) {
  if (!resources) {
    publicationStatus.hidden = true;
    publicationStatus.textContent = "";
    return;
  }
  publicationStatus.hidden = false;
  publicationStatus.textContent =
    resources.publication_status === "candidate_draft"
      ? "candidate_draft / 不可发布"
      : "正式资源包";
}

function renderPath(result) {
  const target = document.getElementById("path-view");
  target.replaceChildren();
  const nodes = result.planning?.path?.nodes || [];
  if (nodes.length === 0) {
    target.append(emptyState("本次运行没有生成学习路径"));
    return;
  }
  const table = document.createElement("table");
  table.className = "data-table";
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["顺序", "知识点", "章节 / 小节", "深度", "状态"].forEach((label) => {
    headerRow.append(textElement("th", label));
  });
  head.append(headerRow);
  const body = document.createElement("tbody");
  nodes.forEach((node) => {
    const row = document.createElement("tr");
    if (node.concept_id === result.handoff?.concept_id) row.className = "current-row";
    [
      String(node.sequence),
      node.concept_id,
      `${node.chapter_id} / ${node.section_id}`,
      node.delivery_depth || "-",
      node.status,
    ].forEach((value) => row.append(textElement("td", value)));
    body.append(row);
  });
  table.append(head, body);
  target.append(table);
}

function renderEvidence(result) {
  const target = document.getElementById("evidence-view");
  target.replaceChildren();
  const retrieval = result.retrieval;
  if (!retrieval) {
    target.append(emptyState("本次运行没有检索结果"));
    return;
  }
  target.append(
    evidenceSection("正式证据", retrieval.evidence || []),
    evidenceSection("候选证据", retrieval.candidate_evidence || []),
  );
  if (retrieval.evidence_gap) {
    const gap = document.createElement("div");
    gap.className = "gap-block";
    gap.append(
      textElement("h3", "证据缺口"),
      textElement("p", retrieval.evidence_gap.message),
      textElement(
        "p",
        `缺失类型：${retrieval.evidence_gap.missing_content_kinds.join(", ")}`,
      ),
    );
    target.append(gap);
  }
}

function evidenceSection(title, records) {
  const section = document.createElement("section");
  const heading = document.createElement("div");
  heading.className = "section-heading";
  heading.append(textElement("h2", title), textElement("span", String(records.length)));
  const list = document.createElement("div");
  list.className = "record-list";
  if (records.length === 0) {
    list.append(textElement("p", "无记录"));
  } else {
    records.forEach((record) => {
      const card = document.createElement("article");
      card.className = "record-card";
      const header = document.createElement("header");
      header.append(
        textElement("h3", record.source_title),
        textElement("span", record.content_kind),
      );
      card.append(
        header,
        textElement("p", record.excerpt),
        textElement(
          "p",
          `${record.evidence_status} · ${record.retrieval_method} · ${record.locator}`,
          "record-meta",
        ),
      );
      list.append(card);
    });
  }
  section.append(heading, list);
  return section;
}

function renderResources(result) {
  const target = document.getElementById("resource-view");
  target.replaceChildren();
  if (!result.resources) {
    const block = document.createElement("div");
    block.className = "gap-block";
    block.append(
      textElement("h3", "资源生成未开放"),
      textElement("p", result.evidence_gap?.message || result.failure?.message || "门禁未通过"),
    );
    target.append(block);
    return;
  }
  const stack = document.createElement("div");
  stack.className = "resource-stack";
  if (result.resources.formal_package) {
    result.resources.formal_package.artifacts.forEach((artifact) => {
      stack.append(resourceCard(artifact.resource_type, artifact.items.map((item) => item.text)));
    });
  } else {
    const draft = result.resources.preview_package?.draft;
    if (draft) {
      stack.append(
        resourceCard("lecture", draft.lecture.sections),
        resourceCard("practical_guide", draft.practical_guide.learning_steps),
        resourceCard(
          "assessment",
          draft.student_quiz.items.map((item) => item.prompt),
        ),
      );
    }
  }
  target.append(stack);
}

function resourceCard(title, items) {
  const card = document.createElement("article");
  card.className = "resource-card";
  const header = document.createElement("header");
  header.append(textElement("h3", title));
  const list = document.createElement("ol");
  items.forEach((item) => list.append(textElement("li", item)));
  card.append(header, list);
  return card;
}

function renderClientError(message) {
  runStatus.textContent = "失败";
  const target = document.getElementById("path-view");
  target.replaceChildren();
  const block = document.createElement("div");
  block.className = "error-block";
  block.append(textElement("h3", "运行失败"), textElement("p", message));
  target.append(block);
  activateTab("path-view");
}

function activateTab(targetId) {
  document.querySelectorAll('[role="tab"]').forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.tab === targetId));
  });
  document.querySelectorAll('[role="tabpanel"]').forEach((panel) => {
    panel.hidden = panel.id !== targetId;
  });
}

async function buildIdempotencyKey(profile, executionMode, topK) {
  const canonical = stableStringify({ profile, executionMode, topK });
  const bytes = new TextEncoder().encode(canonical);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `web-${hex}`;
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function statusLabel(status) {
  return {
    pending: "等待",
    planning: "规划中",
    retrieving: "检索中",
    generating: "生成中",
    completed: "已完成",
    blocked: "已阻塞",
    failed: "失败",
  }[status] || status;
}

function emptyState(message) {
  return textElement("div", message, "empty-state");
}

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
