const state = {
  profile: null,
  profileWarnings: [],
  targetConceptId: "",
  selectedConceptId: "",
  result: null,
  assessmentId: null,
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
    ? `本次高亮 ${state.targetConceptId}；课程路径仍保留完整章节顺序。`
    : "未指定目标时运行完整课程路径。";
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
    targetHint.textContent = "未指定目标时运行完整课程路径。";
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
      ? `画像建议目标：${state.targetConceptId}。课程路径仍保留完整章节顺序。`
      : "未指定目标时运行完整课程路径。";
    validateProfile(state.profile);
    runButton.disabled = false;
    renderProfileSummary();
  } catch (error) {
    state.profile = null;
    state.profileWarnings = [];
    state.targetConceptId = "";
    targetConceptInput.value = "";
    targetHint.textContent = "未指定目标时运行完整课程路径。";
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
    state.assessmentId = null;
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
  target.append(buildPathProgress(nodes));
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

function buildPathProgress(nodes) {
  const counts = nodes.reduce((summary, node) => {
    summary[node.status] = (summary[node.status] || 0) + 1;
    return summary;
  }, {});
  const completed = (counts.completed || 0) + (counts.skipped || 0);
  const percent = Math.round((completed / nodes.length) * 100);
  const progress = document.createElement("section");
  progress.id = "path-progress";
  progress.className = "path-progress";
  progress.append(
    textElement("div", "学习路径进度", "progress-label"),
    textElement("strong", `${percent}%`, "progress-value"),
  );
  const track = document.createElement("div");
  track.className = "progress-track";
  const fill = document.createElement("span");
  fill.className = "progress-fill";
  fill.style.width = `${percent}%`;
  track.append(fill);
  progress.append(track);
  const stats = document.createElement("div");
  stats.className = "progress-stats";
  [
    ["已完成", completed, "completed"],
    ["当前", counts.available || 0, "available"],
    ["待学习", counts.pending || 0, "pending"],
    ["受阻", counts.blocked || 0, "blocked"],
  ].forEach(([label, value, status]) => {
    const item = document.createElement("span");
    item.className = `progress-stat progress-${status}`;
    item.append(textElement("strong", String(value)), textElement("small", label));
    stats.append(item);
  });
  progress.append(stats);
  return progress;
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
  const isCurrent = result.handoff?.concept_id === node.concept_id;
  const facts = detailFacts(node);
  if (isCurrent) {
    facts.classList.add("current-facts");
  }
  detail.replaceChildren(
    textElement("span", `节点 ${String(node.sequence).padStart(2, "0")}`, "detail-index"),
    textElement("h2", node.concept_id),
    textElement("p", `${chapterLabel(node.chapter_id)} / ${sectionLabel(node.section_id)}`),
    isCurrent ? textElement("span", "当前学习节点", "current-node-badge") : document.createDocumentFragment(),
    facts,
    node.reason_codes?.length
      ? textElement("p", `规划依据：${node.reason_codes.map(reasonCodeLabel).join("、")}`, "node-reasons")
      : document.createDocumentFragment(),
    textElement("h3", "学习目标"),
    isCurrent && result.handoff.learning_outcomes?.length
      ? textElement("p", result.handoff.learning_outcomes.join("；"))
      : textElement("p", node.status === "skipped" ? "该节点已根据画像掌握度跳过。" : "进入该节点后生成个性化学习目标。"),
    textElement("h3", "前置知识"),
    textElement(
      "p",
      node.blocking_prerequisite_ids?.length
        ? `尚未满足：${node.blocking_prerequisite_ids.join("、")}`
        : node.hard_prerequisite_ids.length
          ? `已满足：${node.hard_prerequisite_ids.join("、")}`
        : "无硬性前置知识",
    ),
  );
  const actions = document.createElement("div");
  actions.className = "node-actions";
  const enter = document.createElement("button");
  enter.type = "button";
  enter.className = "primary-action compact-action";
  const startable = isStartableNode(node);
  enter.textContent = node.status === "available"
    ? "进入学习"
    : node.status === "pending" && startable
      ? "进入该节点"
      : node.status === "blocked"
        ? "存在前置阻塞"
        : "查看学习条件";
  enter.disabled = !startable;
  enter.addEventListener("click", () => {
    if (node.status === "available") {
      activateTab("resource-view");
    } else if (node.status === "pending") {
      startNode(result, node);
    }
  });
  actions.append(enter);
  const assessmentReady = isCurrent && assessmentItemsFor(result).length > 0;
  if (node.status === "available" && result.resources && !assessmentReady) {
    const complete = document.createElement("button");
    complete.type = "button";
    complete.className = "secondary-action compact-action";
    complete.textContent = "完成并进入下一节点";
    complete.addEventListener("click", () => completeCurrentNode(result, node));
    actions.append(complete);
  }
  detail.append(actions);
}

function isStartableNode(node) {
  if (node.status === "blocked") return false;
  if (node.status === "pending") {
    return (node.blocking_prerequisite_ids || []).length === 0;
  }
  return node.status === "available";
}

async function startNode(result, node) {
  const button = document.querySelector(".node-actions .primary-action");
  if (button) {
    button.disabled = true;
    button.textContent = "正在打开节点";
  }
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(result.run_id)}/start-node`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept_id: node.concept_id }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail?.message || "节点暂时无法开始");
    }
    state.result = payload;
    state.assessmentId = null;
    renderResult(payload);
    activateTab("resource-view");
  } catch (error) {
    renderClientError(error instanceof Error ? error.message : "节点暂时无法开始");
  }
}

async function completeCurrentNode(result, node) {
  const button = document.querySelector(".secondary-action");
  if (button) {
    button.disabled = true;
    button.textContent = "正在更新路径";
  }
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(result.run_id)}/complete-node`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept_id: node.concept_id }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail?.message || "节点完成失败");
    }
    state.result = payload;
    renderResult(payload);
    activateTab("path-view");
  } catch (error) {
    renderClientError(error instanceof Error ? error.message : "节点完成失败");
  }
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

function reasonCodeLabel(code) {
  return {
    mastery_skip_threshold_met: "掌握度已达跳过阈值",
    mastery_missing: "缺少掌握度证据",
    mastery_low_confidence: "掌握度置信度偏低",
    ability_incomplete: "能力维度尚未完整",
    hard_prerequisite_below_threshold: "硬性前置掌握度不足",
    hard_prerequisite_unassessed: "硬性前置尚未评估",
    ready_for_intro: "适合入门交付",
    ready_for_intermediate: "适合进阶交付",
    ready_for_advanced: "适合高级交付",
  }[code] || code;
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
  const workbench = document.createElement("div");
  workbench.id = "learning-workbench";
  workbench.className = "learning-workbench";
  target.append(workbench);
  if (!result.resources) {
    const block = document.createElement("div");
    block.className = "gap-block";
    block.append(
      textElement("h3", "资源生成未开放"),
      textElement("p", result.evidence_gap?.message || result.failure?.message || "门禁未通过"),
      textElement("p", "完成审核后重新运行严格模式。", "resource-next-step"),
    );
    workbench.append(
      resourceIdentity(result),
      generationGate(result),
      block,
    );
    return;
  }
  workbench.append(resourceIdentity(result), generationGate(result), resourceRequirements(result));
  const stack = document.createElement("div");
  stack.className = "resource-stack";
  if (result.resources.publication_status === "candidate_draft") {
    const notice = document.createElement("div");
    notice.className = "candidate-notice";
    notice.append(
      textElement("strong", "候选结构草稿"),
      textElement("span", "可用于查看课程结构；正式发布仍需补齐并审核证据。"),
    );
    workbench.append(notice);
  }
  if (result.resources.formal_package) {
    result.resources.formal_package.artifacts.forEach((artifact) => {
      stack.append(resourceCard(artifact.resource_type, artifact.items.map((item) => item.text)));
    });
  } else {
    const draft = result.resources.preview_package?.draft;
    if (draft) {
      stack.append(
        resourceCard(draft.lecture.title || "讲义", draft.lecture.sections, "lecture"),
        resourceCard(
          draft.practical_guide.title || "实操指南",
          [...draft.practical_guide.learning_steps, ...draft.practical_guide.notebook_tasks],
          "practical_guide",
        ),
      );
    }
  }
  const assessmentItems = assessmentItemsFor(result);
  if (assessmentItems.length > 0) {
    stack.append(buildAssessmentForm(result, assessmentItems));
  }
  workbench.append(stack);
}

function resourceIdentity(result) {
  const handoff = result.handoff;
  const resource = result.resources;
  const card = document.createElement("header");
  card.className = "workbench-header";
  const copy = document.createElement("div");
  copy.append(
    textElement("span", "学习工作台", "result-label"),
    textElement("h2", handoff?.concept_id || resource?.concept_id || "当前节点"),
    textElement("p", handoff ? `${chapterLabel(handoff.chapter_id)} / ${sectionLabel(handoff.section_id)} · 第 ${handoff.sequence} 节` : "等待课程交接"),
  );
  const badge = textElement("strong", resource ? `${resource.depth} · ${resource.publication_status === "formal" ? "正式资源" : "候选预览"}` : "资源门禁");
  badge.className = `workbench-badge ${resource?.publication_status === "formal" ? "is-formal" : "is-candidate"}`;
  card.append(copy, badge);
  return card;
}

function generationGate(result) {
  const gate = result.handoff?.generation_gate;
  const evidenceGap = result.evidence_gap || result.retrieval?.evidence_gap;
  const notice = document.createElement("div");
  notice.className = gate?.allowed ? "gate-notice gate-open" : "gate-notice gate-closed";
  notice.append(
    textElement("strong", gate?.allowed ? "资源生成门禁已通过" : "资源生成门禁未完全通过"),
    textElement("span", gate?.allowed ? "当前内容可以进入正式资源流程。" : (evidenceGap?.message || "正式证据仍需审核；当前仅展示候选预览。")),
  );
  return notice;
}

function resourceRequirements(result) {
  const handoff = result.handoff;
  const allocation = handoff?.resource_allocation;
  const box = document.createElement("section");
  box.className = "resource-requirements";
  box.append(textElement("h3", "本节点交付要求"));
  const facts = document.createElement("dl");
  [
    ["学习目标", handoff?.learning_outcomes?.join("；") || "未提供"],
    ["资源类型", handoff?.required_resource_types?.join("、") || "未提供"],
    ["预计时间", allocation ? `${allocation.estimated_minutes} 分钟` : "未提供"],
    ["个性化策略", handoff?.node_adaptation?.support_intensity || "按画像适配"],
    ["代码环境", `${handoff?.presentation_preferences?.code_language || "Python"} / ${handoff?.presentation_preferences?.framework || "通用"}`],
  ].forEach(([label, value]) => facts.append(textElement("dt", label), textElement("dd", value)));
  box.append(facts);
  return box;
}

function assessmentItemsFor(result) {
  const previewItems = result.resources?.preview_package?.draft?.student_quiz?.items;
  if (Array.isArray(previewItems)) {
    return previewItems.map((item) => ({
      questionId: item.question_id,
      prompt: item.prompt,
      difficulty: item.difficulty,
      kind: item.kind,
    }));
  }
  const artifacts = result.resources?.formal_package?.artifacts || [];
  const assessment = artifacts.find((artifact) => artifact.resource_type === "assessment");
  return (assessment?.items || []).map((item, index) => ({
    questionId: `formal-assessment-${index + 1}`,
    prompt: item.text,
    difficulty: null,
    kind: "assessment",
  }));
}

function buildAssessmentForm(result, items) {
  const form = document.createElement("form");
  form.className = "assessment-form";
  form.dataset.startedAt = String(Date.now());
  form.addEventListener("submit", (event) => submitAssessment(event, result, form));
  const heading = document.createElement("header");
  heading.append(
    textElement("h3", "个性化测验"),
    textElement("p", `${items.length} 题 · 通过线 60 分；提交后会更新掌握度和后续节点深度`),
  );
  form.append(heading);
  const questions = document.createElement("ol");
  questions.className = "assessment-questions";
  items.forEach((item) => {
    const question = document.createElement("li");
    question.append(
      textElement("span", item.kind || "assessment", "question-kind"),
      textElement("p", item.prompt),
    );
    questions.append(question);
  });
  form.append(questions);

  const fields = document.createElement("div");
  fields.className = "assessment-fields";
  const score = document.createElement("input");
  score.type = "range";
  score.min = "0";
  score.max = "100";
  score.value = "60";
  score.name = "score";
  const scoreOutput = textElement("output", "60 分");
  score.addEventListener("input", () => {
    scoreOutput.textContent = `${score.value} 分`;
  });
  fields.append(fieldWithLabel("自评得分", score, scoreOutput));

  const hints = document.createElement("input");
  hints.type = "number";
  hints.min = "0";
  hints.max = "20";
  hints.value = "0";
  hints.name = "hint_count";
  fields.append(fieldWithLabel("使用提示次数", hints));

  const attempts = document.createElement("input");
  attempts.type = "number";
  attempts.min = "1";
  attempts.max = "20";
  attempts.value = "1";
  attempts.name = "attempt_count";
  fields.append(fieldWithLabel("尝试次数", attempts));

  const errorKind = document.createElement("select");
  errorKind.name = "error_kind";
  [
    ["", "自动判断"],
    ["concept_confusion", "概念混淆"],
    ["logic_gap", "推理缺口"],
    ["calculation_error", "计算错误"],
    ["missed_condition", "遗漏条件"],
  ].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    errorKind.append(option);
  });
  fields.append(fieldWithLabel("错误类型（未通过时）", errorKind));
  form.append(fields);

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "primary-action compact-action";
  submit.textContent = "提交测验";
  form.append(submit);
  return form;
}

function fieldWithLabel(label, control, output = null) {
  const wrapper = document.createElement("label");
  wrapper.className = "assessment-field";
  wrapper.append(textElement("span", label), control);
  if (output) wrapper.append(output);
  return wrapper;
}

async function submitAssessment(event, result, form) {
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  if (submit) {
    submit.disabled = true;
    submit.textContent = "正在更新画像";
  }
  const data = new FormData(form);
  const score = Number(data.get("score")) / 100;
  const hintCount = Number(data.get("hint_count"));
  const attemptCount = Number(data.get("attempt_count"));
  const errorKind = String(data.get("error_kind") || "");
  const startedAt = Number(form.dataset.startedAt || Date.now());
  const responseTimeMs = Math.max(0, Date.now() - startedAt);
  const assessmentId = state.assessmentId || `web-assessment-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.assessmentId = assessmentId;
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(result.run_id)}/assessment`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assessment_id: assessmentId,
        concept_id: result.handoff.concept_id,
        score,
        response_time_ms: responseTimeMs,
        hint_count: hintCount,
        attempt_count: attemptCount,
        error_kind: score >= 0.6 ? null : errorKind || null,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail?.message || "测验提交失败");
    }
    state.result = payload;
    state.assessmentId = null;
    renderResult(payload);
    activateTab("path-view");
  } catch (error) {
    if (submit) {
      submit.disabled = false;
      submit.textContent = "提交测验";
    }
    renderClientError(error instanceof Error ? error.message : "测验提交失败");
  }
}

function resourceCard(title, items, kind = "resource") {
  const card = document.createElement("article");
  card.className = `resource-card resource-${kind}`;
  const header = document.createElement("header");
  header.append(textElement("h3", title), textElement("span", contentKindLabel(kind), "kind-tag"));
  const list = document.createElement("ol");
  items.forEach((item) => {
    const value = String(item);
    const row = document.createElement("li");
    if (kind === "practical_guide" && /(?:import |torch|nn\.|Conv2d|shape|kernel_size|padding|stride)/i.test(value)) {
      row.className = "resource-code-line";
      row.textContent = value;
    } else {
      row.textContent = value;
    }
    list.append(row);
  });
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
