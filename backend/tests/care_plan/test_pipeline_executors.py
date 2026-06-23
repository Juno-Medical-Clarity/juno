import json
from unittest.mock import patch

from models.metrics import Metrics
import routes.care_plan as care_plan_module


class FakePipeline:
    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return f"simplified: {text}"

    def clarify_and_action(self, simplified, abbreviations):
        return f"clarified: {simplified}"

    def structure_appointment_note(self, clarified):
        return {"summary": clarified}


def _events_from_chunks(chunks):
    events = []
    for chunk in chunks:
        if isinstance(chunk, tuple):
            continue  # skip __result__ sentinel
        for block in chunk.strip().split("\n\n"):
            if block.startswith("data: "):
                events.append(json.loads(block.removeprefix("data: ")))
    return events


@patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "Patient-friendly", "word_count": 100, "dimensions": {"grade_level": {"score": 70, "raw": 6.0, "label": "Grade Level", "unit": "grade"}, "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon Density", "unit": "proportion"}, "sentence_complexity": {"score": 70, "raw": 12.0, "label": "Sentence Length", "unit": "words/sentence"}, "passive_voice": {"score": 70, "raw": 0.1, "label": "Active Voice", "unit": "passive ratio"}, "actionability": {"score": 70, "raw": 0.05, "label": "Actionability", "unit": "you-rate"}, "numeracy_clarity": {"score": 70, "raw": 1.0, "label": "Numeric Clarity", "unit": "vague count"}, "structural_clarity": {"score": 70, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"}}})
@patch("routes.care_plan.build_glossary_from_simplified_text", return_value={})
@patch(
    "routes.care_plan.detect_terms",
    return_value={
        "substitution_candidates": [],
        "preserve_and_define_terms": [],
        "abbreviations": [],
    },
)
@patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline())
def test_run_care_plan_pipeline_direct_text_yields_steps_and_result_sentinel(
    _pipeline,
    _detect_terms,
    _glossary,
    _score,
):
    metrics = Metrics.start(
        session_id="session-1",
        pipeline_version="v1-2",
        input_type="text",
    )

    chunks = list(care_plan_module.run_care_plan_pipeline(
        "plain note",
        metrics,
        grading_enabled=False,
    ))

    # All string chunks should be step SSE events (not result events)
    str_chunks = [c for c in chunks if isinstance(c, str)]
    events = _events_from_chunks(str_chunks)
    assert [(event["step"], event.get("status")) for event in events] == [
        (2, "active"),
        (2, "done"),
        (3, "active"),
        (3, "done"),
        (4, "active"),
        (4, "done"),
        (5, "active"),
        (5, "done"),
    ]
    # The last chunk should be the __result__ sentinel tuple, not an SSE event
    tuple_chunks = [c for c in chunks if isinstance(c, tuple)]
    assert len(tuple_chunks) == 1
    assert tuple_chunks[0][0] == "__result__"
