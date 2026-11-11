# PDFSplitter

An offline Python tool that splits employee equipment and postpaid allocation PDFs into individually named, one-page PDFs.

The original output format and matching workflow are preserved:

`Employee Name (Job Title) - Device Allocations.pdf`

**Input PDFs and contact-book records are processed locally, not uploaded to a service.**

## Features

- Split one multi-page PDF into one PDF per page.
- Extract employee names and job titles from supported allocation documents.
- Optionally cross-check employee names against a local contacts CSV.
- Preserve historical job titles printed in a signed document when they differ substantially from a current contact title.
- Recognize device and postpaid-number allocations.
- Generate per-page `split_report.csv` entries with `OK`, `REVIEW`, or `ERROR` statuses.
- Avoid overwriting existing PDFs or reports by adding numbered suffixes.
- Preview the proposed output using `--dry-run`.
- Configure input, contact-book, and output locations through the operating system environment or a local `.env` file; support absolute and relative paths on Windows, macOS, and Linux.

**Accuracy note:** `REVIEW` identifies something to verify; it does not necessarily mean PDF splitting failed. Image-only/scanned documents require OCR, which this tool does not implement.

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`: `pypdf` and `python-dotenv`

## Setup in PyCharm

1. Clone or open the project in PyCharm, and select a Python 3.10+ interpreter/virtual environment.
2. Install the requirements in the PyCharm terminal:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copy **`.env.example` to `.env`** in the folder containing `main.py`.
4. Edit the `.env` values to point to the directories containing your PDF and contact CSV, and to the output directory you want. If you use the original folder layout, no changes are required.
5. Put your real contact book on your computer (with columns `Name` and `Title` at minimum). A fictional `contacts.example.csv` is provided only as a format example. The contact CSV is optional.
6. Run `main.py` in PyCharm or run `python main.py` in the terminal. Check the resulting PDFs and `split_report.csv`.

## Environment configuration

Use the values below in `.env` (starting from `.env.example`) **or** set the same keys as operating-system environment variables / PyCharm Run Configuration environment variables:

```dotenv
PDFSPLITTER_INPUT_DIR=.
PDFSPLITTER_INPUT_FILE=ALL.pdf

PDFSPLITTER_CONTACTS_DIR=.
PDFSPLITTER_CONTACTS_FILE=contacts.csv

PDFSPLITTER_OUTPUT_DIR=Renamed_PDFs
```

| Setting | Purpose | Default |
| --- | --- | --- |
| `PDFSPLITTER_INPUT_DIR` | Folder containing the source PDF | `.` |
| `PDFSPLITTER_INPUT_FILE` | Source PDF filename | `ALL.pdf` |
| `PDFSPLITTER_CONTACTS_DIR` | Folder containing the contacts CSV | `.` |
| `PDFSPLITTER_CONTACTS_FILE` | Contacts CSV filename | `contacts.csv` |
| `PDFSPLITTER_OUTPUT_DIR` | Folder where PDFs and reports are written | `Renamed_PDFs` |

**Path handling:** Relative directory paths in `.env` and operating-system environment variables resolve from the **folder containing `main.py`**, regardless of the terminal or PyCharm working directory. `.` refers to that project folder. Absolute paths remain absolute. The code uses `pathlib` and supports `~` (home-directory expansion) and native operating-system environment-variable expansion. Use the path format for the operating system where you run the script. `*_FILE` settings accept filenames only; change `*_DIR` to move files to other locations. Missing output directories are created automatically when processing (not during a dry run).

For example, on Windows, your personal `.env` could use:

```dotenv
PDFSPLITTER_INPUT_DIR=D:/Documents/PDFs
PDFSPLITTER_INPUT_FILE=allocations.pdf
PDFSPLITTER_CONTACTS_DIR=D:/Documents/Contacts
PDFSPLITTER_CONTACTS_FILE=contacts.csv
PDFSPLITTER_OUTPUT_DIR=D:/Documents/SplitResults
```

On macOS/Linux, use native paths such as `~/Documents/PDFs`, `~/Documents/Contacts`, and `~/Documents/SplitResults` instead.

**Precedence:** Explicit **command-line options** override operating-system **environment variables**, which override the local **`.env` file**, which overrides the **built-in defaults**. `.env` is optional and intentionally excluded from Git. Environment variables are read each time the script starts.

## Command-line options

```bash
python main.py --dry-run
python main.py --input "another.pdf"
python main.py --input "another.pdf" --output "my_output"
python main.py --contacts "staff.csv"
python main.py --debug
```

Unlike configured `.env` directories, **relative command-line path options** follow normal shell conventions and resolve from the current working directory. Absolute command-line paths work too. These options let you process an unusual file without changing your saved configuration.

## Data privacy and publishing to GitHub

Do **not** commit your real employee PDFs, `contacts.csv`, generated outputs, or `.env` to a public repository. The supplied `.gitignore` excludes standard local files, virtual environments, and PyCharm state. If you configure a different private filename or output directory, make sure it is also excluded or kept outside the repository.

Check the files selected in PyCharm's **Commit** window before pushing. `.gitignore` does not retroactively hide anything already tracked by Git.

## Tests

The tests use synthetic sample names and documents—no actual employee data is required:

```bash
python -m unittest discover -s tests -v
```

The suite covers the existing PDF splitting/naming workflow and cross-platform configuration resolution.

## Project structure

- `main.py` — PDF splitting, recognition, filename creation, and CLI overrides
- `config.py` — environment-driven path configuration and resolution
- `.env.example` — example local configuration (copy to `.env`)
- `.gitignore` — exclusions for local/private artifacts
- `contacts.example.csv` — fictional example CSV layout
- `requirements.txt` — installation dependencies
- `tests/` — synthetic regression tests
- `LICENSE.txt` — MIT License

## License

MIT License. Copyright (c) 2026 Ibrahim Irusham Rashad. See [LICENSE.txt](LICENSE.txt) for the complete terms.
