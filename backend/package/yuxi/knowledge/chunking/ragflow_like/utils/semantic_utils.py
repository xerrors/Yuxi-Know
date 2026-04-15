from __future__ import annotations

import re
import nltk
from nltk.tokenize import sent_tokenize
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from typing import Callable, List, Any

# Ensure punkt_tab is available
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')

def split_sentences_chinese(text: str) -> List[str]:
    """
    Split sentences by Chinese punctuation while keeping the punctuation.
    """
    pattern = r'(?<=[。！？])(?![”’"])|(?<=[。！？][”’"])'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]

def split_mixed_sentences(text: str) -> List[str]:
    """
    Handle both Chinese and English sentence splitting.
    """
    chunks = re.split(r'(\n+)', text)
    sentences = []

    for ch in chunks:
        if not ch.strip():
            continue
        if re.search(r'[A-Za-z]', ch):
            parts = sent_tokenize(ch)
            sentences.extend([p.strip() for p in parts if p.strip()])
        else:
            sents = split_sentences_chinese(ch)
            if sents:
                sentences.extend([s.strip() for s in sents if s.strip()])
            else:
                parts = re.split(r'(?<=[。！？])', ch)
                sentences.extend([p.strip() for p in parts if p.strip()])
    return sentences

def find_best_num_clusters(embeddings: Any, min_clusters: int = 2, max_clusters: int = 10) -> int:
    """
    Select best number of clusters using silhouette score.
    """
    if len(embeddings) <= min_clusters:
        return len(embeddings)

    best_score = -1
    best_k = min_clusters

    limit_k = min(max_clusters, len(embeddings))
    for k in range(min_clusters, limit_k + 1):
        labels = AgglomerativeClustering(n_clusters=k, metric='cosine', linkage='average').fit_predict(embeddings)
        if len(set(labels)) <= 1:
            continue
        score = silhouette_score(embeddings, labels, metric='cosine')
        if score > best_score:
            best_score = score
            best_k = k

    return best_k

def semantic_chunking_with_auto_clusters(
    text: str, 
    embed_fn: Callable[[List[str]], Any],
    token_count_fn: Callable[[str], int],
    max_chunk_size: int = 512
) -> List[str]:
    """
    Semantic chunking with automatic cluster number selection.
    """
    sentences = split_mixed_sentences(text)
    if len(sentences) < 2:
        return [text.strip()]

    # Vectorization
    embeddings = embed_fn(sentences)
    
    # Pre-calculate token counts
    sentence_token_counts = [token_count_fn(s) for s in sentences]
    total_tokens = sum(sentence_token_counts)

    # Determine number of clusters
    best_k = max(total_tokens // max_chunk_size, 1) + 1
    best_k = min(best_k, len(sentences))
    
    # Clustering
    labels = AgglomerativeClustering(n_clusters=best_k, metric='cosine', linkage='average').fit_predict(embeddings)

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
