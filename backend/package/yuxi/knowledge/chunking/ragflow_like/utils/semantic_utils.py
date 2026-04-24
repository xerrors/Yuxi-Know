from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import nltk
from nltk.tokenize import sent_tokenize
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score

_punkt_checked = False


def _ensure_punkt_tab() -> None:
    """首次使用分句能力时检查 NLTK punkt_tab 资源，缺失时给出可操作错误。"""
    global _punkt_checked
    if _punkt_checked:
        return

    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError as e:
        raise RuntimeError("缺少 NLTK 资源 punkt_tab。请先执行: python -m nltk.downloader punkt_tab") from e

    _punkt_checked = True


def split_sentences_chinese(text: str) -> list[str]:
    """
    使用正则表达式将中文文本分割成句子。

    逻辑：
    - 匹配中文句号、感叹号、问号（。！？）作为分隔点。
    - 使用正向/反向预查处理引号：确保如果标点后面紧跟引号（”’"），该引号会被保留在当前句子末尾，而不是被切分到下一句。
    - 返回去除两端空格且非空的句子列表。
    """
    pattern = r'(?<=[。！？][”’"])|(?<=[。！？])(?![”’"])'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]


def split_mixed_sentences(text: str) -> list[str]:
    """
    处理中英文混合文本的分句逻辑，支持按物理段落分发不同的分句策略。

    该函数采用“分而治之”的策略来处理复杂的混合文本：
    1. **物理分块**：首先按换行符 (`\\n+`) 将原始文本切分为多个物理段落（chunks），确保物理结构不被破坏。
    2. **语言检测与分发**：
       - **英文/混合路径**：若段落中包含英文字母 (`[A-Za-z]`)，则视为英文或混合文本，
         调用 NLTK 的 `sent_tokenize` 进行处理。NLTK 能更好地处理英文缩写、句点等复杂情况。
       - **中文路径**：若段落不含字母，则视为纯中文文本，调用 `split_sentences_chinese`。
         该方法通过正则精准匹配中文标点及后续引号。
       - **兜底方案**：若上述方法未产生结果，则使用简单的正则表达式按中文标点强制分割。
    3. **清洗与过滤**：汇总所有子句，去除两端空白字符，并过滤掉空字符串。

    Args:
        text: 待分句的原始字符串。

    Returns:
        List[str]: 分割后的句子列表。
    """
    _ensure_punkt_tab()

    chunks = re.split(r"(\n+)", text)
    sentences = []

    for ch in chunks:
        if not ch.strip():
            continue
        if re.search(r"[A-Za-z]", ch):
            parts = sent_tokenize(ch)
            sentences.extend([p.strip() for p in parts if p.strip()])
        else:
            sents = split_sentences_chinese(ch)
            if sents:
                sentences.extend([s.strip() for s in sents if s.strip()])
            else:
                parts = re.split(r"(?<=[。！？])", ch)
                sentences.extend([p.strip() for p in parts if p.strip()])
    return sentences


def find_best_num_clusters(embeddings: Any, min_clusters: int = 2, max_clusters: int = 10) -> int:
    """
    使用轮廓系数选择最佳聚类数量。让每个分段语义集中，且分段之间界限分明

    逻辑：
    - 遍历可能的聚类数量（从 min_clusters 到 max_clusters）。
    - 对每个聚类数量，使用 `AgglomerativeClustering` 进行聚类。
    - 计算轮廓系数（Silhouette Score）。
    - 选择轮廓系数最高的聚类数量作为最佳聚类数量。
    - 如果聚类数量为 1 或更少，直接返回 1。

    Args:
        embeddings: 待聚类的向量数据（所有句子的嵌入向量列表）。
        min_clusters: 搜索的最佳聚类数量下限，默认为 2。
        max_clusters: 搜索的最佳聚类数量上限，默认为 10。

    Returns:
        int: 轮廓系数表现最好的聚类数量。
    """
    if len(embeddings) <= min_clusters:
        return len(embeddings)

    best_score = -1
    best_k = min_clusters

    limit_k = min(max_clusters, len(embeddings))
    for k in range(min_clusters, limit_k + 1):
        labels = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(embeddings)
        if len(set(labels)) <= 1:
            continue
        score = silhouette_score(embeddings, labels, metric="cosine")
        if score > best_score:
            best_score = score
            best_k = k

    return best_k


def semantic_chunking_with_auto_clusters(
    text: str,
    embed_fn: Callable[[list[str]], Any] | None,
    token_count_fn: Callable[[str], int],
    max_chunk_size: int = 512,
) -> list[str]:
    """
    对传入的文本进行语义切分，过程中会自动选择最佳的聚集数量。

    逻辑：
    - 先将文本中的句子按语言进行分发，英文/混合文本使用NLTK的sent_tokenize，中文文本使用split_sentences_chinese。
    - 对每个句子进行嵌入向量化。
    - 确定最佳的聚类数量（根据轮廓系数）。
    - 对句子进行聚类后，按原文顺序遍历：当聚类标签变化或达到长度上限时切分，形成连续分块。
    - 如果嵌入模型缺失，则退化为原始切分方式
    """
    sentences = split_mixed_sentences(text)
    if len(sentences) < 2:
        return [text.strip()]

    # 计算每个句子的token数量
    sentence_token_counts = [token_count_fn(s) for s in sentences]
    total_tokens = sum(sentence_token_counts)

    # 如果没有提供向量化函数，或者整体未超长，则直接进行简单合并/返回
    if embed_fn is None or total_tokens <= max_chunk_size:
        chunks = []
        current_chunk = ""
        current_chunk_tokens = 0
        for s, cnt in zip(sentences, sentence_token_counts):
            if current_chunk_tokens + cnt > max_chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = s
                current_chunk_tokens = cnt
            else:
                current_chunk += s
                current_chunk_tokens += cnt
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    # 向量化每个句子, 得到他们的嵌入向量
    embeddings = embed_fn(sentences)

    # 决定合适的聚集数量：超长时按上限向上取整，避免整除时多切一块
    best_k = (total_tokens + max_chunk_size - 1) // max_chunk_size
    best_k = min(best_k, len(sentences))

    # 根据指定的聚集数量、相似度判断方式、联动方式，对句子进行聚类
    # labels 是每个句子的聚类标签列表（如 [0,0,1,2,2]），后续会按原文顺序在标签变化处切分连续分块
    labels = AgglomerativeClustering(n_clusters=best_k, metric="cosine", linkage="average").fit_predict(embeddings)

    chunks = []
    current_chunk = ""
    current_chunk_tokens = 0
    current_label = labels[0]

    for sentence, label, token_count in zip(sentences, labels, sentence_token_counts):
        if label != current_label or current_chunk_tokens + token_count > max_chunk_size:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = sentence
            current_chunk_tokens = token_count
            current_label = label
        else:
            current_chunk += sentence
            current_chunk_tokens += token_count

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
