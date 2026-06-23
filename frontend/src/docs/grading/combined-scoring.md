# Combined Score (Patient Accessibility Score)

The **Combined Score** is Juno's primary readability metric — a composite Patient Accessibility Score (0–100) that aggregates seven evidence-based dimensions of health-literacy difficulty into a single actionable number.

Unlike any individual readability formula, the combined score accounts for vocabulary complexity, sentence structure, passive voice, actionability, numeracy, and document layout simultaneously. This multi-dimensional approach reflects how real patients experience a document: a text that scores well on grade level alone can still be confusing if it is passive, jargon-heavy, or poorly structured.

## How it works

Seven sub-dimension scores (each 0–100, higher = more accessible) are computed independently, then combined as a weighted sum:

| Dimension | Weight | What it measures |
|---|---|---|
| Grade Level | 25% | Reading grade level consensus from SMOG, Flesch-Kincaid, and Dale-Chall |
| Jargon Density | 20% | Proportion of words not on the Dale-Chall familiar-word list |
| Sentence Complexity | 15% | Average words per sentence |
| Passive Voice | 10% | Ratio of passive constructions to total sentences |
| Actionability | 10% | Rate of second-person ("you") instruction language |
| Numeracy Clarity | 10% | Count of vague numeric expressions (e.g., "a few", "several") |
| Structural Clarity | 10% | Average words per paragraph; bonus for bullet/numbered lists |

**Formula:**

```
composite = round(
    grade_level_score         × 0.25
  + jargon_density_score      × 0.20
  + sentence_complexity_score × 0.15
  + passive_voice_score       × 0.10
  + actionability_score       × 0.10
  + numeracy_clarity_score    × 0.10
  + structural_clarity_score  × 0.10
)
```

The result is an integer in the range 0–100.

## Score labels

| Range | Label | Meaning |
|---|---|---|
| 70–100 | **Patient-friendly** | Suitable for most patients at a 6th-grade reading level |
| 40–69 | **Moderate** | May be difficult for patients with limited health literacy |
| 0–39 | **Hard to read** | Likely to cause confusion; significant revision recommended |

## Grade estimate

In addition to the composite score, the combined result reports a `grade_estimate` — the consensus reading grade level drawn from SMOG, Flesch-Kincaid, and Dale-Chall. This is the same value used to compute the Grade Level dimension score, surfaced separately for clinical reference (e.g., "8th grade").

## Before vs after scores

When grading is run on a completed care plan, two composite scores are computed:

- **Before** — scored against the original input text (the raw clinical note or document)
- **After** — scored against Juno's clarified output (the plain-language care plan)

The delta between these two scores shows the accessibility improvement Juno achieved for that document.

## Low-confidence flag

The combined score sets `low_confidence = true` when the input text contains fewer than 30 words or fewer than 3 sentences. At that sample size, individual sub-dimension scores (especially grade level and sentence complexity) are statistically unreliable. The score is still computed and displayed, but should be interpreted with caution.

## How it differs from the individual method scores

The six individual grading methods (SMOG, Flesch-Kincaid, Dale-Chall, PEMAT, SAM, CDC CCI) each measure a narrow aspect of readability using a single validated instrument. They are most useful when you need to compare against published norms (e.g., "this document is at a 10th-grade SMOG level") or understand a specific dimension in isolation.

The combined score is designed for decision-making and tracking:
- It captures dimensions that no single formula covers (actionability, numeracy, structural clarity)
- The 25% weight on grade level reflects the research consensus that vocabulary and grade level are the strongest drivers of patient comprehension
- Jargon density receives 20% because medical terminology is the most common barrier cited in health literacy research, even in texts that score well on traditional grade-level formulas

## Research basis

Each dimension is grounded in peer-reviewed health literacy research:

- **Grade Level** — SMOG (McLaughlin 1969, designed for health materials), Flesch-Kincaid (1975), Dale-Chall (1948/1995)
- **Jargon Density** — Dale-Chall familiar word list; PEMAT item 3 (AHRQ 2013)
- **Sentence Complexity** — PEMAT item 8; AHRQ Health Literacy Universal Precautions Toolkit (3rd ed.)
- **Passive Voice** — PEMAT item 14; AHRQ active-voice guideline
- **Actionability** — PEMAT actionability subscale items 27–33 (AHRQ 2013); CDC Clear Communication Index
- **Numeracy Clarity** — PEMAT items 21–22; POC spec Step 3 (specificity and numeracy)
- **Structural Clarity** — SAM (Doak et al. 1996) layout/typography domain; PEMAT items 9–12

## External references

- [McLaughlin, G. H. (1969). SMOG Grading. *Journal of Reading*, 12(8), 639–646.](https://doi.org/10.1598/jor.1969.12.8.1)
- [Kincaid, J. P. et al. (1975). Derivation of New Readability Formulas. Naval Technical Training Command.](https://stars.library.ucf.edu/cgi/viewcontent.cgi?article=1055&context=istlibrary)
- [Dale, E. & Chall, J. S. (1948). A formula for predicting readability. *Educational Research Bulletin*, 27, 11–28.]
- [Shoemaker, S. J. et al. (2014). The Patient Education Materials Assessment Tool (PEMAT). *Patient Education and Counseling*, 96(3), 395–403.](https://doi.org/10.1016/j.pec.2014.05.027)
- [Doak, C. C., Doak, L. G., & Root, J. H. (1996). *Teaching Patients with Low Literacy Skills* (2nd ed.). J. B. Lippincott.]
- [CDC. (2021). *CDC Clear Communication Index User Guide*.](https://www.cdc.gov/ccindex/)
