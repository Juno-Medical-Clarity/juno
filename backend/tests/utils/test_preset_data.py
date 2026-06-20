import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class PresetDataTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        docconv_input_1 = self.root / "DocConv" / "input-1"
        docconv_input_2 = self.root / "DocConv" / "input-2"
        other_input = self.root / "OtherGroup" / "case-a"

        docconv_input_1.mkdir(parents=True)
        docconv_input_2.mkdir(parents=True)
        other_input.mkdir(parents=True)

        (docconv_input_1 / "notes.txt").write_bytes(b"input 1 notes")
        (docconv_input_1 / "transcript.txt").write_bytes(b"input 1 transcript")
        (docconv_input_2 / "input-2-only.txt").write_bytes(b"input 2 only")
        (other_input / "summary.txt").write_bytes(b"summary")
        (self.root / "DocConv" / "not-an-input.txt").write_text("ignored")

        from utils import preset_data

        self.preset_data = preset_data
        self.original_root = preset_data.PRESET_DATA_ROOT
        preset_data.PRESET_DATA_ROOT = self.root

    def tearDown(self):
        self.preset_data.PRESET_DATA_ROOT = self.original_root
        self.temp_dir.cleanup()

    def test_list_datasets_returns_sorted_groups_inputs_and_representative_files(self):
        datasets = self.preset_data.list_datasets()

        self.assertEqual(
            datasets,
            [
                {
                    "group": "DocConv",
                    "inputs": ["input-1", "input-2"],
                    "files": ["notes.txt", "transcript.txt"],
                },
                {
                    "group": "OtherGroup",
                    "inputs": ["case-a"],
                    "files": ["summary.txt"],
                },
            ],
        )

    def test_read_dataset_file_reads_from_the_requested_input_folder(self):
        content = self.preset_data.read_dataset_file(
            "DocConv", "input-2", "input-2-only.txt"
        )

        self.assertEqual(content, b"input 2 only")

    def test_read_dataset_file_rejects_mismatches_and_traversal(self):
        bad_requests = [
            ("../DocConv", "input-1", "notes.txt"),
            ("DocConv", "../../../etc", "passwd"),
            ("DocConv", "input-1", "../../../../etc/passwd"),
            ("DocConv", "input-2", "notes.txt"),
            ("Missing", "input-1", "notes.txt"),
        ]

        for group, input_id, filename in bad_requests:
            with self.subTest(group=group, input_id=input_id, filename=filename):
                with self.assertRaises(FileNotFoundError):
                    self.preset_data.read_dataset_file(group, input_id, filename)


if __name__ == "__main__":
    unittest.main()
