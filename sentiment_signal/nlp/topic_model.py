"""BERTopic topic modelling for the speech corpus.

Replaces the previous FinBERT-embedding HDBSCAN clustering (`clustering.py`), which
clustered on a *sentiment* embedding and produced topic-incoherent blobs — one
1,200-doc grab-bag of central-bank speeches (see build log §13.25). Instead this:

  1. embeds each speech with a topic-semantic sentence-transformer, chunked and
     mean-pooled so a 40k-char speech is represented by its whole content;
  2. runs BERTopic (UMAP + HDBSCAN + class-based TF-IDF) on those embeddings;
  3. labels each topic with a **secondary** = the topic's c-TF-IDF words (the
     data-driven sub-topic) and a **main** = the hand lexicon's broad headline
     applied to those words (a clean ~12-way grouping for colour/filter).

The lexicon is thus kept only for the broad headline (never the problem); BERTopic
owns the secondary (which was collapsing). Output maps onto the existing
`statement_analysis` columns: cluster_id, topic_main, topic_classification, umap_x/y.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from loguru import logger

from sentiment_signal.nlp.topic_lexicon import classify

DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"  # fast; swap to all-mpnet-base-v2 for higher quality


@dataclass
class TopicResult:
    """Per-document topic assignment plus per-topic labels."""

    topic_ids: list[int]  # BERTopic topic id per document (-1 = outlier, if any remain)
    main_of: dict[int, str]  # topic id -> broad main headline (from lexicon)
    secondary_of: dict[int, str]  # topic id -> c-TF-IDF secondary label
    umap_x: list[float]
    umap_y: list[float]
    sizes: dict[int, int]  # topic id -> document count


def _chunked_embed(
    model, texts: list[str], max_words: int = 256, max_chunks: int = 8
) -> np.ndarray:
    """Mean-pool sentence-transformer embeddings over up to `max_chunks` word-windows
    per document, so long speeches are represented by their whole content rather than
    just the first ~256 tokens the model would otherwise see."""
    all_chunks: list[str] = []
    spans: list[tuple[int, int]] = []
    for t in texts:
        words = (t or "").split()
        chunks = [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)][
            :max_chunks
        ] or [""]
        spans.append((len(all_chunks), len(all_chunks) + len(chunks)))
        all_chunks.extend(chunks)
    vecs = model.encode(
        all_chunks, batch_size=128, normalize_embeddings=True, show_progress_bar=False
    )
    pooled = np.vstack([vecs[a:b].mean(axis=0) for a, b in spans])
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)


def _secondary_label(words: list[tuple[str, float]], n: int = 4) -> str:
    """A readable secondary label from a topic's top c-TF-IDF terms."""
    return ", ".join(w for w, _ in words[:n]) if words else "general"


def fit_topics(
    texts: list[str],
    *,
    embed_model: str = DEFAULT_EMBED_MODEL,
    min_topic_size: int = 20,
    nr_topics: int | None = None,
    reduce_outliers: bool = True,
) -> TopicResult:
    """Fit BERTopic on `texts` and return per-document topics + per-topic labels."""
    from bertopic import BERTopic
    from sentence_transformers import SentenceTransformer
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    logger.info(f"Embedding {len(texts)} docs with {embed_model} (chunked, mean-pooled)…")
    emb = _chunked_embed(SentenceTransformer(embed_model), texts)

    logger.info("Fitting BERTopic (UMAP + HDBSCAN + c-TF-IDF)…")
    umap_model = UMAP(
        n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42
    )
    vectorizer = CountVectorizer(stop_words="english", min_df=5, ngram_range=(1, 2))
    model = BERTopic(
        umap_model=umap_model,
        vectorizer_model=vectorizer,
        min_topic_size=min_topic_size,
        nr_topics=nr_topics,
        verbose=False,
    )
    topics, _ = model.fit_transform(texts, embeddings=emb)

    if reduce_outliers and -1 in set(topics):
        logger.info("Reassigning outliers to nearest topic…")
        topics = model.reduce_outliers(texts, topics, strategy="embeddings", embeddings=emb)
        model.update_topics(texts, topics=topics, vectorizer_model=vectorizer)

    logger.info("Reducing embeddings to 2-D for the scatter…")
    xy = UMAP(
        n_neighbors=15, n_components=2, min_dist=0.0, metric="cosine", random_state=42
    ).fit_transform(emb)

    # Group document texts per topic so the broad main headline comes from the lexicon
    # applied to representative *prose* (it needs multi-word phrases like "financial
    # stability"/"bank capital", which comma-joined c-TF-IDF tokens don't contain).
    # The secondary stays the topic's c-TF-IDF words (the data-driven sub-topic).
    topic_docs: dict[int, list[str]] = {}
    for t, txt in zip(topics, texts):
        topic_docs.setdefault(int(t), []).append(txt)

    main_of: dict[int, str] = {}
    secondary_of: dict[int, str] = {}
    for tid in sorted(set(topics)):
        if tid == -1:
            main_of[tid], secondary_of[tid] = "Other", "unclustered"
            continue
        words = model.get_topic(tid) or []
        secondary_of[tid] = _secondary_label(words)
        sample = " ".join(topic_docs[tid][:40])[:20000]
        main_of[tid] = classify(sample)[0]

    return TopicResult(
        topic_ids=[int(t) for t in topics],
        main_of=main_of,
        secondary_of=secondary_of,
        umap_x=[float(v) for v in xy[:, 0]],
        umap_y=[float(v) for v in xy[:, 1]],
        sizes=dict(Counter(int(t) for t in topics)),
    )
