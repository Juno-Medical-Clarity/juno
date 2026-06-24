# Juno Datasets

Juno is a medical AI platform for processing, summarizing, and structuring clinical text. To power and evaluate its capabilities, Juno integrates a curated collection of publicly available medical datasets spanning doctor-patient conversations, clinical Q&A, and medical text simplification.

This document covers every dataset currently integrated into the preset-data pipeline, how it was parsed, and how to reproduce the parsing step. Datasets requiring PhysioNet credentialing are listed separately at the end.

---

## Summary Table

| # | Dataset | Group | Samples | Source |
|---|---------|-------|---------|--------|
| 1 | PriMock57 Conversations | Doctor-Patient | 57 | [GitHub](https://github.com/babylonhealth/primock57) |
| 2 | PriMock57 Notes | Doctor-Patient | 57 | [GitHub](https://github.com/babylonhealth/primock57) |
| 3 | MTS-Dialog | Doctor-Patient | 1,301 | [GitHub](https://github.com/abachaa/MTS-Dialog) |
| 4 | SubashNeupane SOAP Summary | Doctor-Patient | 1,473 | [HuggingFace](https://huggingface.co/datasets/SubashNeupane/dataset_SOAP_summary) |
| 5 | MedDialog | Doctor-Patient | 20 (loaded) / 200K+ (full) | [HuggingFace](https://huggingface.co/datasets/lighteval/med_dialog) |
| 6 | Smith Collection | Doctor-Patient | 272 | [HuggingFace](https://huggingface.co/datasets/yfyeung/medical) |
| 7 | NoteChat | Doctor-Patient | 50 (loaded) / 207K (full) | [HuggingFace](https://huggingface.co/datasets/akemiH/NoteChat) |
| 8 | MeQSum | Clinical Q&A | 1,000 | [GitHub](https://github.com/abachaa/MeQSum) |
| 9 | LiveQA Medical (TREC 2017) | Clinical Q&A | 104 | [GitHub](https://github.com/abachaa/LiveQA_MedicalTask_TREC2017) |
| 10 | MedicationQA | Clinical Q&A | 690 | [GitHub](https://github.com/abachaa/Medication_QA_MedInfo2019) |
| 11 | Med-EASi | Text Simplification | 1,893 | [HuggingFace](https://huggingface.co/datasets/cbasu/Med-EASi) |
| 12 | MedReadMe | Text Simplification | 4,504 | [GitHub](https://github.com/chaojiang06/medreadme) |
| 13 | GEM/Cochrane Simplification | Text Simplification | 4,459 | [HuggingFace](https://huggingface.co/datasets/GEM/cochrane-simplification) |
| 14 | NoteAid-README | Text Simplification | 500 | [HuggingFace](https://huggingface.co/datasets/bio-nlp-umass/NoteAid-README) |
| 15 | PLABA | Text Simplification | 919 (9,319 sentence pairs) | [OSF](https://osf.io/rnpmf/) / [GitHub](https://github.com/attal-kush/PLABA) |

---

## Group 1: Doctor-Patient Conversations

These datasets contain transcripts or synthetic dialogues between patients and physicians. They are used to evaluate and demonstrate Juno's ability to extract structured information from conversational clinical text.

---

### 1. PriMock57 Conversations

**Source:** [https://github.com/babylonhealth/primock57](https://github.com/babylonhealth/primock57)
**Output directory:** `preset-data/primock57-conversations/`
**Sample count:** 57 consultations

**Description:**
PriMock57 is a dataset of 57 mock primary care consultations recorded by Babylon Health. This variant contains the full consultation transcripts, parsed from TextGrid format and merged into a single dialogue stream using `Doctor:` and `Patient:` prefixes. It is ideal for evaluating how well Juno can parse naturalistic, turn-by-turn clinical conversations.

**Files per sample:**
- `conversation.txt` — merged Doctor/Patient transcript

**Parsing script:**
```bash
python scripts/primock57/parse_primock57_conversations.py
```

---

### 2. PriMock57 Notes

**Source:** [https://github.com/babylonhealth/primock57](https://github.com/babylonhealth/primock57)
**Output directory:** `preset-data/primock57/`
**Sample count:** 57 consultation notes

**Description:**
The companion to PriMock57 Conversations. This variant contains the physician-authored clinical notes written after each of the 57 mock consultations. The notes represent the ground-truth documentation output that a clinician would produce, making this dataset useful for evaluating Juno's summarization and note-generation capabilities.

**Files per sample:**
- Clinical note text file

---

### 3. MTS-Dialog

**Source:** [https://github.com/abachaa/MTS-Dialog](https://github.com/abachaa/MTS-Dialog)
**Output directory:** `preset-data/mts-dialog/`
**Sample count:** 1,301 (1,201 train + 100 validation)

**Description:**
MTS-Dialog is a dataset of short doctor-patient dialogues paired with structured clinical section summaries. Each sample pairs a conversational exchange with a corresponding clinical summary, making it well-suited for training and evaluating medical dialogue summarization. The dataset covers a variety of clinical specialties and conversation styles.

**Files per sample:**
- `conversation.txt` — doctor-patient dialogue
- `summary.txt` — structured clinical section summary

**Parsing script:**
```bash
python scripts/mts-dialog/parse_mts_dialog.py
```

---

### 4. SubashNeupane SOAP Summary

**Source:** [https://huggingface.co/datasets/SubashNeupane/dataset_SOAP_summary](https://huggingface.co/datasets/SubashNeupane/dataset_SOAP_summary)
**Output directory:** `preset-data/soap-summary/`
**Sample count:** 1,473

**Description:**
A dataset of patient-doctor conversations paired with SOAP-format clinical note summaries (Subjective, Objective, Assessment, Plan). SOAP notes are a standard structured documentation format in clinical practice. This dataset is particularly relevant to Juno's goal of converting unstructured conversation into structured clinical documentation.

**Files per sample:**
- `conversation.txt` — patient-doctor dialogue
- `soap_notes.txt` — SOAP-format clinical summary

**Parsing script:**
```bash
python scripts/soap-summary/parse_soap_summary.py
```

---

### 5. MedDialog

**Source:** [https://huggingface.co/datasets/lighteval/med_dialog](https://huggingface.co/datasets/lighteval/med_dialog) (mirror of UCSD-AI4H Medical Dialogue Dataset)
**Output directory:** `preset-data/meddialog/`
**Sample count:** 20 (loaded) — full dataset contains 200K+ samples

**Description:**
MedDialog is a large-scale medical dialogue dataset originally developed by UCSD AI4H, aggregating patient-doctor online conversations from HealthCareMagic and iCliniq platforms. The Juno integration loads a representative 20-sample subset for demonstration purposes. The full dataset is available for extended evaluation runs.

**Files per sample:**
- `conversation.txt` — patient-doctor online dialogue

**Parsing script:**
```bash
python scripts/meddialog/parse_meddialog.py
```

---

### 6. Smith Collection

**Source:** [https://huggingface.co/datasets/yfyeung/medical](https://huggingface.co/datasets/yfyeung/medical) (original DOI via Figshare)
**Output directory:** `preset-data/smith-collection/`
**Sample count:** 272 simulated consultations

**Description:**
The Smith Collection is a set of 272 simulated patient-physician interviews in an OSCE (Objective Structured Clinical Examination) format, with a focus on respiratory cases. The consultations were scripted and acted to simulate realistic clinical encounters. This dataset is useful for evaluating Juno on structured, high-quality simulated dialogue with consistent clinical structure.

**Files per sample:**
- `conversation.txt` — simulated patient-physician interview

**Parsing script:**
```bash
python scripts/smith-collection/parse_smith_collection.py
```

---

### 7. NoteChat

**Source:** [https://huggingface.co/datasets/akemiH/NoteChat](https://huggingface.co/datasets/akemiH/NoteChat)
**Output directory:** `preset-data/notechat/`
**Sample count:** 50 (loaded) — full dataset contains 207K samples

**Description:**
NoteChat is a large synthetic dataset of patient-physician dialogues paired with corresponding clinical notes derived from PMC-Patients. Each sample includes both the conversation and the source clinical note, allowing bidirectional evaluation: conversation-to-note and note-to-conversation. The Juno integration loads a 50-sample subset for demonstration; the full dataset can be loaded for larger evaluation runs.

**Files per sample:**
- `clinical_note.txt` — source clinical note (from PMC-Patients)
- `conversation.txt` — synthetic patient-physician dialogue

**Parsing script:**
```bash
python scripts/notechat/parse_notechat.py
```

---

## Group 2: Clinical Q&A

These datasets contain consumer health questions with expert-authored answers or summaries. They are used to evaluate Juno's ability to understand and respond to patient-authored health queries.

---

### 8. MeQSum

**Source:** [https://github.com/abachaa/MeQSum](https://github.com/abachaa/MeQSum)
**Output directory:** `preset-data/meqsum/`
**Sample count:** 1,000

**Description:**
MeQSum is a dataset of consumer health questions submitted to the National Library of Medicine (NLM), paired with expert-authored condensed summaries. The questions are often verbose and multi-part; the summaries distill them into focused, answerable queries. This dataset helps evaluate Juno's ability to understand and restate complex patient questions.

**Files per sample:**
- `question.txt` — original consumer health question
- `summary.txt` — condensed expert summary of the question

**Parsing script:**
```bash
python scripts/meqsum/parse_meqsum.py
```

---

### 9. LiveQA Medical (TREC 2017)

**Source:** [https://github.com/abachaa/LiveQA_MedicalTask_TREC2017](https://github.com/abachaa/LiveQA_MedicalTask_TREC2017)
**Output directory:** `preset-data/liveqa-medical/`
**Sample count:** 104

**Description:**
The TREC 2017 LiveQA Medical Task dataset is a benchmark of consumer health questions from NLM with expert reference answers. Originally used in the TREC 2017 live question answering competition, each sample comes with detailed metadata including question type and focus. This dataset tests Juno's ability to generate accurate, expert-level responses to health questions.

**Files per sample:**
- `question.txt` — consumer health question
- `answer.txt` — expert reference answer
- `metadata.txt` — question type, focus, and source metadata

**Parsing script:**
```bash
python scripts/liveqa-medical/parse_liveqa_medical.py
```

---

### 10. MedicationQA

**Source:** [https://github.com/abachaa/Medication_QA_MedInfo2019](https://github.com/abachaa/Medication_QA_MedInfo2019)
**Output directory:** `preset-data/medicationqa/`
**Sample count:** 690

**Description:**
MedicationQA is a dataset of consumer medication questions with expert answers, originally presented at MedInfo 2019. Questions were collected from real users seeking information about specific drugs, including dosage, side effects, interactions, and usage. This dataset is particularly relevant for evaluating Juno on medication-related Q&A tasks.

**Files per sample:**
- `question.txt` — consumer medication question
- `answer.txt` — expert answer
- `metadata.txt` — drug name, question focus, and source

**Parsing script:**
```bash
python scripts/medicationqa/parse_medicationqa.py
```

---

## Group 3: Text Simplification & Readability

These datasets focus on making medical language accessible to non-expert readers. They are used to evaluate Juno's ability to simplify clinical jargon, explain terminology, and rewrite complex medical text in plain language.

---

### 11. Med-EASi

**Source:** [https://huggingface.co/datasets/cbasu/Med-EASi](https://huggingface.co/datasets/cbasu/Med-EASi)
**Output directory:** `preset-data/med-easi/`
**Sample count:** 1,893

**Description:**
Med-EASi is a dataset of expert-to-simple medical text pairs with fine-grained simplification annotations. Each sample includes an original medical text passage and a simplified version, along with annotations identifying specific simplification operations performed (e.g., jargon substitution, sentence splitting). This dataset is central to evaluating Juno's plain-language output quality.

**Files per sample:**
- `original.txt` — expert-level medical text
- `simplified.txt` — lay-audience simplified version

**Parsing script:**
```bash
python scripts/med-easi/parse_med_easi.py
```

---

### 12. MedReadMe

**Source:** [https://github.com/chaojiang06/medreadme](https://github.com/chaojiang06/medreadme)
**Output directory:** `preset-data/medreadme/`
**Sample count:** 4,504

**Description:**
MedReadMe is a dataset of medical sentences annotated with readability scores and span-level jargon annotations. Each sample identifies which words or phrases constitute medical jargon and provides a readability score for the full sentence. This dataset enables evaluation of Juno's ability to identify and explain difficult medical terminology at the sentence level.

**Files per sample:**
- `text.txt` — medical sentence
- `annotations.txt` — jargon spans and readability scores

**Parsing script:**
```bash
python scripts/medreadme/parse_medreadme.py
```

---

### 13. GEM/Cochrane Simplification

**Source:** [https://huggingface.co/datasets/GEM/cochrane-simplification](https://huggingface.co/datasets/GEM/cochrane-simplification)
**Output directory:** `preset-data/cochrane-simplification/`
**Sample count:** 4,459

**Description:**
This dataset pairs Cochrane systematic review abstracts — highly technical summaries of clinical evidence — with their corresponding plain-language summaries written for patients and the general public. Cochrane plain-language summaries are authored by trained medical writers, making this a high-quality gold standard for technical-to-lay simplification. It is one of the largest and most reliable simplification datasets in the Juno pipeline.

**Files per sample:**
- `technical.txt` — Cochrane systematic review abstract
- `patient_summary.txt` — Cochrane plain-language summary

**Parsing script:**
```bash
python scripts/cochrane-simplification/parse_cochrane.py
```

---

### 14. NoteAid-README

**Source:** [https://huggingface.co/datasets/bio-nlp-umass/NoteAid-README](https://huggingface.co/datasets/bio-nlp-umass/NoteAid-README)
**Output directory:** `preset-data/noteaid-readme/`
**Sample count:** 500

**Description:**
NoteAid-README is a dataset of medical jargon terms paired with lay-language definitions and EHR context passages in which those terms appear. Unlike sentence-level simplification datasets, NoteAid-README focuses on term-level understanding — providing grounded definitions anchored to real clinical note context. This dataset supports evaluation of Juno's medical terminology explanation capabilities.

**Files per sample:**
- `jargon.txt` — medical term or phrase
- `definition.txt` — lay-language definition
- `context.txt` — EHR passage containing the jargon term

**Parsing script:**
```bash
python scripts/noteaid-readme/parse_noteaid.py
```

---

### 15. PLABA

**Source:** [https://osf.io/rnpmf/](https://osf.io/rnpmf/) / [https://github.com/attal-kush/PLABA](https://github.com/attal-kush/PLABA)
**Output directory:** `preset-data/plaba/`
**Sample count:** 919 abstracts (9,319 sentence pairs)

**Description:**
PLABA (Plain Language Adaptation of Biomedical Abstracts) is a sentence-level simplification dataset pairing PubMed biomedical abstracts with plain-language adaptations. Each abstract is broken into individual sentences, and each sentence is paired with a simplified rewrite authored by trained annotators. With over 9,000 sentence pairs across 919 abstracts, PLABA is one of the most granular simplification benchmarks in the Juno pipeline.

**Files per sample:**
- `original.txt` — PubMed abstract sentence(s)
- `simplified.txt` — plain-language adaptation
- `metadata.txt` — PubMed ID and abstract-level metadata

**Parsing script:**
```bash
python scripts/plaba/parse_plaba.py
```

---

## Future / Restricted Datasets (PhysioNet)

The following datasets are planned for integration but require PhysioNet credentialing. Access requires creating a PhysioNet account and completing a data use agreement at [https://physionet.org](https://physionet.org).

| Dataset | Description |
|---------|-------------|
| **MIMIC-IV-Note** | De-identified clinical notes from Beth Israel Deaconess Medical Center (BIDMC). Largest freely available real EHR note corpus. |
| **MIMIC-IV-Ext-BHC** | MIMIC-IV extension with Brief Hospital Course (BHC) sections extracted and annotated. |
| **EHRNoteQA** | Q&A pairs derived from MIMIC-IV clinical notes for EHR reading comprehension evaluation. |
| **MEDISumQA** | Medical summarization Q&A benchmark built on MIMIC discharge summaries. |
| **DiSCQ** | Discharge Summary Clinical Questions dataset — patient and provider questions about hospital discharge summaries. |

Once credentialed, parsing scripts for these datasets will be added under `scripts/[dataset-name]/` following the same conventions as the datasets above.

---

## Adding a New Dataset

To integrate a new dataset into the Juno preset-data pipeline:

1. Create a parsing script at `scripts/[dataset-name]/parse_[dataset-name].py`
2. Output one sample per subdirectory under `preset-data/[dataset-name]/`
3. Use plain `.txt` files for each field (e.g., `conversation.txt`, `summary.txt`)
4. Run `npm run build` in `frontend/` or push to the `deploy` branch to update the preset list automatically

See `preset-data/README.md` for the full directory structure convention.
