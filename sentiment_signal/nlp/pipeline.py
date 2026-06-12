from __future__ import annotations

import numpy as np
import torch
from loguru import logger
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from sentiment_signal.config import settings

FINBERT = "ProsusAI/finbert"
FOMC_ROBERTA = "gtfintechlab/FOMC-RoBERTa"
DISTILBERT_SST = "distilbert-base-uncased-finetuned-sst-2-english"
EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"

# Stored in statement_analysis.model_version. Bump when the scoring method changes
# so step3 knows which rows are stale and must be re-scored.
FINBERT_CHUNKED_VERSION = "ProsusAI/finbert+chunk-meanpool-v1"

# Transformer context limit; leave room for the [CLS]/[SEP] special tokens.
_MAX_TOKENS = 512
_CHUNK_TOKENS = _MAX_TOKENS - 2

# FOMC-RoBERTa label mapping: HAWKISH=restrictive, DOVISH=accommodative
# hawkish_score = P(HAWKISH) - P(DOVISH)  →  >0 hawkish, <0 dovish
_FOMC_LABEL_MAP = {0: "hawkish", 1: "dovish", 2: "neutral"}


def _best_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def chunk_windows(ids: list[int], window: int) -> list[list[int]]:
    """Split a token-id list into consecutive windows of at most `window` ids."""
    if not ids or window <= 0:
        return []
    return [ids[i : i + window] for i in range(0, len(ids), window)]


def weighted_average(vectors: list, weights: list) -> np.ndarray:
    """Weighted mean of row vectors. Falls back to equal weights if all are zero."""
    a = np.asarray(vectors, dtype=float)
    w = np.asarray(weights, dtype=float)
    if w.sum() == 0:
        w = np.ones_like(w)
    return np.average(a, axis=0, weights=w)


class NLPPipeline:
    """Loads a single transformer and runs batch sentiment scoring + embedding."""

    def __init__(self, model_name: str = FINBERT, device: str | None = None) -> None:
        self.model_name = model_name
        self.device = device or _best_device()
        # float16 matmul is not implemented on CPU (raises "addmm_impl_cpu_ not
        # implemented for 'Half'"), so only use half precision on a GPU device.
        self.use_fp16 = self.device in ("cuda", "mps")
        logger.info(f"NLPPipeline: model={model_name}, device={self.device}, fp16={self.use_fp16}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # We chunk manually and always pass an explicit max_length when truncating, so
        # disable the tokenizer's default length check — otherwise encoding a long
        # document in _chunk_text logs a "sequence too long" warning for every document.
        self.tokenizer.model_max_length = int(1e9)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        if self.use_fp16:
            model = model.half()  # halves VRAM, negligible accuracy loss at inference
        self.model = model.to(self.device)
        self.model.eval()

    def _probs_to_score_label(self, probs) -> tuple[float, str]:
        """Map a probability vector to a polarity score (pos − neg) and a label."""
        probs = np.asarray(probs, dtype=float)
        id2label = self.model.config.id2label
        label = id2label[int(probs.argmax())].lower()
        pos_idx = next((k for k, v in id2label.items() if "pos" in v.lower()), None)
        neg_idx = next((k for k, v in id2label.items() if "neg" in v.lower()), None)
        score = (
            float(probs[pos_idx] - probs[neg_idx])
            if pos_idx is not None and neg_idx is not None
            else 0.0
        )
        return score, label

    def score_batch(self, texts: list[str]) -> list[dict]:
        """Return sentiment score ∈ [-1, 1], label, and raw probs for each text.

        Each text is truncated to one 512-token window — use analyze_documents for
        long documents that must be scored in full.
        """
        results: list[dict] = []
        for i in range(0, len(texts), settings.nlp_batch_size):
            batch = texts[i : i + settings.nlp_batch_size]
            inputs = self.tokenizer(
                batch, return_tensors="pt", truncation=True, padding=True, max_length=_MAX_TOKENS
            ).to(self.device)
            with torch.no_grad():
                logits = self.model(**inputs).logits
            probs = logits.float().softmax(dim=-1).cpu()
            for prob_row in probs:
                score, label = self._probs_to_score_label(prob_row)
                results.append(
                    {"sentiment_score": score, "sentiment_label": label, "probs": prob_row.tolist()}
                )
        return results

    def _chunk_text(self, text: str) -> list[tuple[str, int]]:
        """Split text into (chunk_text, token_count) windows of ≤ _CHUNK_TOKENS tokens."""
        ids = self.tokenizer.encode(text or "", add_special_tokens=False)
        windows = chunk_windows(ids, _CHUNK_TOKENS)
        return [(self.tokenizer.decode(w, skip_special_tokens=True), len(w)) for w in windows]

    def analyze_documents(self, texts: list[str]) -> list[dict]:
        """Score + embed full documents by chunking, then token-weighted aggregation.

        FinBERT truncates at 512 tokens; most speeches/orders are far longer, so a
        single pass scores only the opening. This splits each document into 512-token
        chunks, scores and embeds every chunk, then aggregates (token-weighted mean of
        the class probabilities and of the CLS embeddings) into one document result.

        Returns per-document dicts: sentiment_score, sentiment_label, probs (aggregated),
        embedding (768-d, mean-pooled), n_chunks.
        """
        # Flatten all chunks across documents into one list, tracking per-doc spans.
        all_chunks: list[str] = []
        weights: list[int] = []
        spans: list[tuple[int, int]] = []
        for text in texts:
            chunks = self._chunk_text(text) or [("", 1)]  # placeholder for empty text
            start = len(all_chunks)
            for chunk_text, n_tokens in chunks:
                all_chunks.append(chunk_text)
                weights.append(n_tokens)
            spans.append((start, len(all_chunks)))

        chunk_scores = self.score_batch(all_chunks)
        chunk_embeds = self.embed_batch(all_chunks)

        results: list[dict] = []
        for start, end in spans:
            w = weights[start:end]
            agg_probs = weighted_average([chunk_scores[i]["probs"] for i in range(start, end)], w)
            agg_embed = weighted_average([chunk_embeds[i] for i in range(start, end)], w)
            score, label = self._probs_to_score_label(agg_probs)
            results.append(
                {
                    "sentiment_score": score,
                    "sentiment_label": label,
                    "probs": agg_probs.tolist(),
                    "embedding": agg_embed.tolist(),
                    "n_chunks": end - start,
                }
            )
        return results

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return CLS-token embeddings (dim=768) for pgvector storage."""
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), settings.nlp_batch_size):
            batch = texts[i : i + settings.nlp_batch_size]
            inputs = self.tokenizer(
                batch, return_tensors="pt", truncation=True, padding=True, max_length=_MAX_TOKENS
            ).to(self.device)
            with torch.no_grad():
                hidden = self.model(**inputs, output_hidden_states=True).hidden_states[-1]
            cls = hidden[:, 0, :].float().cpu()
            embeddings.extend(cls.tolist())
        return embeddings

    def score_hawkish_dovish(self, texts: list[str]) -> list[dict]:
        """Score texts with FOMC-RoBERTa (hawkish / neutral / dovish).

        Returns dicts with hawkish_score ∈ [-1, 1] and hawkish_label.
        Loads the model lazily on first call.
        """
        if not hasattr(self, "_fomc_tokenizer"):
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._fomc_tokenizer = AutoTokenizer.from_pretrained(FOMC_ROBERTA)
            fomc_model = AutoModelForSequenceClassification.from_pretrained(FOMC_ROBERTA)
            if self.use_fp16:
                fomc_model = fomc_model.half()
            self._fomc_model = fomc_model.to(self.device)
            self._fomc_model.eval()

        results: list[dict] = []
        for i in range(0, len(texts), settings.nlp_batch_size):
            batch = texts[i : i + settings.nlp_batch_size]
            inputs = self._fomc_tokenizer(
                batch,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512,
            ).to(self.device)
            with torch.no_grad():
                logits = self._fomc_model(**inputs).logits
            probs = logits.float().softmax(dim=-1).cpu()
            for prob_row in probs:
                # FOMC-RoBERTa: 0=HAWKISH, 1=DOVISH, 2=NEUTRAL
                p_hawk = float(prob_row[0])
                p_dove = float(prob_row[1])
                score = p_hawk - p_dove
                label = _FOMC_LABEL_MAP[prob_row.argmax().item()]
                results.append(
                    {"hawkish_score": score, "hawkish_label": label, "probs": prob_row.tolist()}
                )
        return results

    def agreement_score(self, stmt_embedding: list[float], rxn_embedding: list[float]) -> float:
        """Cosine similarity between two precomputed embeddings."""
        s = np.array(stmt_embedding, dtype=float)
        r = np.array(rxn_embedding, dtype=float)
        denom = np.linalg.norm(s) * np.linalg.norm(r)
        if denom == 0:
            return 0.0
        return float(np.dot(s, r) / denom)
