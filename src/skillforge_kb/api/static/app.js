const state = {
  profile: null,
  profileWarnings: [],
  targetConceptId: "",
  selectedConceptId: "",
  result: null,
};

const profileFile = document.getElementById("profile-file");
const profileSummary = document.getElementById("profile-summary");
const profileError = document.getElementById("profile-error");
const targetConceptInput = document.getElementById("target-concept");
const targetHint = document.getElementById("target-hint");
const runButton = document.getElementById("run-platform");
const topKInput = document.getElementById("top-k");
const runStatus = document.getElementById("run-status");
const runId = document.getElementById("run-id");
const publicationStatus = document.getElementById("publication-status");
const rawJson = document.getElementById("raw-json");

profileFile.addEventListener("change", handleProfileFile);
targetConceptInput.addEventListener("input", () => {
  state.targetConceptId = targetConceptInput.value.trim();
  targetHint.textContent = state.targetConceptId
    ? `本次将规划 ${state.targetConceptId} 及其必要先修节点。`
    : "未指定时运行完整课程路径。";
});
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
    state.targetConceptId = "";
    targetConceptInput.value = "";
    targetHint.textContent = "未指定时运行完整课程路径。";
    runButton.disabled = true;
    renderProfileSummary();
    return;
  }
  try {
    const uploadedProfile = JSON.parse(await file.text());
    const normalized = await normalizeProfile(uploadedProfile);
    state.profile = normalized.snapshot;
    state.profileWarnings = normalized.warnings;
    state.targetConceptId = normalized.suggestedTargetConceptId || "";
    targetConceptInput.value = state.targetConceptId;
    targetHint.textContent = state.targetConceptId
      ? `画像建议目标：${state.targetConceptId}。可手动修改。`
      : "未指定时运行完整课程路径。";
    validateProfile(state.profile);
    runButton.disabled = false;
    renderProfileSummary();
  } catch (error) {
    state.profile = null;
    state.profileWarnings = [];
    state.targetConceptId = "";
    targetConceptInput.value = "";
    targetHint.textContent = "未指定时运行完整课程路径。";
    runButton.disabled = true;
    profileError.textContent = error instanceof Error ? error.message : "画像文件无效";
    renderProfileSummary();
  }
}

async function normalizeProfile(profile) {
  if (profile?.schema_version && profile?.graph_version) {
    return {
      snapshot: profile,
      warnings: [],
      suggestedTargetConceptId: "",
    };
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
  return {
    snapshot: payload.snapshot,
    warnings: payload.warnings || [],
    suggestedTargetConceptId: payload.suggested_target_concept_id || "",
  };
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
  if (state.targetConceptId && !/^[a-z0-9][a-z0-9.-]+$/.test(state.targetConceptId)) {
    throw new Error("目标知识点 ID 格式无效");
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
      state.targetConceptId,
    );
    const response = await fetch("/api/v1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile: state.profile,
        idempotency_key: idempotencyKey,
        execution_mode: executionMode,
        top_k: topK,
        target_concept_id: state.targetConceptId || null,
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
  renderOverview(result);
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
    generation.dataset.state = "blocked";
    generation.querySelector("small").textContent = "已阻塞";
  }
}

function renderOverview(result) {
  const target = document.getElementById("run-overview");
  target.replaceChildren();
  const handoff = result.handoff;
  const retrieval = result.retrieval;
  if (!handoff) {
    target.append(textElement("div", "本次运行没有形成资源交接", "overview-empty"));
    return;
  }
  const cards = [
    overviewCard("当前节点", handoff.concept_id, `${handoff.chapter_id} / ${handoff.section_id}`),
    overviewCard("交付深度", handoff.delivery_depth, `${handoff.sequence} / ${result.planning?.path?.nodes?.length || 0} 个节点`),
    overviewCard("证据状态", retrieval?.evidence?.length ? "正式证据可用" : "等待审核证据", `${retrieval?.evidence?.length || 0} 正式 · ${retrieval?.candidate_evidence?.length || 0} 候选`),
    overviewCard("下一步", result.status === "blocked" ? (result.evidence_gap?.message || "补齐证据") : statusLabel(result.status), result.resources?.publication_status === "candidate_draft" ? "候选草稿，不可发布" : ""),
  ];
  const fragment = document.createDocumentFragment();
  cards.forEach((card) => fragment.append(card));
  target.append(fragment);
}

function overviewCard(label, value, detail) {
  const card = document.createElement("article");
  card.className = "overview-card";
  card.append(textElement("span", label, "overview-label"), textElement("strong", value), textElement("small", detail));
  return card;
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
  const summary = document.createElement("div");
  summary.className = "path-summary";
  const targetConcept = result.planning?.path?.target_concept_id;
  summary.append(
    textElement("strong", targetConcept ? `目标路径：${targetConcept}` : "完整课程路径"),
    textElement("span", `${nodes.length} 个节点 · 当前节点高亮显示`),
  );
  target.append(summary);
  const explorer = document.createElement("div");
  explorer.className = "path-explorer";
  const tree = document.createElement("nav");
  tree.className = "chapter-tree";
  tree.setAttribute("aria-label", "课程章节");
  const groups = groupPathNodes(nodes);
  groups.forEach((chapter) => {
    const chapterBlock = document.createElement("section");
    chapterBlock.className = "chapter-group";
    chapterBlock.append(textElement("h3", chapterLabel(chapter.id)));
    chapter.sections.forEach((section) => {
      const sectionBlock = document.createElement("div");
      sectionBlock.className = "section-group";
      sectionBlock.append(textElement("h4", sectionLabel(section.id)));
      section.nodes.forEach((node) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "node-link";
        button.dataset.status = node.status;
        button.dataset.conceptId = node.concept_id;
        if (node.concept_id === result.planning?.path?.target_concept_id) {
          button.classList.add("target-node");
        }
        button.setAttribute("aria-pressed", "false");
        button.append(
          textElement("span", String(node.sequence).padStart(2, "0"), "node-sequence"),
          textElement("span", node.concept_id, "node-name"),
          textElement("span", nodeStatusLabel(node.status), "node-status"),
        );
        button.addEventListener("click", () => selectPathNode(result, node));
        sectionBlock.append(button);
      });
      chapterBlock.append(sectionBlock);
    });
    tree.append(chapterBlock);
  });
  const detail = document.createElement("section");
  detail.className = "node-detail";
  detail.id = "node-detail";
  explorer.append(tree, detail);
  target.append(explorer);
  const initial = nodes.find((node) => node.concept_id === result.planning?.path?.target_concept_id)
    || nodes.find((node) => node.concept_id === result.handoff?.concept_id)
    || nodes.find((node) => node.status === "available")
    || nodes[0];
  selectPathNode(result, initial);
}

function groupPathNodes(nodes) {
  const chapters = [];
  const chapterMap = new Map();
  nodes.forEach((node) => {
    let chapter = chapterMap.get(node.chapter_id);
    if (!chapter) {
      chapter = { id: node.chapter_id, sections: [], sectionMap: new Map() };
      chapterMap.set(node.chapter_id, chapter);
      chapters.push(chapter);
    }
    let section = chapter.sectionMap.get(node.section_id);
    if (!section) {
      section = { id: node.section_id, nodes: [] };
      chapter.sectionMap.set(node.section_id, section);
      chapter.sections.push(section);
    }
    section.nodes.push(node);
  });
  return chapters;
}

function selectPathNode(result, node) {
  state.selectedConceptId = node.concept_id;
  document.querySelectorAll(".node-link").forEach((button) => {
    const selected = button.dataset.conceptId === node.concept_id;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  const detail = document.getElementById("node-detail");
  if (!detail) return;
  detail.replaceChildren(
    textElement("span", `节点 ${String(node.sequence).padStart(2, "0")}`, "detail-index"),
    textElement("h2", node.concept_id),
    textElement("p", `${chapterLabel(node.chapter_id)} / ${sectionLabel(node.section_id)}`),
    detailFacts(node),
    textElement("h3", "前置知识"),
    textElement(
      "p",
      node.hard_prerequisite_ids.length
        ? node.hard_prerequisite_ids.join("、")
        : "无硬性前置知识",
    ),
  );
  const actions = document.createElement("div");
  actions.className = "node-actions";
  const enter = document.createElement("button");
  enter.type = "button";
  enter.className = "primary-action compact-action";
  enter.textContent = node.status === "available" ? "进入学习" : "查看学习条件";
  enter.disabled = node.status === "blocked" || node.status === "pending";
  enter.addEventListener("click", () => {
    if (node.status === "available") activateTab("resource-view");
  });
  actions.append(enter);
  detail.append(actions);
}

function detailFacts(node) {
  const facts = document.createElement("dl");
  facts.className = "detail-facts";
  [["状态", nodeStatusLabel(node.status)], ["交付深度", node.delivery_depth || "已掌握"], ["目标顺序", String(node.sequence)]].forEach(([label, value]) => {
    facts.append(textElement("dt", label), textElement("dd", value));
  });
  return facts;
}

function chapterLabel(id) {
  return id.replace(/^chapter\.(\d+)\./, "第 $1 章 · ").replaceAll("-", " ");
}

function sectionLabel(id) {
  return id.replace(/^section\.\d+\./, "").replaceAll("-", " ");
}

function nodeStatusLabel(status) {
  return { skipped: "已掌握", available: "当前", blocked: "受阻", pending: "待学习", completed: "已完成" }[status] || status;
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
  const summary = document.createElement("div");
  summary.className = "evidence-summary-strip";
  summary.append(
    textElement("strong", `${retrieval.evidence_summary.formal_count} 正式`),
    textElement("span", `${retrieval.evidence_summary.candidate_count} 候选`),
    textElement("span", retrieval.evidence_summary.missing_content_kinds.length ? `缺失正式证据：${retrieval.evidence_summary.missing_content_kinds.join("、")}` : "正式证据类型齐全"),
  );
  target.prepend(summary);
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
        textElement("span", contentKindLabel(record.content_kind), "kind-tag"),
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

function contentKindLabel(kind) {
  return { definition: "定义", code: "代码", exercise: "练习" }[kind] || kind;
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
      textElement("p", "完成审核后重新运行严格模式。", "resource-next-step"),
    );
    target.append(block);
    return;
  }
  const stack = document.createElement("div");
  stack.className = "resource-stack";
  if (result.resources.publication_status === "candidate_draft") {
    const notice = document.createElement("div");
    notice.className = "candidate-notice";
    notice.append(
      textElement("strong", "候选结构草稿"),
      textElement("span", "可用于查看课程结构；正式发布仍需补齐并审核证据。"),
    );
    stack.append(notice);
  }
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

async function buildIdempotencyKey(profile, executionMode, topK, targetConceptId) {
  const canonical = stableStringify({ profile, executionMode, topK, targetConceptId });
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
