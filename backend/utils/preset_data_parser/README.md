# Preset Data Parsers

Each dataset parser lives in its own subfolder:
`backend/utils/preset_data_parser/{dataset_name}/parser.py`

Each parser is a self-contained CLI script. It reads from a downloaded source directory
and writes files into the `preset-data/` tree expected by the runtime. Run it once after
downloading the dataset; it does not need to be re-run unless `preset-data/` is wiped.

## Available parsers

- `primock57/` — 57 GP consultation notes from the primock57 dataset
  Download: https://github.com/Sydney-Informatics-Hub/primock57

## Running a parser

From the repo root:

    python -m backend.utils.preset_data_parser.primock57.parser --source /path/to/primock57

From inside the parser's own directory:

    python parser.py --source /path/to/primock57

## Adding a new parser

1. Create `backend/utils/preset_data_parser/{dataset_name}/`.
2. Add an empty `__init__.py`.
3. Add `parser.py` — a self-contained CLI script following the same CLI interface pattern as `primock57/parser.py`.
4. Add an entry to the "Available parsers" list above.
