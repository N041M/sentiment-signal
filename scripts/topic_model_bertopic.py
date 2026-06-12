#!/usr/bin/env python3
"""Prototype: BERTopic topic modelling, to compare against the FinBERT-embedding
HDBSCAN clustering that produced topic-incoherent blobs (see build log §13.25).

Why this exists: clustering currently runs on FinBERT's CLS vector, a *sentiment*
embedding (silhouette of topic sub-themes = -0.04, i.e. no topic structure), so
central-bank speeches collapse into one 1,200-doc grab-bag. BERTopic instead uses a
topic-semantic sentence-transformer embedding + UMAP + HDBSCAN + class-based TF-IDF.

This script only *reports* (it does not write to the DB): topic count/sizes/words,
and how the current 'Monetary policy' speeches redistribute across BERTopic topics
(the un-lumping test). Embeddings are sentence-transformer, chunked + mean-pooled so
long speeches aren't truncated to their introduction.

    python scripts/topic_model_bertopic.py
"""

import sys

sys.path.insert(0, ".")

import collections

import numpy as np
from loguru import logger
from sqlalchemy import select

from sentiment_signal.db.models import Statement, StatementAnalysis
from sentiment_signal.db.session import SessionLocal

EMB_MODEL = (
    "all-MiniLM-L6-v2"  # fast topic-semantic embedder; swap to all-mpnet-base-v2 for quality
)


def chunked_embed(model, texts: list[str], max_words: int = 256, max_chunks: int = 8) -> np.ndarray:
    """Mean-pool sentence-transformer embeddings over up to max_chunks word-windows
    per document, so a 40k-char speech is represented by its whole content, not just
    the first 256 tokens the model would otherwise see."""
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


def main() -> None:
    session = SessionLocal()
    rows = session.execute(
        select(StatementAnalysis.statement_id, Statement.raw_text, StatementAnalysis.topic_main)
        .join(Statement, Statement.id == StatementAnalysis.statement_id)
        .where(StatementAnalysis.embedding.isnot(None))
    ).all()
    session.close()
    texts = [r[1] or "" for r in rows]
    cur_main = [r[2] for r in rows]

    logger.info(f"{len(texts)} docs; embedding with {EMB_MODEL} (chunked, mean-pooled)…")
    from sentence_transformers import SentenceTransformer

    emb = chunked_embed(SentenceTransformer(EMB_MODEL), texts)

    logger.info("Running BERTopic (UMAP + HDBSCAN + c-TF-IDF)…")
    from bertopic import BERTopic
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    umap_model = UMAP(
        n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42
    )
    vectorizer = CountVectorizer(stop_words="english", min_df=5, ngram_range=(1, 2))
    tm = BERTopic(
        umap_model=umap_model, vectorizer_model=vectorizer, min_topic_size=20, verbose=False
    )
    topics, _ = tm.fit_transform(texts, embeddings=emb)

    info = tm.get_topic_info()
    n_topics = len([t for t in info["Topic"] if t != -1])
    n_outliers = (
        int(info.loc[info["Topic"] == -1, "Count"].sum()) if (info["Topic"] == -1).any() else 0
    )
    logger.info(f"BERTopic found {n_topics} topics, {n_outliers} outliers")

    print("\nTop BERTopic topics (id | size | top words):")
    for _, row in info.head(22).iterrows():
        if row["Topic"] == -1:
            continue
        words = ", ".join(w for w, _ in tm.get_topic(row["Topic"])[:7])
        print(f"  {row['Topic']:>3}  {row['Count']:5d}  {words}")

    mono = collections.Counter(t for t, m in zip(topics, cur_main) if m == "Monetary policy")
    n_mono_topics = len([k for k in mono if k != -1])
    print(
        f"\nUn-lumping test: current 'Monetary policy' speeches now span {n_mono_topics} BERTopic topics"
    )
    print("(was 1 FinBERT cluster). Top destinations:")
    for tid, c in mono.most_common(10):
        words = "(outliers)" if tid == -1 else ", ".join(w for w, _ in tm.get_topic(tid)[:6])
        print(f"   topic {tid:>3}: {c:5d}  {words}")


if __name__ == "__main__":
    main()
