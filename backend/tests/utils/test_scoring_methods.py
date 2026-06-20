"""Tests for backend/utils/scoring_methods.py — per-method score extraction."""

import sys
import unittest
from pathlib import Path

import textstat

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
for p in (PROJECT_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from utils.scoring import _grade_to_score, score_text
from utils.scoring_methods import (
    compute_method_scores,
    score_cdc_cci,
    score_dale_chall,
    score_flesch_kincaid,
    score_pemat,
    score_sam,
    score_smog,
)

# Short text (< 30 sentences) used for SMOG insufficient-sample tests
SHORT_TEXT = "The patient has hypertension. Take your medication daily. Call your doctor if you have chest pain."

# Long enough text (30+ sentences) for SMOG to work — repeat SHORT_TEXT until we have > 30 sentences.
LONG_TEXT = (SHORT_TEXT + " ") * 15  # ~45 sentences


class TestScoreSmog(unittest.TestCase):
    def test_short_text_insufficient_sample(self):
        result = score_smog(SHORT_TEXT)
        self.assertTrue(result["insufficient_sample"])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["grade"], 0.0)

    def test_long_text_has_grade(self):
        result = score_smog(LONG_TEXT)
        self.assertFalse(result["insufficient_sample"])
        self.assertIn("score", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        # grade should match textstat directly
        self.assertAlmostEqual(result["grade"], round(textstat.smog_index(LONG_TEXT), 1), places=1)


class TestScoreFleschKincaid(unittest.TestCase):
    def test_score_in_range(self):
        result = score_flesch_kincaid(SHORT_TEXT)
        self.assertIn("reading_ease", result)
        self.assertIn("grade_level", result)
        self.assertIn("score", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_score_equals_clamped_reading_ease(self):
        result = score_flesch_kincaid(SHORT_TEXT)
        expected = max(0, min(100, round(textstat.flesch_reading_ease(SHORT_TEXT))))
        self.assertEqual(result["score"], expected)


class TestScoreDaleChall(unittest.TestCase):
    def test_returns_expected_keys(self):
        result = score_dale_chall(SHORT_TEXT)
        self.assertIn("raw_score", result)
        self.assertIn("grade_range", result)
        self.assertIn("score", result)

    def test_score_in_range(self):
        result = score_dale_chall(SHORT_TEXT)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


class TestScorePemat(unittest.TestCase):
    def _make_dims(self, score=70):
        return {
            "jargon_density": {"score": score},
            "sentence_complexity": {"score": score},
            "passive_voice": {"score": score},
            "numeracy_clarity": {"score": score},
            "structural_clarity": {"score": score},
            "actionability": {"score": score},
            "grade_level": {"score": score},
        }

    def test_returns_expected_keys(self):
        result = score_pemat(self._make_dims())
        self.assertIn("understandability", result)
        self.assertIn("actionability", result)
        self.assertIn("score", result)

    def test_score_in_range(self):
        result = score_pemat(self._make_dims(50))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


class TestScoreSam(unittest.TestCase):
    def _make_dims(self, score=70):
        return {
            "grade_level": {"score": score},
            "jargon_density": {"score": score},
            "sentence_complexity": {"score": score},
            "passive_voice": {"score": score},
            "structural_clarity": {"score": score},
            "actionability": {"score": score},
            "numeracy_clarity": {"score": score},
        }

    def test_returns_expected_keys(self):
        result = score_sam(self._make_dims())
        self.assertIn("content", result)
        self.assertIn("literacy_demand", result)
        self.assertIn("layout_typography", result)
        self.assertIn("score", result)

    def test_score_in_range(self):
        result = score_sam(self._make_dims(80))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


class TestScoreCdcCci(unittest.TestCase):
    def _make_dims(self, actionability=70, numeracy=70):
        return {
            "actionability": {"score": actionability},
            "numeracy_clarity": {"score": numeracy},
            "grade_level": {"score": 70},
            "jargon_density": {"score": 70},
            "sentence_complexity": {"score": 70},
            "passive_voice": {"score": 70},
            "structural_clarity": {"score": 70},
        }

    def test_all_items_met_when_high_scores(self):
        result = score_cdc_cci(self._make_dims(actionability=80, numeracy=80))
        self.assertEqual(result["main_message"], 1)
        self.assertEqual(result["behavioral_recommendations"], 1)
        self.assertEqual(result["numbers"], 1)
        self.assertEqual(result["call_to_action"], 1)
        self.assertEqual(result["score"], 100)

    def test_no_items_met_when_low_scores(self):
        result = score_cdc_cci(self._make_dims(actionability=20, numeracy=20))
        self.assertEqual(result["main_message"], 0)
        self.assertEqual(result["score"], 0)


class TestComputeMethodScores(unittest.TestCase):
    def test_returns_all_six_methods(self):
        full_score = score_text(LONG_TEXT)
        result = compute_method_scores(LONG_TEXT, full_score["dimensions"])
        expected_keys = {"smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci"}
        self.assertEqual(set(result.keys()), expected_keys)

    def test_each_method_has_score_in_range(self):
        full_score = score_text(SHORT_TEXT)
        result = compute_method_scores(SHORT_TEXT, full_score["dimensions"])
        for name, m in result.items():
            self.assertIn("score", m, f"{name} missing 'score'")
            self.assertGreaterEqual(m["score"], 0, f"{name} score < 0")
            self.assertLessEqual(m["score"], 100, f"{name} score > 100")

    def test_smog_insufficient_sample_for_short_text(self):
        full_score = score_text(SHORT_TEXT)
        result = compute_method_scores(SHORT_TEXT, full_score["dimensions"])
        self.assertTrue(result["smog"]["insufficient_sample"])
        self.assertEqual(result["smog"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
