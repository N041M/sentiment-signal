"""Unit tests for the chunking + aggregation helpers (no model load required).

These cover the document-chunking logic that fixes FinBERT's 512-token truncation:
long documents are split into windows, scored per window, then token-weighted
aggregated back to a single document score/embedding.
"""

import numpy as np
import pytest

from sentiment_signal.nlp.pipeline import chunk_windows, weighted_average


class TestChunkWindows:
    def test_empty(self):
        assert chunk_windows([], 10) == []

    def test_shorter_than_window(self):
        assert chunk_windows([1, 2, 3], 10) == [[1, 2, 3]]

    def test_exact_multiple(self):
        assert chunk_windows([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

    def test_with_remainder(self):
        assert chunk_windows([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_covers_all_tokens_without_overlap(self):
        ids = list(range(1000))
        chunks = chunk_windows(ids, 510)
        # No token lost, none duplicated
        flat = [t for c in chunks for t in c]
        assert flat == ids
        assert len(chunks) == 2  # 510 + 490

    def test_nonpositive_window(self):
        assert chunk_windows([1, 2, 3], 0) == []


class TestWeightedAverage:
    def test_equal_weights_is_plain_mean(self):
        vecs = [[1.0, 0.0], [0.0, 1.0]]
        assert np.allclose(weighted_average(vecs, [1, 1]), [0.5, 0.5])

    def test_weighting_favours_larger_chunk(self):
        # A long chunk (weight 9) and a short one (weight 1) -> result near the long one
        out = weighted_average([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], [9, 1])
        assert out[0] == pytest.approx(0.9)
        assert out[2] == pytest.approx(0.1)

    def test_zero_weights_fall_back_to_equal(self):
        out = weighted_average([[1.0, 0.0], [0.0, 1.0]], [0, 0])
        assert np.allclose(out, [0.5, 0.5])

    def test_single_vector(self):
        assert np.allclose(weighted_average([[0.2, 0.3, 0.5]], [7]), [0.2, 0.3, 0.5])

    def test_probabilities_stay_normalised(self):
        # Aggregating probability vectors should still sum to ~1
        out = weighted_average([[0.7, 0.2, 0.1], [0.1, 0.1, 0.8]], [300, 100])
        assert out.sum() == pytest.approx(1.0)
