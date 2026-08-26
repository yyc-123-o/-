"""知识库检索引擎 — BM25 + 中文分词 + 字段加权 + 同义词扩展。

设计目标:
  1. 不依赖向量模型 / rank_bm25 / faiss，纯标准库 + jieba(可选) + 自实现 BM25，
     保证轻量、可离线、可复现。
  2. 中文使用 jieba 分词；若 jieba 不可用，自动回退到「单字 + 二元组」分词。
  3. 标题/章节路径的命中权重大于正文，让「与标题/小节更相关」的依据排在前面。
  4. 内置 AI/深度学习常用中英术语同义词表，解决「反向传播 vs backprop / BP」、
     「卷积神经网络 vs CNN」这类同一概念不同写法检索不到的问题。

用法:
    engine = RetrievalEngine(chunks)          # chunks 为 index_chunks.jsonl 的 dict 列表
    hits = engine.search("反向传播算法", top_k=5)
    # hits -> [{"index": 0, "score": 1.0, "chunk": {...}}, ...]
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

try:  # jieba 可选依赖，缺失时回退到字符 n-gram
    import jieba as _jieba
except Exception:  # pragma: no cover - 仅在缺失 jieba 时触发
    _jieba = None


# ---------------------------------------------------------------
# 停用词（过滤高频虚词，提升检索精度）
# ---------------------------------------------------------------
_STOPWORDS = {
    # 中文
    "的", "了", "是", "有", "在", "和", "与", "及", "或", "中", "上", "下",
    "怎么", "哪些", "什么", "如何", "请问", "一下", "这个", "那个", "该",
    "吗", "呢", "啊", "吧", "呀", "我", "你", "他", "她", "它", "我们", "你们",
    # 英文
    "a", "an", "the", "is", "are", "was", "were", "be", "of", "to", "in",
    "for", "on", "with", "and", "or", "what", "how", "why", "which", "do",
    "does", "did", "can", "could", "should", "would", "please", "you", "me",
    "i", "this", "that", "it", "as", "at", "by", "from", "about", "into",
}


# ---------------------------------------------------------------
# 同义词 / 中英术语映射（查询侧扩展，值会再经过分词）
# key: 可能出现在用户问题里的短语或词
# value: 等价写法（英文 / 中文 / 缩写），用于召回同一概念的不同表达
# ---------------------------------------------------------------
SYNONYM_MAP: Dict[str, List[str]] = {
    # 神经网络 / 训练
    "卷积神经网络": ["cnn", "convolutional neural network", "convnet", "卷积", "textcnn"],
    "cnn": ["卷积神经网络", "卷积", "convolutional", "textcnn"],
    "循环神经网络": ["rnn", "lstm", "gru", "循环网络"],
    "rnn": ["循环神经网络", "lstm", "gru"],
    "反向传播": ["backpropagation", "backprop", "bp", "误差反向传播"],
    "backpropagation": ["反向传播", "backprop", "bp"],
    "backprop": ["反向传播", "backpropagation", "bp"],
    "梯度下降": ["gradient descent", "sgd", "adam", "优化器", "梯度"],
    "gradient descent": ["梯度下降", "sgd", "adam", "优化器"],
    "损失函数": ["loss function", "loss", "交叉熵", "均方误差", "mse"],
    "loss function": ["损失函数", "loss", "交叉熵"],
    "激活函数": ["activation function", "relu", "sigmoid", "softmax", "激活"],
    "activation function": ["激活函数", "relu", "sigmoid", "softmax"],
    "过拟合": ["overfitting", "过拟合", "正则化", "regularization"],
    "正则化": ["regularization", "l2", "dropout", "过拟合"],
    "注意力机制": ["attention", "self-attention", "自注意力", "transformer"],
    "attention": ["注意力机制", "自注意力", "self-attention"],
    "自注意力": ["self-attention", "attention", "注意力机制"],
    "transformer": ["注意力机制", "attention", "self-attention", "自注意力"],

    # 大模型 / 微调 / 部署
    "大语言模型": ["llm", "大模型", "语言模型", "gpt", "deepseek"],
    "llm": ["大语言模型", "大模型", "语言模型"],
    "微调": ["finetune", "fine-tuning", "lora", "qlora", "sft", "fine tuning"],
    "finetune": ["微调", "lora", "qlora", "sft"],
    "fine-tuning": ["微调", "lora", "qlora", "sft"],
    "lora": ["微调", "qlora", "低秩", "low-rank", "大模型"],
    "qlora": ["lora", "微调", "量化", "低秩"],
    "deepseek": ["大语言模型", "llm", "deepseek-r1", "deepseek-v3", "大模型"],
    "langchain": ["大语言模型应用", "llm 应用", "agent", "智能体"],
    "智能体": ["agent", "langchain", "大语言模型应用"],
    "agent": ["智能体", "langchain", "大语言模型应用"],
    "提示词": ["prompt", "prompting", "提示工程"],
    "prompt": ["提示词", "提示工程", "prompting"],
    "部署": ["deploy", "deployment", "fastapi", "webdemo", "推理服务"],

    # RAG / 检索 / 向量
    "检索增强生成": ["rag", "检索增强", "retrieval augmented", "知识库问答"],
    "rag": ["检索增强生成", "检索增强", "retrieval augmented", "知识库问答"],
    "向量数据库": ["vector database", "faiss", "向量检索", "向量", "milvus"],
    "vector database": ["向量数据库", "faiss", "向量检索"],
    "向量检索": ["vector search", "faiss", "向量数据库", "向量"],
    "嵌入": ["embedding", "向量化", "bge", "向量", "表征"],
    "embedding": ["嵌入", "向量化", "bge", "向量", "表征"],
    "重排序": ["rerank", "re-rank", "reranking"],
    "rerank": ["重排序", "re-rank", "reranking"],
    "faiss": ["向量数据库", "向量检索", "vector database", "向量索引"],
    "bge": ["embedding", "嵌入", "向量化", "向量模型"],
    "graphrag": ["图检索增强", "graph rag", "知识图谱", "图神经网络"],

    # 知识图谱 / 图
    "知识图谱": ["knowledge graph", "neo4j", "图数据库", "图谱"],
    "knowledge graph": ["知识图谱", "neo4j", "图数据库"],
    "图数据库": ["neo4j", "knowledge graph", "知识图谱", "图存储"],
    "neo4j": ["知识图谱", "图数据库", "knowledge graph"],

    # 生成模型
    "生成对抗网络": ["gan", "生成式对抗", "对抗生成", "对抗网络"],
    "gan": ["生成对抗网络", "生成式对抗", "对抗网络"],
    "扩散模型": ["diffusion", "stable diffusion", "扩散", "ddpm"],
    "diffusion": ["扩散模型", "扩散", "ddpm", "stable diffusion"],

    # 其它常见
    "多模态": ["multimodal", "图文", "跨模态"],
    "文本分类": ["textcnn", "text classification", "分类", "文本"],
    "分词": ["tokenizer", "tokenization", "切词"],
    "词向量": ["word embedding", "word2vec", "embedding"],
}


# ---------------------------------------------------------------
# BM25 参数与字段权重
# ---------------------------------------------------------------
K1 = 1.5
B = 0.75
_FIELD_WEIGHTS = {"title": 3.0, "heading": 2.0, "body": 1.0}

# 查询扩展词相对原始词的重要性（<1 表示扩展词更弱）
_SYNONYM_WEIGHT = 0.6


def _tokenize(text: str) -> List[str]:
    """把文本切成检索词：英文/数字按词，中文按 jieba（回退单字+二元组）。"""
    text = (text or "").lower()
    tokens: List[str] = []

    # 英文 / 数字 / 标识符（C#、C++、7b、deepseek 等），长度 >= 2
    for tok in re.findall(r"[a-z0-9_+#]+", text):
        if len(tok) >= 2:
            tokens.append(tok)

    # 中文片段
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if _jieba is not None:
            for w in _jieba.cut(run):
                w = w.strip()
                if w and w not in _STOPWORDS:
                    tokens.append(w)
        else:  # 无 jieba：单字 + 二元组
            tokens.extend(ch for ch in run if ch not in _STOPWORDS)
            tokens.extend(
                run[i:i + 2]
                for i in range(len(run) - 1)
                if run[i:i + 2] not in _STOPWORDS
            )

    return [t for t in tokens if t and t not in _STOPWORDS]


def _expand_query(query_raw: str) -> List[Tuple[str, float]]:
    """分词 + 同义词扩展，返回 (term, weight) 列表（已去重、保留最大权重）。"""
    q = (query_raw or "").lower()
    weighted: Dict[str, float] = {}

    # 原始词
    for t in _tokenize(q):
        weighted[t] = max(weighted.get(t, 0.0), 1.0)

    # 同义词扩展（对原始问句做子串命中，避免 jieba 把词组拆开后丢失概念）
    for phrase, synonyms in SYNONYM_MAP.items():
        if phrase in q:
            for syn in synonyms:
                for st in _tokenize(syn):
                    weighted[st] = max(weighted.get(st, 0.0), _SYNONYM_WEIGHT)

    return list(weighted.items())


class RetrievalEngine:
    """基于 BM25 的轻量检索器。"""

    def __init__(self, chunks: List[dict]):
        self.chunks = chunks
        self._docs: List[Dict[str, List[str]]] = []
        self._idf: Dict[str, float] = {}
        self._avgdl: float = 0.0
        self._built: bool = False

    def build(self) -> None:
        """构建内存索引（惰性调用，仅执行一次）。"""
        if self._built:
            return

        df: Counter = Counter()
        total_len = 0
        for c in self.chunks:
            title_tokens = _tokenize(c.get("source_title", ""))
            heading_tokens = _tokenize(" ".join(c.get("heading_path", [])))
            body_tokens = _tokenize(c.get("text", ""))
            self._docs.append(
                {"title": title_tokens, "heading": heading_tokens, "body": body_tokens}
            )
            for term in set(title_tokens) | set(heading_tokens) | set(body_tokens):
                df[term] += 1
            total_len += len(title_tokens) + len(heading_tokens) + len(body_tokens)

        n = max(1, len(self._docs))
        self._avgdl = total_len / n
        for term, d in df.items():
            self._idf[term] = math.log((n - d + 0.5) / (d + 0.5) + 1.0)
        self._built = True

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """返回 [{"index": int, "score": float, "chunk": dict}, ...]，按相关度降序。

        score 已相对本次查询的最高分归一化到 [0, 1]（最高命中为 1.0）。
        """
        self.build()
        qterms = _expand_query(query)
        if not qterms:
            return []

        raw_scores: List[Tuple[float, int]] = []
        for i, doc in enumerate(self._docs):
            dl = len(doc["title"]) + len(doc["heading"]) + len(doc["body"])
            norm = 1.0 - B + B * dl / self._avgdl
            s = 0.0
            for term, w in qterms:
                idf = self._idf.get(term)
                if idf is None:
                    continue
                tf = (
                    doc["title"].count(term) * _FIELD_WEIGHTS["title"]
                    + doc["heading"].count(term) * _FIELD_WEIGHTS["heading"]
                    + doc["body"].count(term) * _FIELD_WEIGHTS["body"]
                )
                if tf <= 0:
                    continue
                s += w * idf * (tf * (K1 + 1.0)) / (tf + K1 * norm)
            if s > 0.0:
                raw_scores.append((s, i))

        raw_scores.sort(key=lambda item: item[0], reverse=True)
        raw_scores = raw_scores[: max(1, min(top_k, 20))]
        if not raw_scores:
            return []

        max_score = raw_scores[0][0] or 1.0
        return [
            {
                "index": i,
                "score": round(min(1.0, s / max_score), 4),
                "chunk": self.chunks[i],
            }
            for s, i in raw_scores
        ]
