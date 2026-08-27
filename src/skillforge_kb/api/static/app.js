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
const profileJsonInput = document.getElementById("profile-json-input");
const loadProfileJsonButton = document.getElementById("load-profile-json");
const profileJsonStatus = document.getElementById("profile-json-status");

profileFile.addEventListener("change", handleProfileFile);
targetConceptInput.addEventListener("input", () => {
  state.targetConceptId = targetConceptInput.value.trim();
  targetHint.textContent = state.targetConceptId
    ? `本次高亮 ${state.targetConceptId}；课程路径仍保留完整章节顺序。`
    : "未指定目标时运行完整课程路径。";
});
runButton.addEventListener("click", runPlatform);
loadProfileJsonButton.addEventListener("click", runPastedProfile);
document.querySelectorAll('[role="tab"]').forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});
document.getElementById("evidence-search-btn").addEventListener("click", runEvidenceSearch);
document.getElementById("evidence-query").addEventListener("keydown", (event) => {
  if (event.key === "Enter") runEvidenceSearch();
});

void consumeDiagnosisHandoff();

async function consumeDiagnosisHandoff() {
  const handoffKey = "skillforge.pendingProfile.v1";
  let raw;
  try {
    raw = sessionStorage.getItem(handoffKey);
    if (!raw) return;
    sessionStorage.removeItem(handoffKey);
  } catch (_error) {
    return;
  }
  try {
    const handoff = JSON.parse(raw);
    const createdAt = Number(handoff?.created_at);
    if (!handoff?.profile || !Number.isFinite(createdAt) || Date.now() - createdAt > 15 * 60 * 1000) {
      throw new Error("诊断画像交接已失效，请重新完成学情诊断");
    }
    const normalized = await normalizeProfile(handoff.profile);
    state.profile = normalized.snapshot;
    state.profileWarnings = normalized.warnings;
    state.targetConceptId = "";
    targetConceptInput.value = "";
    targetHint.textContent = "诊断已完成，正在生成完整课程路径。";
    validateProfile(state.profile);
    renderProfileSummary();
    profileError.textContent = "已接收学情诊断结果，正在生成完整课程路径...";
    await runPlatform();
  } catch (error) {
    state.profile = null;
    state.profileWarnings = [];
    runButton.disabled = true;
    profileError.textContent = error instanceof Error ? error.message : "诊断画像交接失败";
    renderProfileSummary();
  }
}

async function runPastedProfile() {
  resetProfileError();
  if (!profileJsonInput.value.trim()) {
    profileJsonStatus.textContent = "请先粘贴画像 JSON";
    return;
  }
  loadProfileJsonButton.disabled = true;
  profileJsonStatus.textContent = "正在校验画像...";
  try {
    const pasted = JSON.parse(profileJsonInput.value);
    const normalized = await normalizeProfile(pasted?.profile || pasted);
    state.profile = normalized.snapshot;
    state.profileWarnings = normalized.warnings;
    state.targetConceptId = "";
    targetConceptInput.value = "";
    targetHint.textContent = "未指定目标时运行完整课程路径。";
    validateProfile(state.profile);
    renderProfileSummary();
    runButton.disabled = false;
    profileJsonStatus.textContent = "画像已载入，正在生成完整课程路径...";
    await runPlatform();
  } catch (error) {
    state.profile = null;
    state.profileWarnings = [];
    runButton.disabled = true;
    renderProfileSummary();
    profileJsonStatus.textContent = "画像载入失败";
    profileError.textContent = error instanceof Error ? error.message : "画像 JSON 无效";
  } finally {
    loadProfileJsonButton.disabled = false;
  }
}

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
    const groups = groupProfileWarnings(state.profileWarnings);
    const details = document.createElement("details");
    details.className = "profile-warnings";
    details.append(
      textElement("summary", "画像转换摘要"),
    );
    const summary = document.createElement("p");
    summary.className = "profile-conversion-summary";
    const facts = [
      `${state.profile.knowledge_mastery.length} 项已映射到课程图谱`,
      groups.unmapped.length ? `${groups.unmapped.length} 项暂未纳入当前图谱` : null,
      groups.unassessed.length ? `${groups.unassessed.length} 项未测评，不使用其数值` : null,
      groups.version.length ? "图谱版本已自动匹配" : null,
    ].filter(Boolean);
    summary.textContent = facts.join("；");
    details.append(summary);
    const list = document.createElement("ul");
    [...groups.unmapped, ...groups.unassessed, ...groups.other].forEach((warning) => {
      list.append(textElement("li", profileWarningLabel(warning)));
    });
    if (list.children.length) details.append(list);
    profileSummary.append(details);
  }
}

function groupProfileWarnings(warnings) {
  const groups = { version: [], unmapped: [], unassessed: [], other: [] };
  warnings.forEach((warning) => {
    const reason = String(warning.reason || "");
    if (reason.includes("graph_version inferred")) groups.version.push(warning);
    else if (reason.includes("unmapped") || reason.includes("composite")) groups.unmapped.push(warning);
    else if (reason.includes("numeric mastery discarded")) groups.unassessed.push(warning);
    else groups.other.push(warning);
  });
  return groups;
}

function profileWarningLabel(warning) {
  const reason = String(warning.reason || "");
  if (reason.includes("numeric mastery discarded")) {
    return `${warning.legacy_id}：画像标记为未测评，掌握度数值不参与个性化决策。`;
  }
  if (reason.includes("error pattern references unmapped")) {
    return `${warning.legacy_id}：对应错误模式未纳入当前课程图谱。`;
  }
  return `${warning.legacy_id}：该知识点暂未纳入当前课程图谱，因此不参与路径决策。`;
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
    isCurrent ? personalizationPanel(result) : document.createDocumentFragment(),
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

function personalizationPanel(result) {
  const adaptation = result.handoff?.node_adaptation || result.planning?.current_adaptation;
  if (!adaptation) return document.createDocumentFragment();
  const section = document.createElement("section");
  section.className = "personalization-panel";
  section.append(textElement("h3", "个性化计算"));
  const readiness = Math.round((adaptation.readiness_score || 0) * 100);
  const support = Math.round((adaptation.support_need_score || 0) * 100);
  section.append(
    textElement("p", `当前交付深度为 ${adaptation.delivery_depth}；准备度 ${readiness}%；学习支持强度为 ${support}%（${supportIntensityLabel(adaptation.support_intensity)}）。`),
  );
  const factors = document.createElement("ul");
  const labels = {
    mastery_gap: "掌握度缺口",
    error_risk: "错误风险",
    ability_gap: "能力匹配缺口",
    conservative_evidence_floor: "证据不足保护项",
  };
  (adaptation.support_contributions || []).forEach((item) => {
    const contribution = Math.round(item.contribution * 100);
    factors.append(textElement("li", `${labels[item.factor] || item.factor}：${contribution}%`));
  });
  section.append(factors);
  return section;
}

function supportIntensityLabel(value) {
  return {
    compact: "紧凑",
    standard: "标准",
    scaffolded: "分步引导",
    remediation: "补救学习",
  }[value] || value || "标准";
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
  const target = document.getElementById("evidence-results");
  target.replaceChildren();
  const retrieval = result.retrieval;
  if (!retrieval) {
    target.append(emptyState("本次运行没有检索结果"));
    return;
  }
  target.append(
    retrievalGuide(result, retrieval),
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
      list.append(evidenceCard({
        sourceTitle: record.source_title,
        contentKind: record.content_kind,
        headingPath: record.heading_path,
        body: record.excerpt || record.text || "",
        meta: [
          record.evidence_status,
          record.retrieval_method,
          record.locator,
          typeof record.score === "number" ? `score ${record.score.toFixed(3)}` : null,
        ],
      }));
    });
  }
  section.append(heading, list);
  return section;
}

function evidenceCard({ sourceTitle, contentKind, headingPath, body, meta }) {
  const card = document.createElement("article");
  card.className = "record-card";
  const header = document.createElement("header");
  const titleLine = document.createElement("div");
  titleLine.className = "record-title";
  titleLine.append(textElement("h3", sourceTitle));
  if (contentKind) {
    titleLine.append(textElement("span", contentKindLabel(contentKind), "kind-tag"));
  }
  header.append(titleLine);
  if (Array.isArray(headingPath) && headingPath.length) {
    header.append(textElement("p", headingPath.join(" / "), "record-path"));
  }
  card.append(
    header,
    textElement("p", truncate(body, 420)),
    textElement("p", meta.filter(Boolean).join(" · "), "record-meta"),
  );
  return card;
}

function truncate(text, limit) {
  const value = String(text || "");
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

async function runEvidenceSearch() {
  const input = document.getElementById("evidence-query");
  const statusEl = document.getElementById("evidence-search-status");
  const button = document.getElementById("evidence-search-btn");
  const query = input.value.trim();
  if (!query) {
    statusEl.textContent = "请输入检索内容。";
    return;
  }
  button.disabled = true;
  button.textContent = "检索中";
  statusEl.textContent = "正在检索…";
  try {
    const response = await fetch("/api/v1/retrieval/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: 10 }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail?.message || "检索失败");
    }
    renderSearchResults(query, payload);
    if (payload.status === "unavailable") {
      statusEl.textContent = payload.error_message || "检索失败";
      return;
    }
    statusEl.textContent = payload.hits?.length
      ? `返回 ${payload.hits.length} 条候选片段。`
      : "知识库中没有匹配的候选片段。";
  } catch (error) {
    statusEl.textContent = error instanceof Error ? error.message : "检索失败";
  } finally {
    button.disabled = false;
    button.textContent = "检索";
  }
}

function renderSearchResults(query, payload) {
  const target = document.getElementById("evidence-results");
  target.replaceChildren();
  const hits = payload.hits || [];
  const section = document.createElement("section");
  const heading = document.createElement("div");
  heading.className = "section-heading";
  heading.append(
    textElement("h2", "检索结果"),
    textElement("span", `“${query}” · ${hits.length} 条`),
  );
  section.append(heading);
  if (!hits.length) {
    section.append(textElement("p", "知识库中没有匹配的候选片段，试试更通用的关键词。"));
  } else {
    const list = document.createElement("div");
    list.className = "record-list";
    hits.forEach((hit) => {
      list.append(evidenceCard({
        sourceTitle: hit.source_title,
        contentKind: null,
        headingPath: hit.heading_path,
        body: hit.text,
        meta: ["candidate", "bm25", `score ${(hit.score ?? 0).toFixed(3)}`, hit.chunk_id],
      }));
    });
    section.append(list);
  }
  target.append(section);
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
    stack.append(buildFormalLearningTabs(result, result.resources.formal_package.artifacts));
  } else {
    const draft = result.resources.preview_package?.draft;
    if (draft) {
      stack.append(buildLearningTabs(result, draft));
    }
  }
  workbench.append(stack);
}

function retrievalGuide(result, retrieval) {
  const guide = document.createElement("section");
  guide.className = "retrieval-guide";
  guide.append(textElement("h2", "领域检索如何参与学习"));
  const conceptId = result.handoff?.concept_id || retrieval.request.concept_id;
  guide.append(
    textElement("p", `课程图谱先定位当前知识点“${conceptLabel(conceptId)}”及其章节、先修关系和交付深度；文本库再按定义、代码、练习三类检索候选片段。`),
    textElement("p", `本次每类候选证据上限为 ${retrieval.request.top_k} 条。候选片段可以辅助生成学习资源；只有已审核且许可合规的正式证据才能进入正式资源模式。`),
  );
  return guide;
}

function buildFormalLearningTabs(result, artifacts) {
  const byType = Object.fromEntries(
    (Array.isArray(artifacts) ? artifacts : []).map((artifact) => [artifact.resource_type, artifact]),
  );
  const lecture = byType.lecture;
  const practical = byType.practical_guide;
  const assessment = byType.assessment;
  const lesson = {
    title: lecture?.title || "课程讲义",
    blocks: (lecture?.items || []).map((item, index) => ({
      kind: index === 0 ? "objective" : index === (lecture.items.length - 1) ? "summary" : "definition",
      title: item.title || `学习内容 ${index + 1}`,
      body: item.text || item.excerpt || "当前讲义内容暂不可用。",
      code: item.code || null,
    })),
  };
  if (!lesson.blocks.length) {
    lesson.blocks.push({
      kind: "summary",
      title: "讲义内容待补齐",
      body: "当前节点尚未生成可展示的讲义条目，请返回课程规划检查资源类型和证据门禁。",
    });
  }
  const projectRequirement = result.handoff?.required_resource_types?.includes("project")
    ? "项目实践要求：将当前知识点应用到一个最小可验证任务，提交代码、关键结果、失败原因与改进说明。"
    : null;
  const practice = {
    title: practical?.title || "代码实践",
    learning_steps: [
      ...(practical?.items || []).map((item) => item.text || item.excerpt || ""),
      ...(projectRequirement ? [projectRequirement] : []),
    ].filter(Boolean),
    notebook_tasks: [],
    exercise: {
      language: "python",
      task: projectRequirement || "根据本节讲义完成一个最小可运行示例，并在编辑器中记录输入、输出与解释。",
      starter_code: "# TODO: 根据讲义完成当前知识点的最小实现\nresult = None\nprint(result)\n",
      expected_output: "请根据讲义中的示例填写并解释输出。",
      checks: ["代码包含输入与结果", "打印结果", "解释结果与知识点的关系"],
      required_tokens: ["result", "print"],
    },
  };
  const shell = document.createElement("section");
  shell.className = "learning-tabs";
  const tabList = document.createElement("div");
  tabList.className = "learning-tab-list";
  tabList.setAttribute("role", "tablist");
  const panel = document.createElement("div");
  panel.className = "learning-tab-panel";
  const tabs = [
    ["lesson", "讲义", () => buildLessonPanel(lesson)],
    ["practice", "实践", () => buildPracticePanel(result, practice)],
    ["assessment", "测验", () => buildAssessmentPanel(result)],
  ];
  const show = (key) => {
    panel.replaceChildren();
    tabs.forEach(([tabKey, label, build]) => {
      const button = tabList.querySelector(`[data-learning-tab="${tabKey}"]`);
      button?.classList.toggle("is-active", tabKey === key);
      button?.setAttribute("aria-selected", String(tabKey === key));
      if (tabKey === key) panel.append(build());
    });
  };
  tabs.forEach(([key, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "learning-tab";
    button.dataset.learningTab = key;
    button.setAttribute("role", "tab");
    button.textContent = label;
    button.addEventListener("click", () => show(key));
    tabList.append(button);
  });
  shell.append(tabList, panel);
  show("lesson");
  return shell;
}

function buildLearningTabs(result, draft) {
  const shell = document.createElement("section");
  shell.className = "learning-tabs";
  const tabList = document.createElement("div");
  tabList.className = "learning-tab-list";
  tabList.setAttribute("role", "tablist");
  const panel = document.createElement("div");
  panel.className = "learning-tab-panel";
  const tabs = [
    ["lesson", "讲义", () => buildLessonPanel(draft.lecture)],
    ["practice", "实践", () => buildPracticePanel(result, draft.practical_guide)],
    ["assessment", "测验", () => buildAssessmentPanel(result)],
  ];
  const show = (key) => {
    panel.replaceChildren();
    tabs.forEach(([tabKey, label, build]) => {
      const button = tabList.querySelector(`[data-learning-tab="${tabKey}"]`);
      button?.classList.toggle("is-active", tabKey === key);
      button?.setAttribute("aria-selected", String(tabKey === key));
      if (tabKey === key) panel.append(build());
    });
  };
  tabs.forEach(([key, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "learning-tab";
    button.dataset.learningTab = key;
    button.setAttribute("role", "tab");
    button.textContent = label;
    button.addEventListener("click", () => show(key));
    tabList.append(button);
  });
  shell.append(tabList, panel);
  show("lesson");
  return shell;
}

function buildLessonPanel(lecture) {
  const article = document.createElement("article");
  article.className = "lesson-article";
  article.append(textElement("h2", lecture.title));
  const blocks = Array.isArray(lecture.blocks) && lecture.blocks.length
    ? lecture.blocks
    : (lecture.sections || []).map((body, index) => ({ kind: "summary", title: `学习要点 ${index + 1}`, body }));
  blocks.forEach((block, index) => {
    const section = document.createElement("section");
    section.className = `lesson-block lesson-${block.kind || "summary"}`;
    const folio = textElement("span", String(index + 1).padStart(2, "0"), "lesson-folio");
    const copy = document.createElement("div");
    copy.append(textElement("h3", block.title), textElement("p", block.body));
    if (block.code) copy.append(codeBlock(block.code));
    section.append(folio, copy);
    article.append(section);
  });
  return article;
}

function buildPracticePanel(result, guide) {
  const exercise = guide.exercise;
  if (!exercise) {
    const section = document.createElement("section");
    section.className = "practice-lab practice-steps-only";
    section.append(textElement("h2", guide.title || "代码实践"));
    const steps = document.createElement("ol");
    [...(guide.learning_steps || []), ...(guide.notebook_tasks || [])].forEach((step) => {
      steps.append(textElement("li", step));
    });
    if (!steps.children.length) {
      steps.append(textElement("li", "当前节点暂未提供实践步骤，请检查资源生成结果。"));
    }
    section.append(steps);
    return section;
  }
  const section = document.createElement("section");
  section.className = "practice-lab";
  const header = document.createElement("header");
  header.append(textElement("h2", guide.title || "代码实践"), textElement("p", exercise.task));
  const grid = document.createElement("div");
  grid.className = "practice-grid";
  const editor = document.createElement("textarea");
  editor.className = "code-editor";
  editor.name = "practice-source";
  editor.spellcheck = false;
  editor.value = exercise.starter_code;
  editor.setAttribute("aria-label", "Python 代码编辑器");
  const side = document.createElement("aside");
  side.className = "practice-notes";
  side.append(
    textElement("h3", "预期观察"),
    codeBlock(exercise.expected_output),
    textElement("h3", "检查清单"),
  );
  const checks = document.createElement("ul");
  (exercise.checks || []).forEach((check) => checks.append(textElement("li", check)));
  side.append(checks);
  grid.append(editor, side);
  const actions = document.createElement("div");
  actions.className = "practice-actions";
  const review = document.createElement("button");
  review.type = "button";
  review.className = "primary-action compact-action";
  review.textContent = "检查代码";
  const feedback = document.createElement("div");
  feedback.className = "practice-feedback";
  review.addEventListener("click", () => submitPracticeReview(result, editor, review, feedback));
  actions.append(review, textElement("span", "代码只作静态分析，不会在服务器执行。", "practice-safety"));
  section.append(header, grid, actions, feedback);
  return section;
}

async function submitPracticeReview(result, editor, button, feedback) {
  button.disabled = true;
  button.textContent = "正在检查";
  feedback.replaceChildren();
  try {
    const response = await fetch(`/api/v1/runs/${encodeURIComponent(result.run_id)}/practice-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept_id: result.handoff.concept_id, source: editor.value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail?.message || "代码检查失败");
    feedback.classList.toggle("is-passed", payload.accepted);
    feedback.classList.toggle("is-needs-revision", !payload.accepted);
    feedback.append(
      textElement("strong", payload.accepted ? "静态检查通过" : "请修改后再试"),
      textElement("p", payload.feedback),
    );
    if (payload.issues?.length) {
      const issues = document.createElement("ul");
      payload.issues.forEach((issue) => issues.append(textElement("li", issue.message)));
      feedback.append(issues);
    }
    feedback.append(textElement("p", `下一步：${payload.next_step}`, "practice-next-step"));
  } catch (error) {
    feedback.className = "practice-feedback is-needs-revision";
    feedback.append(textElement("p", error instanceof Error ? error.message : "代码检查失败"));
  } finally {
    button.disabled = false;
    button.textContent = "检查代码";
  }
}

function buildAssessmentPanel(result) {
  const items = assessmentItemsFor(result);
  if (!items.length) return emptyState("当前节点没有可用测验题目");
  return buildAssessmentForm(result, items);
}

function codeBlock(value) {
  const pre = document.createElement("pre");
  pre.className = "resource-code-line";
  pre.textContent = value;
  return pre;
}

function conceptLabel(conceptId) {
  const labels = {
    "math.linear-algebra.scalar": "标量",
    "math.linear-algebra.vector": "向量",
    "math.linear-algebra.matrix": "矩阵",
    "math.linear-algebra.tensor": "张量",
    "dl.cnn.convolution": "卷积运算",
    "dl.cnn.cross-correlation": "互相关",
  };
  return labels[conceptId] || conceptId.split(".").at(-1).replaceAll("-", " ");
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
  const badge = textElement("strong", resource ? `${resource.depth} · ${resource.publication_status === "formal" ? "正式资源" : "学习演示资源"}` : "资源审核状态");
  badge.className = `workbench-badge ${resource?.publication_status === "formal" ? "is-formal" : "is-candidate"}`;
  card.append(copy, badge);
  return card;
}

function generationGate(result) {
  const gate = result.handoff?.generation_gate;
  const evidenceGap = result.evidence_gap || result.retrieval?.evidence_gap;
  const notice = document.createElement("div");
  if (result.resources?.publication_status === "candidate_draft") {
    notice.className = "gate-notice gate-candidate";
    notice.append(
      textElement("strong", "演示学习资源已生成"),
      textElement("span", "当前资源基于课程图谱和候选证据生成，可用于学习、实践与测验；未作为正式发布资料。"),
    );
    return notice;
  }
  notice.className = gate?.allowed ? "gate-notice gate-open" : "gate-notice gate-closed";
  notice.append(
    textElement("strong", gate?.allowed ? "正式资源证据已就绪" : "正式资源待证据审核"),
    textElement("span", gate?.allowed ? "当前内容可生成正式发布资源。" : (evidenceGap?.message || "当前知识点缺少已审核、许可合规的正式证据。")),
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
      choices: item.choices || [],
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
    if (item.choices?.length) {
      const choices = document.createElement("div");
      choices.className = "quiz-choices";
      item.choices.forEach((choice, index) => {
        const label = document.createElement("label");
        label.className = "quiz-choice";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `answer-${item.questionId}`;
        input.value = String(index);
        input.required = true;
        label.append(input, textElement("span", choice));
        choices.append(label);
      });
      question.append(choices);
    }
    questions.append(question);
  });
  form.append(questions);

  const fields = document.createElement("div");
  fields.className = "assessment-fields";
  const hasChoices = items.some((item) => item.choices?.length);
  if (!hasChoices) {
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
  }

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
  const hintCount = Number(data.get("hint_count"));
  const attemptCount = Number(data.get("attempt_count"));
  const errorKind = String(data.get("error_kind") || "");
  const responses = {};
  form.querySelectorAll('input[type="radio"]:checked').forEach((input) => {
    responses[input.name.replace("answer-", "")] = Number(input.value);
  });
  const hasSelectedResponses = Object.keys(responses).length > 0;
  const score = hasSelectedResponses ? null : Number(data.get("score") || 0) / 100;
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
        error_kind: hasSelectedResponses || score >= 0.6 ? null : errorKind || null,
        responses,
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
