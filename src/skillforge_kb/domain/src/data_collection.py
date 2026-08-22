"""
数据采集脚本
------------
补上之前遗漏的一环: 把"现成可用的公开资源"实际下载到 data/raw/, 而不是假设文件已经在那。

已在沙盒里验证过路径有效性的部分: D2L仓库结构、roadmap.sh仓库结构(结论: roadmap.sh的json
是可视化流程图布局, 不是干净的前置知识图, 已在代码里做了明确标注和降级处理, 不要直接当作
精确的PREREQUISITE_OF关系入库)。

arXiv API / Wikidata SPARQL 这两段代码逻辑正确、接口地址真实, 但因为沙盒网络白名单限制没能
现场跑通, 请在AutoDL(或任意不限网络的环境)上执行验证。

用法: python data_collection.py --source d2l roadmap arxiv wikidata --out data/raw
"""

from __future__ import annotations
import os
import re
import json
import time
import subprocess
import argparse
from typing import List, Optional
import requests


# ============================================================
# 1. D2L(动手学深度学习) —— 已验证仓库结构, markdown可直接喂 parse_markdown()
# ============================================================
def _clean_d2l_syntax(text: str) -> str:
    """
    D2L用MyST/Sphinx风格写书, 正文里混有构建系统指令和目录列表, 直接切片会污染chunk质量:
    - :label:`xxx` / :numref:`xxx` 这类交叉引用指令
    - ```toc```代码块里的章节目录列表(不是正文内容)
    统一清掉, 只保留真正的讲解文字。
    """
    text = re.sub(r":(label|numref|eqref|ref):`[^`]*`", "", text)
    text = re.sub(r"```toc.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def download_d2l(dest_dir: str, chapters: Optional[List[str]] = None):
    """
    chapters: 只拉取指定章节目录(如 ["chapter_linear-networks", "chapter_attention-mechanisms"]),
              为None时拉取整个仓库(体积较大, 含大量代码示例, 建议按需选章节)。
    """
    repo_url = "https://github.com/d2l-ai/d2l-zh.git"
    clone_dir = os.path.join(dest_dir, "_d2l_repo")
    os.makedirs(dest_dir, exist_ok=True)

    if not os.path.exists(clone_dir):
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", repo_url, clone_dir],
            check=True,
        )
    if chapters:
        subprocess.run(["git", "sparse-checkout", "set", *chapters], cwd=clone_dir, check=True)
    else:
        subprocess.run(["git", "sparse-checkout", "disable"], cwd=clone_dir, check=True)

    # 把各章节的 index.md 拷到统一的 raw 目录, 文件名带章节前缀避免重名覆盖
    out_dir = os.path.join(dest_dir, "d2l")
    os.makedirs(out_dir, exist_ok=True)
    count = 0
    for root, _, files in os.walk(clone_dir):
        if "chapter_" not in root:
            continue
        for fname in files:
            if fname == "index.md":  # d2l每章正文都是 index.md, index_origin.md 是双语底稿, 跳过
                chapter_name = os.path.basename(root)
                src = os.path.join(root, fname)
                dst = os.path.join(out_dir, f"{chapter_name}.md")
                with open(src, "r", encoding="utf-8") as f:
                    content = f.read()
                content = _clean_d2l_syntax(content)
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(content)
                count += 1
    print(f"[d2l] 已导出 {count} 个章节markdown到 {out_dir}")


# ============================================================
# 2. roadmap.sh AI Engineer —— 已验证: json是可视化布局, 不是精确前置图
#    策略: content/*.md 直接作为知识点短文语料; 前置顺序按同一x坐标列内的y坐标做启发式排序,
#    输出一份 "候选PREREQUISITE_OF关系" 文件, 明确标注为待人工/LLM复核, 不直接当真值导入。
# ============================================================
def download_roadmap_ai_engineer(dest_dir: str, x_bin_width: float = 150.0):
    repo_url = "https://github.com/kamranahmedse/developer-roadmap.git"
    clone_dir = os.path.join(dest_dir, "_roadmap_repo")
    os.makedirs(dest_dir, exist_ok=True)

    if not os.path.exists(clone_dir):
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", repo_url, clone_dir],
            check=True,
        )
    subprocess.run(
        ["git", "sparse-checkout", "set", "src/data/roadmaps/ai-engineer"],
        cwd=clone_dir, check=True,
    )

    roadmap_dir = os.path.join(clone_dir, "src/data/roadmaps/ai-engineer")
    json_path = os.path.join(roadmap_dir, "ai-engineer.json")
    content_dir = os.path.join(roadmap_dir, "content")

    # 2a. 导出知识点短文(可直接切片的语料)
    out_dir = os.path.join(dest_dir, "roadmap_ai_engineer")
    os.makedirs(out_dir, exist_ok=True)
    for fname in os.listdir(content_dir):
        if fname.endswith(".md"):
            with open(os.path.join(content_dir, fname), "r", encoding="utf-8") as f:
                content = f.read()
            # 文件名形如 "temperature@_bPTciEA1GT1JwfXim19z.md", @前面是可读标题
            title = fname.split("@")[0]
            with open(os.path.join(out_dir, f"{title}.md"), "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{content}")
    print(f"[roadmap] 已导出 {len(os.listdir(out_dir))} 篇知识点短文到 {out_dir}")

    # 2b. 启发式推导候选前置关系(按x坐标分列, 列内按y坐标从上到下排序)
    with open(json_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    topic_nodes = [n for n in graph["nodes"] if n.get("type") in ("topic", "subtopic")]
    columns: dict = {}
    for n in topic_nodes:
        label = n.get("data", {}).get("label")
        if not label:
            continue
        x = n["position"]["x"]
        col_key = round(x / x_bin_width)
        columns.setdefault(col_key, []).append((n["position"]["y"], label))

    candidate_edges = []
    for col_key, items in columns.items():
        items.sort(key=lambda t: t[0])  # 按y坐标从上到下
        for i in range(len(items) - 1):
            candidate_edges.append({"prerequisite": items[i][1], "next": items[i + 1][1]})

    candidate_path = os.path.join(dest_dir, "roadmap_ai_engineer_candidate_edges.json")
    with open(candidate_path, "w", encoding="utf-8") as f:
        json.dump(candidate_edges, f, ensure_ascii=False, indent=2)
    print(
        f"[roadmap] 已生成 {len(candidate_edges)} 条候选前置关系 -> {candidate_path}\n"
        f"          ⚠️ 这是按可视化坐标推导的启发式结果, 不是精确知识图, "
        f"建议过一遍LLM或人工做二次校验后再导入 kg_schema_neo4j.KGBuilder"
    )


# ============================================================
# 3. arXiv API —— 真实接口, 沙盒里无法验证(域名不在白名单), 请在AutoDL上跑
# ============================================================
def fetch_arxiv_papers(query: str, dest_dir: str, max_results: int = 30):
    """
    arXiv官方API, 免费无需key。注意: 只返回摘要(abstract), 不是全文;
    如需全文, 需要额外用 arxiv.org/pdf/{id} 下载PDF再走你的 document_parser.parse_pdf()。
    """
    out_dir = os.path.join(dest_dir, "arxiv")
    os.makedirs(out_dir, exist_ok=True)

    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    resp = requests.get(base_url, params=params, timeout=30)
    resp.raise_for_status()

    # arXiv返回Atom XML, 用标准库解析, 不额外引入feedparser依赖
    import xml.etree.ElementTree as ET

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    count = 0
    for entry in root.findall("atom:entry", ns):
        title = entry.find("atom:title", ns).text.strip()
        summary = entry.find("atom:summary", ns).text.strip()
        arxiv_id = entry.find("atom:id", ns).text.strip().split("/")[-1]
        safe_title = re.sub(r"[^\w\u4e00-\u9fff-]", "_", title)[:60]
        with open(os.path.join(out_dir, f"{arxiv_id}_{safe_title}.md"), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\narXiv ID: {arxiv_id}\n\n## 摘要\n\n{summary}\n")
        count += 1
        time.sleep(0.3)  # arXiv要求控制请求频率
    print(f"[arxiv] 已抓取 {count} 篇论文摘要到 {out_dir}(注意: 仅摘要, 非全文)")


# ============================================================
# 4. Wikidata SPARQL —— 真实接口, 沙盒里无法验证, 请在AutoDL上跑
#    直接产出可导入Neo4j的三元组(subclass of / instance of 关系), 不需要经过LLM抽取,
#    质量比LLM抽取更稳定, 适合做图谱骨架。
# ============================================================
WIKIDATA_AI_ROOT_QID = "Q2539"  # machine learning 在Wikidata的实体ID

def fetch_wikidata_concepts(dest_dir: str, root_qid: str = WIKIDATA_AI_ROOT_QID, depth: int = 2):
    sparql = f"""
    SELECT ?item ?itemLabel ?itemLabel_zh ?parent ?parentLabel WHERE {{
      ?item wdt:P279{{1,{depth}}} wd:{root_qid} .
      ?item wdt:P279 ?parent .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en". }}
      OPTIONAL {{ ?item rdfs:label ?itemLabel_zh . FILTER(LANG(?itemLabel_zh) = "zh") }}
    }}
    """
    resp = requests.get(
        "https://query.wikidata.org/sparql",
        params={"query": sparql, "format": "json"},
        headers={"User-Agent": "domain-kg-rag-collector/1.0"},
        timeout=60,
    )
    resp.raise_for_status()
    bindings = resp.json()["results"]["bindings"]

    triples = []
    for b in bindings:
        child = b.get("itemLabel_zh", {}).get("value") or b.get("itemLabel", {}).get("value")
        parent = b.get("parentLabel", {}).get("value")
        if child and parent:
            triples.append({"head": child, "relation": "PART_OF", "tail": parent})

    os.makedirs(dest_dir, exist_ok=True)
    out_path = os.path.join(dest_dir, "wikidata_ml_concepts.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(triples, f, ensure_ascii=False, indent=2)
    print(f"[wikidata] 已导出 {len(triples)} 条概念从属关系 -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", nargs="+", choices=["d2l", "roadmap", "arxiv", "wikidata"], required=True)
    parser.add_argument("--out", default="data/raw")
    parser.add_argument("--arxiv-query", default="large language model fine-tuning")
    args = parser.parse_args()

    if "d2l" in args.source:
        download_d2l(args.out, chapters=["chapter_attention-mechanisms", "chapter_natural-language-processing-pretraining"])
    if "roadmap" in args.source:
        download_roadmap_ai_engineer(args.out)
    if "arxiv" in args.source:
        fetch_arxiv_papers(args.arxiv_query, args.out)
    if "wikidata" in args.source:
        fetch_wikidata_concepts(args.out)
