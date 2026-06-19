from pathlib import Path


PRESET_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "preset-data"


def _input_files(group: str, input_id: str) -> list[str]:
    input_dir = PRESET_DATA_ROOT / group / input_id
    if not input_dir.is_dir():
        return []
    return sorted(p.name for p in input_dir.iterdir() if p.is_file())


def list_datasets() -> list[dict]:
    if not PRESET_DATA_ROOT.is_dir():
        return []

    datasets = []
    for group_dir in sorted(p for p in PRESET_DATA_ROOT.iterdir() if p.is_dir()):
        inputs = sorted(p.name for p in group_dir.iterdir() if p.is_dir())
        files = _input_files(group_dir.name, inputs[0]) if inputs else []
        datasets.append({"group": group_dir.name, "inputs": inputs, "files": files})
    return datasets


def read_dataset_file(group: str, input_id: str, filename: str) -> bytes:
    match = next((d for d in list_datasets() if d["group"] == group), None)
    if match is None or input_id not in match["inputs"]:
        raise FileNotFoundError()

    if filename not in _input_files(group, input_id):
        raise FileNotFoundError()

    root = PRESET_DATA_ROOT.resolve()
    path = (PRESET_DATA_ROOT / group / input_id / filename).resolve()
    if not path.is_relative_to(root):
        raise FileNotFoundError()

    return path.read_bytes()
