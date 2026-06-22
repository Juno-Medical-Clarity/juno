"""Tests for free read-path tolerance on strict model payloads."""

import json
from pathlib import Path

from backend.models.care_plan_versions.v1_2 import CarePlanV1_2


FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "care_plan_v1_2.json"


def test_care_plan_v1_2_without_raw_validates_for_free_read_tolerance():
    data = json.loads(FIXTURE_PATH.read_text())
    data.pop("raw")

    # PRD §9-1: no migration or legacy-handling code; this is only free read tolerance.
    model = CarePlanV1_2.model_validate(data)

    assert model.raw is None
