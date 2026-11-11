"""Portable configuration tests using only temporary files and fake paths."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import main


class ConfigTests(unittest.TestCase):
    def test_legacy_defaults_are_project_relative(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = config.load_file_config(root, environment={})
            self.assertEqual(paths.input_pdf, root / "ALL.pdf")
            self.assertEqual(paths.contacts_csv, root / "contacts.csv")
            self.assertEqual(paths.output_dir, root / "Renamed_PDFs")

    def test_environment_supports_relative_directories_and_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = {
                "PDFSPLITTER_INPUT_DIR": "files/input",
                "PDFSPLITTER_INPUT_FILE": "allocations.pdf",
                "PDFSPLITTER_CONTACTS_DIR": "files/data",
                "PDFSPLITTER_CONTACTS_FILE": "staff.csv",
                "PDFSPLITTER_OUTPUT_DIR": "files/output",
            }
            paths = config.load_file_config(root, environment=values)
            self.assertEqual(paths.input_pdf, root / "files/input/allocations.pdf")
            self.assertEqual(paths.contacts_csv, root / "files/data/staff.csv")
            self.assertEqual(paths.output_dir, root / "files/output")

    def test_absolute_directories_are_not_rebased(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "different"
            paths = config.load_file_config(root / "project", environment={
                "PDFSPLITTER_INPUT_DIR": str(outside),
                "PDFSPLITTER_CONTACTS_DIR": str(outside),
                "PDFSPLITTER_OUTPUT_DIR": str(outside / "output"),
            })
            self.assertEqual(paths.input_pdf, outside / "ALL.pdf")
            self.assertEqual(paths.contacts_csv, outside / "contacts.csv")
            self.assertEqual(paths.output_dir, outside / "output")

    def test_dotenv_is_used_and_process_environment_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env").write_text(
                "PDFSPLITTER_INPUT_DIR=from_dotenv\n"
                "PDFSPLITTER_INPUT_FILE=source.pdf\n"
                "PDFSPLITTER_OUTPUT_DIR=generated\n", encoding="utf-8")
            paths = config.load_file_config(root, environment={
                "PDFSPLITTER_INPUT_DIR": "from_system",
            })
            self.assertEqual(paths.input_pdf, root / "from_system/source.pdf")
            self.assertEqual(paths.output_dir, root / "generated")
            self.assertEqual(paths.contacts_csv, root / "contacts.csv")

    def test_relative_config_does_not_depend_on_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "app"
            root.mkdir()
            elsewhere = Path(temp) / "elsewhere"
            elsewhere.mkdir()
            original_cwd = Path.cwd()
            try:
                os.chdir(elsewhere)
                # Project dir is explicit; even if cwd differs, paths are stable.
                paths = config.load_file_config(root, environment={"PDFSPLITTER_OUTPUT_DIR": "out"})
            finally:
                os.chdir(original_cwd)
            self.assertEqual(paths.output_dir, root / "out")

    def test_file_settings_reject_path_components(self):
        with tempfile.TemporaryDirectory() as temp:
            for value in ("../private.csv", r"folder\private.csv", ".."):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "must be a filename"):
                        config.load_file_config(Path(temp), environment={
                            "PDFSPLITTER_CONTACTS_FILE": value,
                        })

    def test_empty_environment_setting_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                config.load_file_config(Path(temp), environment={
                    "PDFSPLITTER_OUTPUT_DIR": "  ",
                })

    def test_cli_overrides_environment_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {
                "PDFSPLITTER_INPUT_DIR": "environment_input",
                "PDFSPLITTER_CONTACTS_DIR": "environment_contacts",
                "PDFSPLITTER_OUTPUT_DIR": "environment_output",
            }), mock.patch.object(main, "run", return_value=0) as run, \
                 mock.patch.object(sys, "argv", ["main.py", "--input", str(Path(temp) / "in.pdf"),
                                  "--contacts", str(Path(temp) / "addressbook.csv"),
                                  "--output", str(Path(temp) / "finished")]):
                self.assertEqual(main.main(), 0)
                args, kwargs = run.call_args
                self.assertEqual(args[:3], (Path(temp) / "in.pdf",
                                            Path(temp) / "addressbook.csv",
                                            Path(temp) / "finished"))
                self.assertEqual(args[3:], (False, False))
                self.assertEqual(kwargs, {})

    def test_main_uses_dotenv_config_from_other_working_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            root.mkdir()
            elsewhere = Path(temp) / "other"
            elsewhere.mkdir()
            (root / ".env").write_text(
                "PDFSPLITTER_INPUT_DIR=documents\n"
                "PDFSPLITTER_INPUT_FILE=allocated.pdf\n"
                "PDFSPLITTER_CONTACTS_DIR=records\n"
                "PDFSPLITTER_CONTACTS_FILE=people.csv\n"
                "PDFSPLITTER_OUTPUT_DIR=finished\n", encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                os.chdir(elsewhere)
                with mock.patch.object(config, "PROJECT_DIR", root), \
                     mock.patch.object(main, "run", return_value=0) as run, \
                     mock.patch.object(sys, "argv", ["main.py"]):
                    self.assertEqual(main.main(), 0)
                    self.assertEqual(run.call_args.args[:3],
                                     (root / "documents/allocated.pdf",
                                      root / "records/people.csv",
                                      root / "finished"))
            finally:
                os.chdir(original_cwd)

    def test_relative_cli_paths_are_cwd_based(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(config.resolve_cli_path(Path("my.pdf")), root / "my.pdf")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
