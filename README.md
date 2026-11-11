# PDFSplitter

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/ittudeitachi/PDF-Splitter/blob/main/LICENSE.txt)
[![GitHub release](https://img.shields.io/github/v/release/ittudeitachi/PDF-Splitter?label=Release)](https://github.com/ittudeitachi/PDF-Splitter/releases)

PDFSplitter is a Python command-line tool for splitting multi-page PDF allocation documents into separate, clearly named files.

It extracts employee names and job titles from supported documents, optionally checks them against a local contactbook, and generates a report so you can review uncertain results.

## What It Does

PDFSplitter processes a PDF page by page and provides:

- Individual PDF files for each page
- Employee name and job title extraction
- Optional employee verification using `contacts.csv`
- Recognition of device and postpaid-number allocation documents
- Descriptive filenames based on the extracted information
- Review flags for ambiguous or conflicting information
- A `split_report.csv` with per-page results
- Duplicate filename protection to avoid overwriting existing files
- A dry-run mode to preview filenames without creating files

When a document contains a historical job title, PDFSplitter can preserve that title even if the contactbook shows a newer one.

## What It Does Not Do Yet

PDFSplitter does not perform OCR. Scanned or image-only PDFs need a searchable text layer before employee details can be extracted reliably.

It is designed for supported allocation document layouts, not arbitrary PDF forms. Unrecognized document types and uncertain matches are flagged for manual review rather than silently assumed to be correct.

## Example

Input:

```text
ALL.pdf
```

Example output filenames:

```text
Alex Morgan (Accountant) - Device Allocations.pdf
Jordan Taylor (Butler) - Device Allocations.pdf
```

Example processing summary:

```text
OK Page 1 -> Alex Morgan (Accountant) - Device Allocations.pdf
REVIEW Page 2 -> Jordan Taylor (Butler) - Device Allocations.pdf | Document title differs from contacts.csv; kept the document title
Report: .../Renamed_PDFs/split_report.csv
Done: 1 OK, 1 REVIEW, 0 ERROR
```

The names above are fictional examples. Page 2 illustrates a historical job title being kept even when the contactbook shows a promotion. Actual results depend on the PDF content.

## Requirements

- Python 3.10 or newer
- `pypdf`
- `python-dotenv`

Install the packages listed in `requirements.txt` as shown below.

## Installation

Clone the repository:

```bash
git clone https://github.com/ittudeitachi/PDF-Splitter.git
cd PDF-Splitter
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment:

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

### Windows (Command Prompt)

```bat
.venv\Scripts\activate.bat
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install the required packages:

```bash
python -m pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` in the project root:

```dotenv
PDFSPLITTER_INPUT_DIR=.
PDFSPLITTER_INPUT_FILE=ALL.pdf

PDFSPLITTER_CONTACTS_DIR=.
PDFSPLITTER_CONTACTS_FILE=contacts.csv

PDFSPLITTER_OUTPUT_DIR=Renamed_PDFs
```

The defaults expect `ALL.pdf` and, optionally, `contacts.csv` in the project folder. Output files are written to `Renamed_PDFs`.

- `PDFSPLITTER_INPUT_DIR` and `PDFSPLITTER_INPUT_FILE` select the source PDF.
- `PDFSPLITTER_CONTACTS_DIR` and `PDFSPLITTER_CONTACTS_FILE` select the contactbook.
- `PDFSPLITTER_OUTPUT_DIR` selects the output folder.

You can use absolute paths or relative directory paths on Windows, macOS, and Linux. Configured relative directories resolve from the project folder, not the terminal's current working directory. The output directory is created automatically when needed.

Environment variable precedence is **command-line option > system environment variable > `.env` > default**. Command-line relative paths resolve from the current working directory.

Your optional contacts CSV should include `Name` and `Title` columns. See `contacts.example.csv` for the format:

```csv
Name,Title
Alex Morgan,Accountant
Jordan Taylor,Senior Butler
```

If the contacts file is missing, PDFSplitter continues using information extracted from the PDF without contactbook verification.

**Privacy:** Keep real employee PDFs, `contacts.csv`, and `.env` on your machine. Do not commit them to a public repository.

## Usage

Run PDFSplitter with the configured paths:

```bash
python main.py
```

Preview filenames without writing files:

```bash
python main.py --dry-run
```

Override the paths for a single run:

```bash
python main.py --input "another.pdf" --contacts "staff.csv" --output "my_output"
```

Print extra name-extraction diagnostics:

```bash
python main.py --debug
```

After processing, check the generated PDFs and `split_report.csv` inside your output folder.

The report marks each page as `OK`, `REVIEW`, or `ERROR`. A `REVIEW` status indicates that the filename or extracted details should be checked; it does not necessarily mean PDF splitting failed.

If a filename already exists, PDFSplitter adds a number rather than overwriting it. Existing processing reports are also preserved.

## Project Structure

```text
PDF-Splitter/
├── main.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── contacts.example.csv
├── tests/
│   ├── test_config.py
│   └── test_main.py
├── LICENSE.txt
└── README.md
```

## Tests

Run the included regression tests:

```bash
python -m unittest discover -s tests -v
```

The tests use synthetic sample data rather than private employee documents.

## Potential Future Improvements

- OCR support for scanned documents
- Recognition of additional PDF document layouts
- Additional report export formats

These are possible enhancements, not features included in the current release.

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
