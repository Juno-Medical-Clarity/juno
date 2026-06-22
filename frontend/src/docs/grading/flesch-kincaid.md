# Flesch-Kincaid

The **Flesch-Kincaid** formulas were developed by Rudolf Flesch (1948) and later adapted by J. Peter Kincaid for the U.S. Navy (1975). They are among the most widely used readability measures in English and are built into Microsoft Word.

## How it works

Two related formulas are computed:

- **Reading Ease** (Flesch): a 0–100 score where higher is easier. Scores above 60 are considered plain language; scores below 30 are very difficult.
- **Grade Level** (Flesch-Kincaid): the estimated US school grade level required to understand the text.

Both formulas weight average sentence length and average syllable count per word.

## Score breakdown

- **`reading_ease`**: Flesch Reading Ease score (0–100; higher = easier)
- **`grade_level`**: Flesch-Kincaid Grade Level

The normalized score (0–100) used for comparison is the Reading Ease score clamped to [0, 100].

## External reference

[Kincaid, J. P., et al. (1975). Derivation of New Readability Formulas for Navy Enlisted Personnel. *Naval Technical Training Command Research Branch*.](https://apps.dtic.mil/sti/citations/ADA006655)
