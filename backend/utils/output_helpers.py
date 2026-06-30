"""Shared output-name derivation helper."""


def derive_output_name(
    care_plan_data: dict,
    source_filename: str = "",
    group_fallback: str = "",
) -> str:
    """Derive a human-readable output name from care plan data.

    Priority (each result capped at 60 chars):
    1. reason_for_visit[0].reason (title-cased)
    2. diagnosis.main_conclusion first sentence
    3. source_filename stem (if not '' and not 'text_input')
    4. group_fallback (e.g. '{group} {input_id}' for batch)
    5. 'Appointment'
    """
    try:
        rfv = care_plan_data.get("reason_for_visit")
        if rfv and isinstance(rfv, list):
            reason = (rfv[0].get("reason") or "").strip()
            if reason:
                return reason.title()[:60]
        diagnosis = care_plan_data.get("diagnosis") or {}
        main = (diagnosis.get("main_conclusion") or "").strip()
        if main:
            first_sentence = main.split(".")[0].strip()
            if first_sentence:
                return first_sentence[:60]
    except Exception:
        pass
    filename = source_filename or ""
    if filename and filename != "text_input":
        stem = filename.split(",")[0].strip()
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        stem = stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem.title()[:60]
    if group_fallback:
        return group_fallback.title()[:60]
    return "Appointment"
