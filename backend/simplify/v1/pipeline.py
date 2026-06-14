"""
simplify/v1/pipeline.py — V1 medical document simplification pipeline.

Implements SimplifyPipeline. Refactored from utils/simplify_ai.py.
Steps:
  0. detect_jargon      — scispaCy NER + textstat (deterministic, no LLM)
  1. classify_document  — LLM classifies lab_result vs appointment_note
  A. simplify_language  — rewrite to 6th-grade level (LLM call A)
  B. add_definitions    — inject parenthetical definitions (LLM call B)
  C. clarify_and_action — numeracy + active voice + action emphasis (LLM call C)
  D. structure_document — JSON structuring + question generation (LLM call D)
"""

import json
import logging
import re
import os

import vertexai
from vertexai.preview.generative_models import (
    GenerativeModel,
    GenerationConfig,
    HarmCategory,
    HarmBlockThreshold,
    FinishReason,
)

from simplify.interface import SimplifyPipeline
from utils.scoring import score_text

logger = logging.getLogger(__name__)

# ── Optional scispaCy import ──────────────────────────────────────────────────
try:
    import spacy
    _SPACY_MODEL_NAME = "en_ner_bc5cdr_md"
    try:
        _NLP = spacy.load(_SPACY_MODEL_NAME)
        _SCISPACY_AVAILABLE = True
        logger.info("scispaCy model '%s' loaded successfully", _SPACY_MODEL_NAME)
    except OSError:
        _NLP = None
        _SCISPACY_AVAILABLE = False
        logger.warning(
            "scispaCy model '%s' not found. Falling back to keyword-based jargon "
            "detection. Install with: pip install scispacy && pip install "
            "https://s3-us-west-2.amazonaws.com/ai2-s3-scispacy/releases/v0.5.3/"
            "en_ner_bc5cdr_md-0.5.3.tar.gz",
            _SPACY_MODEL_NAME,
        )
except ImportError:
    _NLP = None
    _SCISPACY_AVAILABLE = False
    logger.warning("spacy/scispaCy not installed. Using keyword-based jargon detection.")

# ── Optional textstat import ──────────────────────────────────────────────────
try:
    import textstat as _textstat
    _TEXTSTAT_AVAILABLE = True
except ImportError:
    _textstat = None  # type: ignore[assignment]
    _TEXTSTAT_AVAILABLE = False
    logger.warning("textstat not installed. Skipping readability grade check.")


# ── AHRQ-inspired substitution list (used in prompt) ─────────────────────────
_AHRQ_SUBSTITUTIONS = """
- "absence of" → "none" / "no"
- "administer" → "give"
- "adverse effects" → "side effects"
- "approximately" → "about"
- "commence" → "start"
- "contraindicated" → "should not be used"
- "discontinue" → "stop"
- "elevated" → "high"
- "facilitate" → "help"
- "hypertension" → "high blood pressure" (unless in jargon list)
- "indicate" → "show"
- "initiate" → "start"
- "medication" → "medicine" (where context allows)
- "monitor" → "check" / "watch"
- "obtain" → "get"
- "perform" → "do"
- "physician" → "doctor"
- "prior to" → "before"
- "sufficient" → "enough"
- "utilize" → "use"
"""

# Common medical abbreviations for regex pre-pass
_ABBREVIATION_MAP = {
    r'\bq\.?d\.?\b':    'once a day',
    r'\bb\.?i\.?d\.?\b': 'twice a day',
    r'\bt\.?i\.?d\.?\b': 'three times a day',
    r'\bq\.?i\.?d\.?\b': 'four times a day',
    r'\bp\.?r\.?n\.?\b': 'as needed',
    r'\ba\.?m\.?\b':    'morning',
    r'\bp\.?m\.?\b':    'evening',
    r'\bp\.?o\.?\b':    'by mouth',
    r'\bi\.?v\.?\b':    'intravenously',
    r'\bi\.?m\.?\b':    'by injection',
    r'\bh\.?s\.?\b':    'at bedtime',
    r'\bstat\b':        'immediately',
}


def _apply_abbreviation_regex(text: str) -> str:
    """Pre-pass: expand common Latin/medical abbreviations."""
    for pattern, replacement in _ABBREVIATION_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Fractions: "1/3" → "1 in 3"
    text = re.sub(r'\b(\d+)/(\d+)\b', lambda m: f'{m.group(1)} in {m.group(2)}', text)
    # Percentages: "25%" → "25 out of 100"
    text = re.sub(r'(\d+(?:\.\d+)?)\s*%', lambda m: f'{m.group(1)} out of 100', text)
    return text


def _keyword_jargon_detect(text: str) -> list[str]:
    """
    Fallback jargon detection when scispaCy is unavailable.
    Returns tokens longer than 8 characters that look like medical terms
    (heuristic: contain no spaces, appear to be Latinate or compound).
    """
    words = re.findall(r'\b[A-Za-z][a-z]{7,}\b', text)
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            result.append(lw)
    return result


class V1Pipeline(SimplifyPipeline):
    """
    Orchestrates the V1 medical document simplification pipeline.

    Each public method corresponds to one pipeline step and can be called
    independently. SSE event emission is handled by the route layer, not here.
    """

    def __init__(self):
        project_id = os.environ.get("GCP_PROJECT_ID", "")
        location = os.environ.get("GCP_LOCATION", "us-central1")
        model_name = os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")

        vertexai.init(project=project_id, location=location)
        self._model = GenerativeModel(model_name)
        self._safety = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH:        HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT:  HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT:  HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT:         HarmBlockThreshold.BLOCK_NONE,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _generate_text(self, prompt: str, temperature: float = 0.3,
                       max_tokens: int = 8192) -> str:
        """Call the model and return raw text response."""
        response = self._model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            safety_settings=self._safety,
        )
        if not response.candidates:
            raise RuntimeError("Model response was blocked or had no candidates")
        candidate = response.candidates[0]
        if (hasattr(candidate, 'finish_reason')
                and candidate.finish_reason == FinishReason.MAX_TOKENS):
            logger.warning("Hit max tokens during text generation — proceeding with partial output")
        return response.text.strip()

    def _generate_json(self, prompt: str, temperature: float = 0.2,
                       max_tokens: int = 8192) -> dict | list:
        """Call the model and parse JSON from the response."""
        raw = self._generate_text(prompt, temperature, max_tokens)
        # Strip markdown code fences
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
        clean = json_match.group(1).strip() if json_match else raw.strip()
        return json.loads(clean)

    # ── Step 0: Jargon detection ──────────────────────────────────────────────

    def detect_jargon(self, text: str) -> dict[str, list[str]]:
        """
        Deterministically identify medical entities and complex terms.

        Returns:
            {
              "medical_jargon": [...],   # preserve as-is (named medical entities)
              "complex_terms":  [...],   # simplify (long/obscure words)
            }
        """
        medical_jargon: list[str] = []
        complex_terms: list[str] = []

        if _SCISPACY_AVAILABLE and _NLP is not None:
            doc = _NLP(text[:100_000])  # cap at 100k chars for performance
            seen_ents: set[str] = set()
            for ent in doc.ents:
                lower = ent.text.lower().strip()
                if lower and lower not in seen_ents:
                    seen_ents.add(lower)
                    medical_jargon.append(ent.text.strip())

            # Complex terms: tokens not in jargon list, length > 8, not stop words
            seen_complex: set[str] = set()
            for token in doc:
                if (not token.is_stop and not token.is_punct
                        and len(token.text) > 8
                        and token.text.lower() not in seen_ents
                        and token.text.lower() not in seen_complex):
                    seen_complex.add(token.text.lower())
                    complex_terms.append(token.text)
        else:
            # Fallback: keyword-based
            all_long = _keyword_jargon_detect(text)
            # Treat anything in a known medical prefix/suffix list as jargon
            med_prefixes = (
                'hyper', 'hypo', 'cardio', 'neuro', 'hepat', 'nephro',
                'onco', 'hemo', 'leuko', 'erythro', 'osteo', 'arthro',
                'dermato', 'gastro', 'pulmon', 'cerebro', 'vascu',
            )
            med_suffixes = (
                'ectomy', 'oscopy', 'otomy', 'plasty', 'ology', 'itis',
                'osis', 'emia', 'pathy', 'algia', 'uria', 'iasis',
                'genesis', 'lysis', 'megaly', 'phobia', 'tomy',
            )
            for w in all_long:
                if any(w.startswith(p) for p in med_prefixes) or \
                   any(w.endswith(s) for s in med_suffixes):
                    medical_jargon.append(w)
                else:
                    complex_terms.append(w)

        # Readability-based filtering with textstat
        if _TEXTSTAT_AVAILABLE and _textstat is not None:
            # Keep only words that are difficult for the average reader
            filtered_complex: list[str] = []
            for w in complex_terms:
                if len(w) > 10:
                    filtered_complex.append(w)
            complex_terms = filtered_complex

        return {
            "medical_jargon": medical_jargon[:150],  # cap lists
            "complex_terms":  complex_terms[:150],
        }

    # ── Step A: Language simplification ──────────────────────────────────────

    def simplify_language(self, text: str, medical_jargon: list[str],
                          complex_terms: list[str]) -> str:
        """
        LLM call A — rewrite document to 6th-grade reading level.
        Preserves medical_jargon terms exactly; simplifies complex_terms.
        """
        jargon_str = ', '.join(medical_jargon[:60]) or 'none'
        complex_str = ', '.join(complex_terms[:60]) or 'none'

        prompt = f"""You are a health literacy expert. Rewrite the following medical document so a patient with a 6th-grade reading level can understand it.

RULES:
1. Use short sentences (under 20 words each where possible).
2. Use active voice. Address the patient as "you".
3. Preserve these medical terms EXACTLY as written (do not change or define them here): {jargon_str}
4. Replace complex words where possible. Suggested replacements: {complex_str}
5. Use these AHRQ-recommended substitutions where applicable:
{_AHRQ_SUBSTITUTIONS}
6. Do NOT add information that is not in the original text.
7. Keep all numbers, dates, and dosages accurate.
8. Output ONLY the rewritten text — no preamble, no headings, no commentary.
9. Do NOT include the patient's name, date of birth, age, address, insurance details, or any
   other personal identifiers in the output. Refer to the patient only as "you" / "your".

ORIGINAL DOCUMENT:
{text}

REWRITTEN DOCUMENT:"""

        simplified = self._generate_text(prompt, temperature=0.3, max_tokens=16384)

        # Quality gate: if textstat available, re-prompt once if grade > 7
        if _TEXTSTAT_AVAILABLE and _textstat is not None:
            grade = _textstat.flesch_kincaid_grade(simplified)
            if grade > 7:
                logger.info("Readability grade %.1f > 7 — running stricter simplification pass", grade)
                stricter_prompt = f"""The following text has a reading level that is still too complex for a patient.
Rewrite it again using even simpler words and shorter sentences. Target a 5th-grade level.
Keep all medical terms ({jargon_str}) unchanged. Output ONLY the rewritten text.

TEXT:
{simplified}

SIMPLER VERSION:"""
                simplified = self._generate_text(stricter_prompt, temperature=0.2, max_tokens=16384)

        return simplified

    # ── Step B: Add definitions ───────────────────────────────────────────────

    def add_definitions(self, text: str, medical_jargon: list[str]) -> str:
        """
        LLM call B — inject a short parenthetical definition after the
        first occurrence of each genuinely opaque medical term.
        """
        if not medical_jargon:
            return text

        jargon_str = ', '.join(medical_jargon[:60])

        prompt = f"""You are a patient education specialist. In the text below, add a short parenthetical definition (3–5 words) after the FIRST occurrence of each medical term that a patient would not know.

TERMS TO CONSIDER: {jargon_str}

RULES:
1. Only define terms that are genuinely opaque to the average patient.
2. Skip common terms the patient already knows: "blood pressure", "MRI", "X-ray", "heart rate", "diabetes", "cancer", "infection", "fever", "pain".
3. Format: TERM (plain definition) — example: "myelin (protective nerve coating)"
4. Define each term ONLY on its first occurrence — do not repeat definitions.
5. Do NOT change any other part of the text.
6. Output ONLY the modified text — no commentary.

TEXT:
{text}

TEXT WITH DEFINITIONS:"""

        return self._generate_text(prompt, temperature=0.1, max_tokens=16384)

    # ── Step C: Clarify numbers and actions ──────────────────────────────────

    def clarify_and_action(self, text: str) -> str:
        """
        LLM call C — convert remaining medical shorthand, clarify vague
        quantities where context supports it, and emphasise patient actions.
        Runs a deterministic regex pre-pass first.
        """
        pre_processed = _apply_abbreviation_regex(text)

        prompt = f"""You are a health literacy expert helping patients understand what they need to do.

Review the text below and:
1. Convert any remaining medical abbreviations to plain English.
2. Where context makes it clear, replace vague quantities ("a few", "some", "several") with specifics. Never fabricate — only clarify when the context explicitly supports a specific number.
3. Make sure every instruction to the patient is in active voice and starts with a clear action verb ("Take", "Call", "Schedule", "Avoid", "Ask").
4. Do NOT add, remove, or fabricate any medical information.
5. Output ONLY the improved text — no commentary, no headings.

TEXT:
{pre_processed}

IMPROVED TEXT:"""

        return self._generate_text(prompt, temperature=0.2, max_tokens=16384)

    # ── Step 0 (new): Document classification ────────────────────────────────

    def classify_document(self, text: str) -> dict:
        """
        Classify the document as 'lab_result' or 'appointment_note'.

        Returns:
            { "doc_type": "lab_result"|"appointment_note", "confidence": "high"|"low" }
        Default on uncertainty: "appointment_note"
        """
        prompt = f"""Classify the following medical document into one of two categories:
- "lab_result": document primarily contains test values, lab measurements, reference ranges, or diagnostic test results
- "appointment_note": document primarily describes a clinical visit, doctor's notes, diagnoses, prescriptions, or patient-provider interactions

Return a JSON object with exactly these keys:
{{
  "doc_type": "lab_result" or "appointment_note",
  "confidence": "high" or "low"
}}

Rules:
- If the document contains mostly numerical lab values with reference ranges, choose "lab_result"
- If the document is primarily a narrative of a medical visit or clinical notes, choose "appointment_note"
- If uncertain, default to "appointment_note"
- Output ONLY valid JSON — no markdown, no commentary

DOCUMENT (first 2000 characters):
{text[:2000]}

JSON OUTPUT:"""

        try:
            raw = self._generate_json(prompt, temperature=0.1, max_tokens=256)
            if isinstance(raw, dict) and raw.get("doc_type") in ("lab_result", "appointment_note"):
                return raw
        except Exception:
            logger.warning("classify_document failed — defaulting to appointment_note")

        return {"doc_type": "appointment_note", "confidence": "low"}

    # ── Step D: Structure document ────────────────────────────────────────────

    def structure_document(self, text: str, medical_jargon: list[str],
                           doc_type: str = "appointment_note") -> dict:
        """
        LLM call D — produce structured JSON output based on document type.
        Delegates to _structure_lab_result or _structure_appointment_note.
        """
        if doc_type == "lab_result":
            return self._structure_lab_result(text, medical_jargon)
        return self._structure_appointment_note(text, medical_jargon)

    def _structure_lab_result(self, text: str, medical_jargon: list[str]) -> dict:
        """Layered Clarity Model — lab result structuring prompt."""
        jargon_str = ', '.join(medical_jargon[:60]) or 'none'

        prompt = f"""You are a medical document analyst. Read the simplified lab result text below and extract structured information following the Layered Clarity Model.

MEDICAL TERMS (for reference): {jargon_str}

TEXT:
{text}

OUTPUT INSTRUCTIONS:
Return a single JSON object with EXACTLY these keys:

{{
  "doc_type": "lab_result",
  "urgency": "normal|caution|concern|urgent",
  "summary": "2-3 plain-language sentences covering the overall result",
  "critical_flags": ["string — anything needing immediate or same-day action"],
  "abnormal_results": [
    {{
      "name": "string — test name",
      "value": "string — measured value",
      "unit": "string — unit of measurement",
      "normal_range": "string — reference range (empty string if not available)",
      "status": "caution|concern|critical",
      "plain_meaning": "plain language explanation of what this value means for the patient",
      "why": "deeper context about why this result matters, shown only on demand"
    }}
  ],
  "normal_results": [
    {{ "name": "string", "value": "string", "unit": "string" }}
  ],
  "action_items": [{{"text": "string — action starting with a verb (Take/Call/Schedule/Avoid)", "urgency": "immediate|soon|routine"}}],
  "what_this_means": "overall plain-language summary paragraph",
  "follow_ups": ["string"],
  "questions": ["string — question the patient should ask their doctor"]
}}

RULES:
1. urgency at document level = highest urgency of any individual result; use "normal" if all results are in range
2. critical_flags: ONLY values requiring same-day or emergency action; leave empty array if none
3. abnormal_results: ONLY include values that are outside the normal range
4. normal_results: values that are within normal range (name, value, unit only — no definitions needed)
5. Sort action_items by urgency: immediate first, then soon, then routine. Max 10 items.
6. summary: 2-3 plain sentences covering the overall result — e.g. "Most of your results are in the normal range. Two values need attention. Your doctor will review these with you."
7. questions: generate 3-5 questions grounded in what the text says
8. Output ONLY valid JSON — no markdown, no commentary

JSON OUTPUT:"""

        raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object from lab structure step, got: {type(raw)}")

        defaults: dict = {
            "doc_type":        "lab_result",
            "urgency":         "normal",
            "summary":         "",
            "critical_flags":  [],
            "abnormal_results": [],
            "normal_results":  [],
            "action_items":    [],
            "what_this_means": "",
            "follow_ups":      [],
            "questions":       [],
        }
        for k, v in defaults.items():
            if k not in raw:
                raw[k] = v
        raw["doc_type"] = "lab_result"
        return raw

    def _structure_appointment_note(self, text: str, medical_jargon: list[str]) -> dict:
        """Narrative Action Model — appointment note structuring prompt."""
        jargon_str = ', '.join(medical_jargon[:60]) or 'none'

        prompt = f"""You are a medical document analyst. Read the simplified appointment note below and extract structured information following the Narrative Action Model (What Happened → What It Means → What To Do).

MEDICAL TERMS (for reference): {jargon_str}

TEXT:
{text}

OUTPUT INSTRUCTIONS:
Return a single JSON object with EXACTLY these keys:

{{
  "doc_type": "appointment_note",
  "urgency": "normal|caution|concern|urgent",
  "summary": "2-3 plain-language sentences covering what happened, the key finding, and the main next step",
  "what_happened": {{
    "summary": "1-2 sentence visit summary",
    "date": "string or null if not mentioned",
    "reason": "why the patient came to this appointment"
  }},
  "what_it_means": {{
    "headline": "key finding or diagnosis in one plain-language sentence",
    "findings": [
      {{
        "item": "string — finding, diagnosis, or observation",
        "urgency": "immediate|soon|routine|informational"
      }}
    ]
  }},
  "what_to_do": [
    {{
      "text": "action starting with a verb (Take / Call / Schedule / Avoid / Ask)",
      "urgency": "immediate|soon|routine",
      "category": "medication|appointment|lifestyle|monitoring",
      "why": "one sentence on why this action matters (empty string if not applicable)"
    }}
  ],
  "low_priority": ["string — items noted as normal, unremarkable, or informational"],
  "follow_ups": ["string"],
  "questions": ["string — question the patient should ask their doctor"]
}}

RULES:
1. Everything the doctor said goes somewhere — nothing is silently dropped
2. Items noted as "normal" or "unremarkable" go in low_priority (not in findings)
3. Sort what_to_do by urgency: immediate first, then soon, then routine. Max 10 items.
4. urgency at document level = highest urgency of any finding or action
5. Each what_to_do item has exactly one category; why is optional (use empty string if not applicable)
6. questions: generate 3-5 questions grounded in what the text says
7. what_happened.date: extract the visit date if mentioned, otherwise null
8. summary: 2-3 plain sentences covering what happened, the key finding, and the main next step
9. Output ONLY valid JSON — no markdown, no commentary

JSON OUTPUT:"""

        raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object from appointment structure step, got: {type(raw)}")

        defaults: dict = {
            "doc_type":       "appointment_note",
            "urgency":        "normal",
            "summary":        "",
            "what_happened":  {"summary": "", "date": None, "reason": ""},
            "what_it_means":  {"headline": "", "findings": []},
            "what_to_do":     [],
            "low_priority":   [],
            "follow_ups":     [],
            "questions":      [],
        }
        for k, v in defaults.items():
            if k not in raw:
                raw[k] = v
        raw["doc_type"] = "appointment_note"
        return raw

    def run(self, text: str) -> dict:
        """Run the full V1 pipeline and return the structured result."""
        before_score = score_text(text)

        jargon_result = self.detect_jargon(text)
        medical_jargon = jargon_result["medical_jargon"]
        complex_terms = jargon_result["complex_terms"]

        classification = self.classify_document(text)
        doc_type = classification.get("doc_type", "appointment_note")

        simplified = self.simplify_language(text, medical_jargon, complex_terms)
        with_definitions = self.add_definitions(simplified, medical_jargon)
        clarified = self.clarify_and_action(with_definitions)

        after_score = score_text(clarified)
        structured = self.structure_document(clarified, medical_jargon, doc_type)

        result = {**structured}
        if before_score is not None:
            result["before_score"] = before_score
        if after_score is not None:
            result["after_score"] = after_score
        return result
