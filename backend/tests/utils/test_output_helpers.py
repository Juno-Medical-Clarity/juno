"""Tests for utils/output_helpers.py"""
from utils.output_helpers import derive_output_name


def test_rfv_reason_title_cased():
    result = derive_output_name({"reason_for_visit": [{"reason": "chest pain"}]})
    assert result == "Chest Pain"


def test_diagnosis_fallback():
    data = {"reason_for_visit": [], "diagnosis": {"main_conclusion": "Hypertension. More details."}}
    result = derive_output_name(data)
    assert result == "Hypertension"


def test_filename_fallback():
    result = derive_output_name({}, source_filename="annual_checkup.pdf")
    assert result == "Annual Checkup"


def test_group_fallback():
    result = derive_output_name({}, group_fallback="sp1 0001")
    assert result == "Sp1 0001"


def test_appointment_fallback():
    result = derive_output_name({})
    assert result == "Appointment"


def test_max_60_chars():
    long_reason = "a" * 100
    result = derive_output_name({"reason_for_visit": [{"reason": long_reason}]})
    assert len(result) == 60


def test_text_input_filename_skipped():
    result = derive_output_name({}, source_filename="text_input")
    assert result == "Appointment"
