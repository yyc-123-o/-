from __future__ import annotations

# The HTML/CSS/JavaScript template intentionally preserves browser-readable lines.
# ruff: noqa: E501
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from skillforge_kb.binding.matcher import build_candidate_bindings
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import RelationKind
from skillforge_kb.planning.ordering import stable_required_concept_ids
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "resources" / "ontology"
OUTPUT = ROOT / "reports" / "generated" / "course-graph-visualization.html"
LOGIC_OUTPUT = ROOT / "reports" / "generated" / "course-graph-logic-report.json"


def graph_payload(
    catalog: OntologyCatalog,
    resource_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    chapters = catalog.chapters()
    sections = {section.id: section for section in catalog.course_document.sections}
    chapter_by_id = {chapter.id: chapter for chapter in chapters}
    concepts = catalog.concepts()
    resource_bindings = resource_bindings or []
    resource_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in resource_bindings:
        resource_by_concept[str(binding["concept_id"])].append(binding)
    positions = {
        concept_id: index
        for index, concept_id in enumerate(stable_required_concept_ids(catalog), start=1)
    }

    chapter_nodes: list[dict[str, Any]] = []
    section_nodes: list[dict[str, Any]] = []
    concept_nodes: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_nodes.append({
            "id": chapter.id,
            "type": "chapter",
            "order": chapter.order,
            "label": chapter.title.zh,
            "labelEn": chapter.title.en,
            "summary": chapter.summary,
            "core": chapter.core,
            "conceptCount": sum(
                1 for concept in concepts
                if sections[catalog.section_for(concept.id).id].chapter_id == chapter.id
            ),
        })
    for section in sorted(sections.values(), key=lambda item: (item.chapter_id, item.order)):
        section_nodes.append({
            "id": section.id,
            "type": "section",
            "chapterId": section.chapter_id,
            "order": section.order,
            "label": section.title.zh,
            "labelEn": section.title.en,
        })
    for concept in concepts:
        section = catalog.section_for(concept.id)
        chapter = chapter_by_id[section.chapter_id]
        concept_nodes.append({
            "id": concept.id,
            "type": "concept",
            "chapterId": chapter.id,
            "sectionId": section.id,
            "order": positions[concept.id],
            "label": concept.names.zh,
            "labelEn": concept.names.en,
            "difficulty": concept.difficulty,
            "required": concept.required,
            "summary": concept.summary,
            "resourceCount": len(resource_by_concept.get(concept.id, [])),
        })

    edges: list[dict[str, Any]] = []
    for assignment in catalog.course_document.teaches:
        edges.append({
            "source": assignment.section_id,
            "target": assignment.concept_id,
            "kind": "teaches",
        })
    for section in sections.values():
        edges.append({
            "source": section.chapter_id,
            "target": section.id,
            "kind": "contains",
        })
    for relation in catalog.relations():
        edges.append({
            "source": relation.source,
            "target": relation.target,
            "kind": relation.kind.value,
            "minMastery": relation.min_mastery,
        })
    chapter_links: dict[tuple[str, str], int] = defaultdict(int)
    for relation in catalog.relations(RelationKind.HARD_PREREQUISITE):
        source_chapter = catalog.section_for(relation.source).chapter_id
        target_chapter = catalog.section_for(relation.target).chapter_id
        if source_chapter != target_chapter:
            chapter_links[(source_chapter, target_chapter)] += 1
    for (source_chapter, target_chapter), count in sorted(chapter_links.items()):
        edges.append(
            {
                "source": source_chapter,
                "target": target_chapter,
                "kind": "chapter_prerequisite",
                "count": count,
            }
        )

    logic = logic_report(catalog, positions)
    logic["candidateBindingCount"] = len(resource_bindings)
    logic["boundConceptCount"] = sum(
        1 for concept in concepts if resource_by_concept.get(concept.id)
    )
    return {
        "version": catalog.course_document.version,
        "chapters": chapter_nodes,
        "sections": section_nodes,
        "concepts": concept_nodes,
        "edges": edges,
        "resourceBindings": resource_bindings,
        "logic": logic,
    }


def logic_report(catalog: OntologyCatalog, positions: dict[str, int]) -> dict[str, Any]:
    concepts = catalog.concepts()
    concept_ids = {concept.id for concept in concepts}
    hard_edges = [
        (relation.source, relation.target)
        for relation in catalog.relations(RelationKind.HARD_PREREQUISITE)
    ]
    incoming = defaultdict(list[str])
    outgoing = defaultdict(list[str])
    for source, target in hard_edges:
        incoming[target].append(source)
        outgoing[source].append(target)
    roots = sorted(concept_ids - set(incoming))
    leaves = sorted(concept_ids - set(outgoing))
    reverse_edges = []
    for source, target in hard_edges:
        if positions[source] >= positions[target]:
            reverse_edges.append(
                {
                    "source": source,
                    "target": target,
                    "sourceOrder": positions[source],
                    "targetOrder": positions[target],
                }
            )
    cycles = find_cycles(concept_ids, outgoing)
    isolated = sorted(
        concept_ids - set(incoming) - set(outgoing)
    )
    cross_chapter = []
    for source, target in hard_edges:
        source_chapter = catalog.section_for(source).chapter_id
        target_chapter = catalog.section_for(target).chapter_id
        if source_chapter != target_chapter:
            cross_chapter.append({
                "source": source,
                "target": target,
                "sourceChapter": source_chapter,
                "targetChapter": target_chapter,
            })
    return {
        "conceptCount": len(concepts),
        "hardPrerequisiteCount": len(hard_edges),
        "roots": roots,
        "leaves": leaves,
        "reverseOrderEdges": reverse_edges,
        "cycles": cycles,
        "isolatedConcepts": isolated,
        "crossChapterPrerequisites": cross_chapter,
    }


def find_cycles(nodes: set[str], outgoing: dict[str, list[str]]) -> list[list[str]]:
    state: dict[str, int] = {node: 0 for node in nodes}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for target in outgoing[node]:
            if state[target] == 0:
                visit(target)
            elif state[target] == 1 and target in stack:
                start = stack.index(target)
                cycles.append([*stack[start:], target])
        stack.pop()
        state[node] = 2

    for node in sorted(nodes):
        if state[node] == 0:
            visit(node)
    return cycles


def render_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).translate(
        str.maketrans({"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"})
    )
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SkillForge Course Graph</title>
<style>
:root {{ color-scheme: light; --ink:#17212b; --muted:#637083; --line:#d7dee7; --panel:#ffffff; --bg:#f4f7fa; --blue:#1f6feb; --blue-soft:#e7f0ff; --amber:#b46900; --amber-soft:#fff4d6; --red:#b42318; --red-soft:#fff0ee; --green:#16805d; --green-soft:#e5f6ef; --resource:#d97745; --resource-soft:#fff0e8; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font-family:Inter,Segoe UI,Microsoft YaHei,sans-serif; background:var(--bg); color:var(--ink); }}
header {{ padding:26px 32px 20px; border-bottom:1px solid var(--line); background:var(--panel); }}
h1 {{ margin:0 0 6px; font-size:24px; letter-spacing:0; }} .subtitle {{ color:var(--muted); font-size:13px; }}
main {{ display:grid; grid-template-columns:280px minmax(0,1fr) 310px; min-height:calc(100vh - 94px); }}
aside, .detail {{ background:var(--panel); padding:18px; }} aside {{ border-right:1px solid var(--line); }} .detail {{ border-left:1px solid var(--line); }}
.section-title {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:4px 0 12px; }}
.toggle {{ display:flex; gap:8px; align-items:center; font-size:12px; color:var(--ink); margin:-2px 0 18px; cursor:pointer; }} .toggle input {{ accent-color:var(--resource); }}
.chapter-list {{ display:grid; gap:5px; }} button.chapter {{ text-align:left; border:1px solid transparent; background:transparent; color:var(--ink); padding:9px 10px; border-radius:5px; cursor:pointer; }} button.chapter:hover {{ background:var(--blue-soft); }} button.chapter.active {{ background:var(--blue); color:white; }}
.chapter-name {{ font-size:13px; font-weight:600; }} .chapter-meta {{ font-size:11px; opacity:.72; margin-top:3px; }}
.stats {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:18px 0; }} .stat {{ padding:10px; border:1px solid var(--line); border-radius:5px; background:#fbfcfd; }} .stat strong {{ display:block; font-size:20px; }} .stat span {{ color:var(--muted); font-size:11px; }}
.canvas {{ min-width:0; padding:22px; overflow:auto; }} .toolbar {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; }} .toolbar strong {{ font-size:15px; }} .legend {{ display:flex; flex-wrap:wrap; gap:10px; color:var(--muted); font-size:11px; }} .legend i {{ width:9px; height:9px; display:inline-block; border-radius:2px; margin-right:4px; }}
svg {{ display:block; width:100%; min-width:720px; height:calc(100vh - 185px); min-height:550px; background:#fbfcfd; border:1px solid var(--line); border-radius:6px; }} .edge {{ fill:none; stroke:#aeb9c6; stroke-width:1.2; opacity:.62; }} .edge.hard_prerequisite {{ stroke:#6683a5; stroke-width:1.6; }} .edge.chapter_prerequisite {{ stroke:#1f6feb; stroke-width:2.4; opacity:.82; }} .edge.soft_prerequisite {{ stroke:#b98b39; stroke-dasharray:4 4; }} .edge.contrasts_with,.edge.confused_with {{ stroke:#c28787; stroke-dasharray:3 3; }}
.node {{ cursor:pointer; stroke-width:1.3; }} .node.chapter {{ fill:var(--blue); stroke:#124f9e; }} .node.section {{ fill:var(--amber-soft); stroke:#d9a13a; }} .node.concept {{ fill:var(--green-soft); stroke:#65ad91; }} .node.concept.has-resources {{ stroke:var(--resource); }} .node.selected {{ stroke:#17212b; stroke-width:3; }} .node.dim {{ opacity:.18; }} .label {{ font-size:10px; pointer-events:none; fill:var(--ink); }} .label.chapter {{ fill:white; font-weight:600; font-size:11px; }} .label.dim {{ opacity:.2; }} .resource-badge {{ fill:var(--resource); stroke:white; stroke-width:1; }} .resource-count {{ fill:white; font-size:8px; font-weight:700; pointer-events:none; }}
.detail h2 {{ font-size:16px; margin:0 0 8px; }} .detail p {{ margin:6px 0; font-size:12px; line-height:1.5; }} .detail code {{ font-size:11px; }} .pill {{ display:inline-block; padding:3px 6px; border-radius:3px; font-size:11px; background:var(--blue-soft); color:#174a89; margin:2px 3px 2px 0; }} .ok {{ color:var(--green); }} .warn {{ color:var(--amber); }} .bad {{ color:var(--red); }} .empty {{ color:var(--muted); font-size:12px; }}
@media (max-width:1000px) {{ main {{ grid-template-columns:220px minmax(0,1fr); }} .detail {{ grid-column:1/-1; border-left:0; border-top:1px solid var(--line); }} }}
@media (max-width:680px) {{ header {{ padding:18px; }} main {{ display:block; }} aside {{ border-right:0; border-bottom:1px solid var(--line); }} .canvas {{ padding:12px; }} svg {{ min-width:680px; height:560px; }} }}
</style>
</head>
<body>
<header><h1>AI Learning Course Graph</h1><div id="subtitle" class="subtitle"></div></header>
<main>
<aside><div class="section-title">章节导航</div><div id="chapters" class="chapter-list"></div><div class="stats"><div class="stat"><strong id="conceptCount"></strong><span>概念节点</span></div><div class="stat"><strong id="edgeCount"></strong><span>先修关系</span></div><div class="stat"><strong id="crossCount"></strong><span>跨章节先修</span></div><div class="stat"><strong id="cycleCount"></strong><span>检测环路</span></div><div class="stat"><strong id="bindingCount"></strong><span>候选绑定</span></div><div class="stat"><strong id="coveredConceptCount"></strong><span>有资源概念</span></div></div><div class="section-title">显示层</div><label class="toggle"><input id="resourceToggle" type="checkbox" checked><span>显示候选资源标记</span></label><div class="section-title">关系图例</div><div class="legend"><span><i style="background:#6683a5"></i>硬先修</span><span><i style="background:#b98b39"></i>软先修</span><span><i style="background:#c28787"></i>对比/易混淆</span><span><i style="background:#d97745"></i>候选资源</span></div></aside>
<section class="canvas"><div class="toolbar"><strong id="viewTitle">课程章节主干</strong><span class="legend"><span><i style="background:#1f6feb"></i>章节</span><span><i style="background:#d9a13a"></i>小节</span><span><i style="background:#65ad91"></i>概念</span><span><i style="background:#d97745"></i>候选资源数</span></span></div><svg id="graph" role="img" aria-label="课程知识图谱关系图"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#6683a5"></path></marker></defs><g id="edges"></g><g id="nodes"></g></svg></section>
<section class="detail"><div class="section-title">逻辑检查</div><div id="logic"></div><hr><div class="section-title">当前选择</div><div id="selected"><div class="empty">选择章节或概念查看详情</div></div></section>
</main>
<script>
const DATA = {data};
const state = {{ chapterId: null, selectedId: null, showResources: true }};
const svg = document.getElementById('graph');
const edgesEl = document.getElementById('edges');
const nodesEl = document.getElementById('nodes');
const byId = new Map([...DATA.chapters, ...DATA.sections, ...DATA.concepts].map(item => [item.id, item]));
const chapterById = new Map(DATA.chapters.map(item => [item.id, item]));
const resourcesByConcept = new Map();
DATA.resourceBindings.forEach(binding => {{
  if (!resourcesByConcept.has(binding.concept_id)) resourcesByConcept.set(binding.concept_id, []);
  resourcesByConcept.get(binding.concept_id).push(binding);
}});
const position = new Map();
const W = 1160, H = 760;
svg.setAttribute('viewBox', `0 0 ${{W}} ${{H}}`);
document.getElementById('conceptCount').textContent = DATA.logic.conceptCount;
document.getElementById('edgeCount').textContent = DATA.logic.hardPrerequisiteCount;
document.getElementById('crossCount').textContent = DATA.logic.crossChapterPrerequisites.length;
document.getElementById('cycleCount').textContent = DATA.logic.cycles.length;
document.getElementById('bindingCount').textContent = DATA.logic.candidateBindingCount;
document.getElementById('coveredConceptCount').textContent = DATA.logic.boundConceptCount;
document.getElementById('subtitle').textContent = `ai-course-v1 · ${{DATA.logic.conceptCount}} 个概念 · ${{DATA.chapters.length}} 个章节 · ${{DATA.logic.hardPrerequisiteCount}} 条先修关系 · ${{DATA.logic.candidateBindingCount}} 条候选资源绑定`;
function layout() {{
  const chapterGap = W / (DATA.chapters.length + 1);
  DATA.chapters.forEach((chapter, index) => position.set(chapter.id, {{x:(index+1)*chapterGap, y:100}}));
  DATA.sections.forEach(section => {{ const c = position.get(section.chapterId); const siblings = DATA.sections.filter(item => item.chapterId === section.chapterId); const i=siblings.indexOf(section); position.set(section.id, {{x:c.x + (i-(siblings.length-1)/2)*32, y:230 + Math.min(i,5)*16}}); }});
  DATA.concepts.forEach(concept => {{ const c=position.get(concept.chapterId); const siblings=DATA.concepts.filter(item=>item.chapterId===concept.chapterId); const i=siblings.indexOf(concept); const cols=4; position.set(concept.id, {{x:c.x + ((i%cols)-(cols-1)/2)*48, y:380 + Math.floor(i/cols)*55}}); }});
}}
function visible(item) {{
  if (!state.chapterId) return item.type === 'chapter';
  return item.type === 'chapter' || item.chapterId === state.chapterId;
}}
function render() {{
  layout(); edgesEl.innerHTML=''; nodesEl.innerHTML='';
  const visibleIds = new Set([...DATA.chapters,...DATA.sections,...DATA.concepts].filter(visible).map(item=>item.id));
  DATA.edges.filter(edge=>visibleIds.has(edge.source)&&visibleIds.has(edge.target)).forEach(edge=>{{ const a=position.get(edge.source), b=position.get(edge.target); if(!a||!b)return; const path=document.createElementNS('http://www.w3.org/2000/svg','path'); path.setAttribute('d',`M ${{a.x}} ${{a.y}} C ${{a.x}} ${{(a.y+b.y)/2}}, ${{b.x}} ${{(a.y+b.y)/2}}, ${{b.x}} ${{b.y}}`); path.setAttribute('class',`edge ${{edge.kind}}`); if(edge.kind.includes('prerequisite'))path.setAttribute('marker-end','url(#arrow)'); edgesEl.appendChild(path); }});
  [...DATA.chapters,...DATA.sections,...DATA.concepts].filter(visible).forEach(item=>{{ const p=position.get(item.id); const group=document.createElementNS('http://www.w3.org/2000/svg','g'); const node=document.createElementNS('http://www.w3.org/2000/svg','rect'); node.setAttribute('x',p.x-(item.type==='chapter'?52: item.type==='section'?38:30)); node.setAttribute('y',p.y-(item.type==='chapter'?18:14)); node.setAttribute('width',item.type==='chapter'?104:item.type==='section'?76:60); node.setAttribute('height',item.type==='chapter'?36:28); node.setAttribute('rx','4'); node.setAttribute('class',`node ${{item.type}} ${{item.type==='concept' && state.showResources && item.resourceCount ? 'has-resources':''}} ${{state.selectedId===item.id?'selected':''}}`); node.addEventListener('click',()=>select(item.id)); group.appendChild(node); const text=document.createElementNS('http://www.w3.org/2000/svg','text'); text.setAttribute('x',p.x); text.setAttribute('y',p.y+4); text.setAttribute('text-anchor','middle'); text.setAttribute('class',`label ${{item.type}}`); text.textContent=item.type==='chapter'?`第${{item.order}}章`:item.label.length>7?item.label.slice(0,7)+'…':item.label; group.appendChild(text); if (item.type==='concept' && state.showResources && item.resourceCount) {{ const badge=document.createElementNS('http://www.w3.org/2000/svg','circle'); badge.setAttribute('cx',p.x+25); badge.setAttribute('cy',p.y-10); badge.setAttribute('r','9'); badge.setAttribute('class','resource-badge'); group.appendChild(badge); const count=document.createElementNS('http://www.w3.org/2000/svg','text'); count.setAttribute('x',p.x+25); count.setAttribute('y',p.y-7); count.setAttribute('text-anchor','middle'); count.setAttribute('class','resource-count'); count.textContent=item.resourceCount > 99 ? '99+' : item.resourceCount; group.appendChild(count); }} nodesEl.appendChild(group); }});
  document.getElementById('viewTitle').textContent = state.chapterId ? `${{chapterById.get(state.chapterId).label}} · 概念依赖` : '课程章节主干';
}}
function escapeHtml(value) {{ return String(value).replace(/[&<>"']/g, character => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[character])); }}
function select(id) {{ state.selectedId=id; const item=byId.get(id); if(item.type==='chapter') state.chapterId=state.chapterId===id?null:id; render(); const related=DATA.edges.filter(edge=>edge.source===id||edge.target===id); const resources=resourcesByConcept.get(id)||[]; const resourceHtml=item.type==='concept' ? `<p>候选资源绑定：${{resources.length}} 条</p>` + (resources.length ? `<div>${{resources.slice(0,8).map(resource=>`<span class="pill">${{escapeHtml(resource.source_title)}} · ${{escapeHtml(resource.match_type)}}</span>`).join('')}}${{resources.length>8?`<span class="pill">还有 ${{resources.length-8}} 条</span>`:''}}</div><p class="warn">候选状态：未审核，不能作为正式证据</p>` : '<p class="empty">暂无候选资源绑定</p>') : ''; document.getElementById('selected').innerHTML=`<h2>${{item.label}}</h2><p><code>${{item.id}}</code></p><p>${{item.summary||item.labelEn||''}}</p><p>${{related.length}} 条关联边</p>${{item.type==='concept'?`<p>章节：${{chapterById.get(item.chapterId).label}}</p>${{resourceHtml}}`:''}}`; }}
const list=document.getElementById('chapters'); DATA.chapters.forEach(chapter=>{{ const button=document.createElement('button'); button.className='chapter'; button.innerHTML=`<div class="chapter-name">第${{chapter.order}}章 · ${{chapter.label}}</div><div class="chapter-meta">${{chapter.conceptCount}} 个概念</div>`; button.addEventListener('click',()=>{{state.chapterId=state.chapterId===chapter.id?null:chapter.id;state.selectedId=null;document.querySelectorAll('button.chapter').forEach(b=>b.classList.remove('active'));if(state.chapterId)button.classList.add('active');document.getElementById('selected').innerHTML='<div class="empty">选择概念查看节点详情</div>';render();}});list.appendChild(button);}});
const logic=document.getElementById('logic'); logic.innerHTML=`<p class="${{DATA.logic.cycles.length?'bad':'ok'}}">${{DATA.logic.cycles.length?'发现 '+DATA.logic.cycles.length+' 个环路':'未发现硬先修环路'}}</p><p class="${{DATA.logic.reverseOrderEdges.length?'warn':'ok'}}">${{DATA.logic.reverseOrderEdges.length?'发现 '+DATA.logic.reverseOrderEdges.length+' 条顺序逆序边':'所有硬先修边符合课程序列'}}</p><p>根节点：${{DATA.logic.roots.length}} 个；叶节点：${{DATA.logic.leaves.length}} 个</p><p>跨章节先修：${{DATA.logic.crossChapterPrerequisites.length}} 条</p><p>孤立概念：${{DATA.logic.isolatedConcepts.length}} 个</p>`;
document.getElementById('resourceToggle').addEventListener('change', event=>{{ state.showResources=event.target.checked; render(); if(state.selectedId) select(state.selectedId); }});
render();
</script>
</body>
</html>'''


def main() -> None:
    catalog = OntologyCatalog.load(
        ONTOLOGY / "ai_course_v1.yaml",
        ONTOLOGY / "ai_relations_v1.yaml",
    )
    corpus = KnowledgeCorpus.load(ROOT / "data" / "index_chunks.jsonl")
    bindings = [
        binding.model_dump(mode="json")
        for binding in build_candidate_bindings(catalog, corpus)
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = graph_payload(catalog, bindings)
    OUTPUT.write_text(render_html(payload), encoding="utf-8")
    LOGIC_OUTPUT.write_text(
        json.dumps(payload["logic"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT}")
    print(f"wrote {LOGIC_OUTPUT}")


if __name__ == "__main__":
    main()
