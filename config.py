"""Portable file-path configuration for PDFSplitter.

Read local .env values without modifying the process environment. Explicit
operating-system environment variables take precedence over .env values.
Relative configured directories are anchored to this project's location,
not the shell/PyCharm working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

try:
    from dotenv import dotenv_values
except ImportError:
    raise SystemExit("Missing configuration dependency. Run: python -m pip install -r requirements.txt")


PROJECT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class FileConfig:
    input_pdf: Path
    contacts_csv: Path
    output_dir: Path


def _expand_path(value: str) -> Path:
    """Expand ~ and native OS environment references in a path."""
    return Path(os.path.expandvars(os.path.expanduser(value)))


def resolve_config_dir(value: str, project_dir: Path) -> Path:
    """Resolve a configured directory independently of the current cwd."""
    path = _expand_path(value)
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def resolve_cli_path(value: Path) -> Path:
    """Preserve normal CLI behavior: relative paths use the invoking cwd."""
    return _expand_path(str(value)).resolve()


def load_file_config(project_dir: Path | None = None,
                     environment: Mapping[str, str] | None = None) -> FileConfig:
    """Load file directories and names: OS env > local .env > legacy defaults.

    The two *_FILE variables must be filenames, not paths; configure their
    parent directories separately using *_DIR.
    """
    root = (project_dir if project_dir is not None else PROJECT_DIR).resolve()
    env_file = dotenv_values(root / ".env")
    env = os.environ if environment is None else environment

    def setting(key: str, default: str) -> str:
        value = env[key] if key in env else env_file.get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must not be empty")
        return value.strip()

    def filename(key: str, default: str) -> str:
        value = setting(key, default)
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError(f"{key} must be a filename, not a path; use its *_DIR setting")
        return value

    input_dir = resolve_config_dir(setting("PDFSPLITTER_INPUT_DIR", "."), root)
    contacts_dir = resolve_config_dir(setting("PDFSPLITTER_CONTACTS_DIR", "."), root)
    output_dir = resolve_config_dir(setting("PDFSPLITTER_OUTPUT_DIR", "Renamed_PDFs"), root)

    input_file = filename("PDFSPLITTER_INPUT_FILE", "ALL.pdf")
    contacts_file = filename("PDFSPLITTER_CONTACTS_FILE", "contacts.csv")
    return FileConfig(input_dir / input_file, contacts_dir / contacts_file, output_dir)
