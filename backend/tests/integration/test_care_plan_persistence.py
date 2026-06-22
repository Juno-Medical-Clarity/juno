import io
import json
import logging
from unittest.mock import ANY, patch

import pytest

from models.metrics import Metrics
import routes.care_plan as care_plan_module


class FakePipeline:
    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return f"simplified: {text}"

    def clarify_and_action(self, simplified, abbreviations):
        return f"clarified: {simplified}"

    def structure_appointment_note(self, clarified):
        return {"summary": clarified}


def _events_from_response(response):
    events = []
    for block in response.get_data(as_text=True).strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block.removeprefix("data: ")))
    return events


def _events_from_chunks(chunks):
    events = []
    for chunk in chunks:
        if isinstance(chunk, tuple):
            continue  # skip __result__ sentinel
        for block in chunk.strip().split("\n\n"):
            if block.startswith("data: "):
                events.append(json.loads(block.removeprefix("data: ")))
    return events


def _docx_bytes(text):
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    buffer.seek(0)
    return buffer


@patch("routes.care_plan.save_care_plan_output")
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
    save_care_plan_output,
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
    save_care_plan_output.assert_not_called()


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.care_plan.save_care_plan_output", return_value="saved-123")
@patch("routes.care_plan.upload_combined_pdf", return_value="gs://bucket/input.pdf")
@patch("routes.care_plan.merge_pdfs", return_value=b"%PDF combined")
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
def test_multi_file_input_is_concatenated_and_saved_after_result(
    _pipeline,
    _detect_terms,
    _glossary,
    _score,
    merge_pdfs,
    upload_combined_pdf,
    save_care_plan_output,
    _verify_token,
    client,
):
    response = client.post(
        "/care_plan",
        headers={"Authorization": "Bearer token"},
        data={
            "version": "v1-2",
            "files": [
                (io.BytesIO(b"first note"), "a.txt"),
                (io.BytesIO(b"second note"), "b.txt"),
            ]
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    events = _events_from_response(response)
    result_event = events[-1]
    assert result_event["step"] == "result"
    assert result_event["data"]["metrics"]["saved_id"] == "saved-123"
    assert result_event["data"]["metrics"]["session_id"] is not None
    assert isinstance(result_event["data"]["metrics"]["session_id"], str)
    assert "first note" in result_event["data"]["care_plan"]["raw"]["text"]
    assert "second note" in result_event["data"]["care_plan"]["raw"]["text"]
    assert "Source: a.txt" in result_event["data"]["care_plan"]["raw"]["text"]
    assert "Source: b.txt" in result_event["data"]["care_plan"]["raw"]["text"]

    merge_pdfs.assert_called_once()
    upload_combined_pdf.assert_called_once_with(b"%PDF combined", "user-1")
    save_care_plan_output.assert_called_once()
    saved_kwargs = save_care_plan_output.call_args.kwargs
    assert saved_kwargs["user_id"] == "user-1"
    assert saved_kwargs["source_filename"] == "a.txt, b.txt"
    assert "input_pdf_gcs" not in saved_kwargs
    # pdf_gcs_url now lives inside output_data.input (SP-11)
    persisted_output = saved_kwargs["output_data"]
    assert persisted_output["input"]["pdf_gcs_url"] == "gs://bucket/input.pdf"
    assert persisted_output["metrics"]["saved_id"] == "saved-123"


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.care_plan.save_care_plan_output", return_value="saved-123")
@patch("routes.care_plan.upload_combined_pdf", return_value="gs://bucket/input.pdf")
@patch("routes.care_plan.merge_pdfs", return_value=b"%PDF combined")
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
def test_uploaded_docx_content_is_included_in_combined_pdf_artifact(
    _pipeline,
    _detect_terms,
    _glossary,
    _score,
    merge_pdfs,
    upload_combined_pdf,
    _save_care_plan_output,
    _verify_token,
    client,
):
    response = client.post(
        "/care_plan",
        headers={"Authorization": "Bearer token"},
        data={
            "version": "v1-2",
            "files": [(_docx_bytes("docx clinical note"), "visit.docx")],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    _events_from_response(response)
    merge_pdfs.assert_called_once_with([(b"docx clinical note", "visit.txt")])
    upload_combined_pdf.assert_called_once_with(b"%PDF combined", "user-1")


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_multi_file_upload_rejects_too_many_files(_verify_token, client, caplog):
    with caplog.at_level(logging.ERROR, logger="utils.juno_logger"):
        response = client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={
                "version": "v1-2",
                "files": [
                    (io.BytesIO(f"note {index}".encode("utf-8")), f"{index}.txt")
                    for index in range(11)
                ]
            },
            content_type="multipart/form-data",
        )
        events = _events_from_response(response)

    assert events[-1]["step"] == "error"
    assert "at most 10 files" in events[-1]["error"]


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.care_plan.MAX_AGGREGATE_FILE_BYTES", 10, create=True)
@patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline())
def test_multi_file_upload_rejects_aggregate_size_over_limit(_pipeline, _verify_token, client, caplog):
    with caplog.at_level(logging.ERROR, logger="utils.juno_logger"):
        response = client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={
                "version": "v1-2",
                "files": [
                    (io.BytesIO(b"abcdef"), "a.txt"),
                    (io.BytesIO(b"ghijkl"), "b.txt"),
                ]
            },
            content_type="multipart/form-data",
        )
        events = _events_from_response(response)

    assert events[-1]["step"] == "error"
    assert "combined upload size exceeds" in events[-1]["error"]


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.care_plan.save_care_plan_output")
@patch("routes.care_plan.upload_combined_pdf")
@patch("routes.care_plan.merge_pdfs", return_value=b"%PDF combined")
@patch("routes.care_plan._fetch_from_gcs", return_value=(b"stored note", "stored.txt"))
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
def test_doc_id_input_is_processed_but_not_persisted(
    _pipeline,
    _detect_terms,
    _glossary,
    _score,
    _fetch_from_gcs,
    merge_pdfs,
    upload_combined_pdf,
    save_care_plan_output,
    _verify_token,
    client,
):
    response = client.post(
        "/care_plan",
        headers={"Authorization": "Bearer token"},
        data={"version": "v1-2", "doc_id": "legacy-doc"},
    )

    events = _events_from_response(response)
    result_event = events[-1]
    assert result_event["step"] == "result"
    assert "stored note" in result_event["data"]["care_plan"]["raw"]["text"]
    assert result_event["data"]["metrics"]["saved_id"] is None
    assert result_event["data"]["metrics"]["session_id"] is not None
    assert isinstance(result_event["data"]["metrics"]["session_id"], str)
    merge_pdfs.assert_called_once_with(ANY)
    upload_combined_pdf.assert_not_called()
    save_care_plan_output.assert_not_called()


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.care_plan.save_care_plan_output", side_effect=RuntimeError("no firestore"))
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
def test_save_failure_returns_result_without_saved_id(
    _pipeline,
    _detect_terms,
    _glossary,
    _score,
    save_care_plan_output,
    _verify_token,
    client,
    caplog,
):
    with caplog.at_level(logging.ERROR, logger="utils.juno_logger"):
        response = client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={"version": "v1-2", "text": "plain note"},
        )
        events = _events_from_response(response)

    assert response.status_code == 200
    result_event = events[-1]
    assert result_event["step"] == "result"
    assert result_event["data"]["metrics"]["saved_id"] is None
    assert result_event["data"]["metrics"]["session_id"] is not None
    assert isinstance(result_event["data"]["metrics"]["session_id"], str)
    save_care_plan_output.assert_called_once()
    assert "failed to save output" in caplog.text
