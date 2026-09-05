# CDC Clear Communication Index

The **CDC Clear Communication Index** (CDC CCI) is a research-based tool developed by the Centers for Disease Control and Prevention to help public health professionals create clear, actionable health communication materials.

## How it works

Simplify computes an automated approximation of four CDC CCI items using internal dimension scores:

- **Main message present**: actionability score >= 50
- **Behavioral recommendation present**: average of actionability + numeracy clarity >= 50
- **Numbers used correctly**: numeracy clarity score >= 50
- **Call to action present**: actionability score >= 60

The score is the percentage of the four items met (0, 25, 50, 75, or 100).

## Score breakdown

- **`main_message`**: 1 if main message criterion met, else 0
- **`behavioral_recommendations`**: 1 if behavioral recommendation criterion met, else 0
- **`numbers`**: 1 if numeracy criterion met, else 0
- **`call_to_action`**: 1 if call-to-action criterion met, else 0

Note: Full CDC CCI has 20 scored items. Simplify approximates the 4 most automatable items from text alone.

## External reference

[CDC Clear Communication Index](https://www.cdc.gov/healthliteracy/develop/clear-communication-index.html)
