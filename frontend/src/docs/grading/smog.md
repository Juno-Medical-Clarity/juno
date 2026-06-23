# SMOG

**SMOG** (Simple Measure of Gobbledygook) was developed by G. Harry McLaughlin in 1969 specifically for health education materials. It is widely used by the CDC and health literacy researchers as a standard measure for patient-facing documents.

## How it works

SMOG counts the number of polysyllabic words (words with 3 or more syllables) in a sample of 30 sentences and applies a formula to estimate the reading grade level. The assumption is that polysyllabic words are the primary driver of reading difficulty.

SMOG requires at least 30 sentences to produce a valid result. Texts with fewer than 30 sentences return a score of 0 and are flagged as insufficient sample.

## Score breakdown

- **`grade`**: Estimated US reading grade level (e.g., 8.0 = 8th grade)
- **`insufficient_sample`**: `true` if the text has fewer than 30 sentences

The normalized score (0–100) is derived from the grade level: lower grade = higher score.

## External reference

[McLaughlin, G. H. (1969). SMOG Grading — a New Readability Formula. *Journal of Reading*, 12(8), 639–646.](https://doi.org/10.1598/jor.1969.12.8.1)
