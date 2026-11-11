"""Split an allocation PDF into individually named, one-page PDF files.

The original workflow is intentionally retained:
    ALL.pdf + contacts.csv -> Renamed_PDFs/<Name> (<Title>) - <Type>.pdf

Accuracy improvements: cross-check header, declaration and signature names; avoid
unreliable fuzzy matches; report questionable results instead of hiding them.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from config import load_file_config, resolve_cli_path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except ImportError:
        raise SystemExit("Missing PDF library. Run: python -m pip install -r requirements.txt")


DEBUG = False

UNKNOWN = "Unknown"
REVIEW = "REVIEW"
OK = "OK"
DOC_TYPES = ("Device Allocations", "Postpaid Number Allocations", "Unknown Document Type")


@dataclass(frozen=True)
class Contact:
    name: str
    title: str


@dataclass(frozen=True)
class Candidate:
    name: str
    title: str
    source: str
    priority: int


@dataclass(frozen=True)
class Resolution:
    name: str
    title: str
    source: str
    contact_match: str
    status: str
    notes: str


def normalize_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def fix_merged_words(text: str) -> str:
    # E.g., "AhmedAlam" but do not split acronyms like "IT".
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text or "")


def normalized_lines(text: str) -> list[str]:
    lines = []
    for line in (text or "").replace("\r", "\n").split("\n"):
        line = normalize_ascii(line)
        line = fix_merged_words(line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def normalize_compare(text: str) -> str:
    t = fix_merged_words(normalize_ascii(text)).casefold().replace("&", " and ")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def name_key(text: str) -> str:
    # No digits/periods in names; treat punctuation and spacing uniformly.
    t = fix_merged_words(normalize_ascii(text)).casefold()
    return re.sub(r"[^a-z]+", "", t)


def clean_name(text: str) -> str:
    text = fix_merged_words(normalize_ascii(text))
    text = re.sub(r"^(?:\d+[.)]\s*)?(?:[Il]\s*,\s*)", "", text.strip())
    return re.sub(r"\s+", " ", text).strip(" \t.,:;/-")


def beautify_title(text: str) -> str:
    t = fix_merged_words(normalize_ascii(text))
    t = re.sub(r"\s+", " ", t).strip(" .,:;- ")
    if not t:
        return UNKNOWN
    small = {"of", "and", "the", "in", "for", "to", "on", "at", "a", "an"}
    upper = {"it", "hr", "f&b", "gm", "dof", "ceo", "cfo", "hse"}
    parts = []
    for i, part in enumerate(t.split()):
        lower = part.lower()
        if lower in upper:
            parts.append(lower.upper())
        elif lower == "&":
            parts.append("&")
        elif i and lower in small:
            parts.append(lower)
        else:
            parts.append(part[:1].upper() + part[1:].lower())
    return " ".join(parts)


def valid_name(text: str) -> bool:
    """Reject field labels, whole paragraphs and signatures posing as names."""
    n = clean_name(text)
    tokens = normalize_compare(n).split()
    bad = {
        "date", "title", "subject", "allocation", "equipment", "company", "phone",
        "laptop", "postpaid", "mobile", "model", "issuer", "holder", "manager",
        "the", "signature", "team", "department", "end", "user", "from", "to",
    }
    return (2 <= len(tokens) <= 9 and 5 <= len(n) <= 95
            and not any(c.isdigit() for c in n)
            and not any(tok in bad for tok in tokens))


def safe_piece(text: str, max_chars: int = 95) -> str:
    text = normalize_ascii(text or UNKNOWN)
    text = re.sub(r'[\\/*?:"<>|\x00-\x1f]+', "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text[:max_chars].rstrip(" .") or UNKNOWN)


def load_contacts(path: Path) -> list[Contact]:
    if not path.is_file():
        print(f"WARNING: Contact file not found: {path} (PDF-only matching will be used)")
        return []
    result: list[Contact] = []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"Name", "Title"}.issubset(reader.fieldnames):
                print("WARNING: contacts.csv needs 'Name' and 'Title' columns; PDF-only matching will be used")
                return []
            for row in reader:
                name = clean_name(row.get("Name") or "")
                if valid_name(name):
                    result.append(Contact(name, beautify_title(row.get("Title") or "")))
    except (OSError, UnicodeError, csv.Error) as exc:
        print(f"WARNING: Unable to read contacts: {exc} (PDF-only matching will be used)")
        return []
    print(f"Loaded {len(result)} contacts")
    return result


def detect_document_type(text: str) -> str:
    t = normalize_compare(text)
    # Specific postpaid indicators must beat generic equipment wording.
    if any(signal in t for signal in (
        "company postpaid number allocation", "allocation of company postpaid number",
        "postpaid number", "mobile operator", "mobile number allocation",
    )):
        return "Postpaid Number Allocations"
    if any(signal in t for signal in (
        "allocation of equipment", "allocation of company laptop",
        "allocation of company phone", "allocated with a company phone",
        "allocated with a company laptop", "serial no", "notebook pc", "hp elitebook",
    )):
        return "Device Allocations"
    return "Unknown Document Type"


def _push(out: list[Candidate], name: str, title: str, source: str, priority: int) -> None:
    name = clean_name(name)
    if valid_name(name):
        candidate = Candidate(name, beautify_title(title), source, priority)
        if (candidate.name, candidate.title, candidate.source) not in {
            (c.name, c.title, c.source) for c in out
        }:
            out.append(candidate)


def extract_holder_candidates(text: str) -> list[Candidate]:
    """Use field boundaries, not greedy multi-line matching.

    A document's header and signed end-user field are independent sources.
    Disagreement between them is surfaced in the report.
    """
    lines = normalized_lines(text)
    candidates: list[Candidate] = []

    # The declaration field often contains the most readable name and title.
    # Restrict to one line so it cannot consume other unrelated text.
    declaration = re.compile(
        r"^(?:\d+[.)]\s*)?(?:[Il]\s*,\s*)?"
        r"(?P<name>[A-Za-z][A-Za-z .'-]{3,95}?)\s+Title\s*:\s*"
        r"(?P<title>[A-Za-z][A-Za-z &/'-]{1,100})$", re.IGNORECASE
    )
    for line in lines:
        match = declaration.fullmatch(line)
        if match:
            _push(candidates, match.group("name"), match.group("title"), "declaration", 105)

    # Many exported PDFs print header labels first and field values later:
    # "Allocation of Equipment / <issuer> / <employee> / Allocation of Company Phone".
    # Do not assume the issuer is the document holder.
    for index, line in enumerate(lines):
        if normalize_compare(line) in {"allocation of equipment", "company postpaid number allocation", "allocation of company postpaid number"}:
            following = lines[index + 1:index + 6]
            if len(following) >= 3:
                # Require the next line after employee to be the subject to avoid
                # accidentally using arbitrary boilerplate text as a name.
                if (valid_name(following[0]) and valid_name(following[1])
                        and "allocation" in normalize_compare(following[2])):
                    _push(candidates, following[1], "", "header", 115)
        # Some forms have a real 'End User: <name>' field near signature.
        match = re.match(r"^End\s*User\s*:\s*(.*)$", line, re.IGNORECASE)
        if match:
            name_parts = [match.group(1).strip()] if match.group(1).strip() else []
            for next_line in lines[index + 1:index + 3]:
                if re.match(r"^(Title\s*:|THE\s+ISSUER|IT\s+Team|\()", next_line, re.I):
                    break
                if name_parts and valid_name(" ".join(name_parts)):
                    break
                name_parts.append(next_line)
            title = ""
            for next_line in lines[index + 1:index + 4]:
                m_title = re.match(r"^Title\s*:\s*(.*)$", next_line, re.I)
                if m_title:
                    title = m_title.group(1)
                    break
            _push(candidates, " ".join(name_parts), title, "end_user", 65)

    return candidates


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def contact_score(candidate: str, contact: str) -> float:
    a, b = normalize_compare(candidate), normalize_compare(contact)
    if not a or not b:
        return 0.0
    if name_key(candidate) == name_key(contact):
        return 1.0
    aa, bb = a.split(), b.split()
    if len(aa) < 2 or len(bb) < 2:
        return 0.0
    if sorted(aa) == sorted(bb):
        return 0.99
    # A typo in an otherwise identical long name is okay only when the
    # first and last tokens are also consistent; partial names aren't enough.
    if abs(len(aa) - len(bb)) > 1:
        return 0.0
    overall = _similarity(a, b)
    first = _similarity(aa[0], bb[0])
    last = _similarity(aa[-1], bb[-1])
    if overall < 0.88 or first < 0.76 or last < 0.76:
        return 0.0
    if abs(len(aa) - len(bb)) == 1 and overall < 0.95:
        return 0.0
    return overall


def best_contact(name: str, contacts: list[Contact]) -> tuple[Optional[Contact], str, str]:
    if not contacts:
        return None, "none", ""
    ranked = sorted(((contact_score(name, c.name), c) for c in contacts),
                    key=lambda item: item[0], reverse=True)
    score, best = ranked[0]
    if score < 0.90:
        return None, "none", ""
    # Identical/near-identical records for different staff: no blind choice.
    different = [(s, c) for s, c in ranked[1:] if name_key(c.name) != name_key(best.name)]
    runner = different[0][0] if different else 0.0
    if runner >= score - 0.055:
        return None, "ambiguous", "Multiple contacts have similarly matching names"
    # Same name with conflicting titles is also ambiguous.
    duplicates = [c for s, c in ranked if s == 1.0 and name_key(c.name) == name_key(best.name)]
    if len({normalize_compare(c.title) for c in duplicates}) > 1:
        return None, "ambiguous", "Contact list contains conflicting titles for this name"
    if score == 1.0:
        return best, "exact", ""
    if score >= 0.95:
        return best, "strong", ""
    return None, "uncertain", "Possible but insufficiently reliable contact match"


def choose_best_holder(text: str, contacts: list[Contact]) -> Resolution:
    candidates = extract_holder_candidates(text)
    if not candidates:
        return Resolution(UNKNOWN, UNKNOWN, "none", "none", REVIEW, "No reliable employee name found")

    scored = []
    for cand in candidates:
        match, kind, note = best_contact(cand.name, contacts)
        # Independent declaration + header corroboration is stronger than a
        # damaged signature, even when the employee is absent from contacts.csv.
        supporting = [other for other in candidates if other.source != cand.source and
                      (name_key(other.name) == name_key(cand.name) or
                       contact_score(other.name, cand.name) >= 0.93)]
        bonus = 38 if supporting else 0
        contact_bonus = 35 if kind == "exact" else (20 if kind == "strong" else 0)
        scored.append((cand.priority + bonus + contact_bonus, cand, match, kind, note, supporting))
    scored.sort(key=lambda item: item[0], reverse=True)
    _, chosen, contact, kind, note, supporting = scored[0]

    # Prefer a matching contact's spelling, but only after strong confirmation.
    # Preserve the source document's name order. Contacts may list the exact
    # same name tokens in a different order; that must not rename the holder.
    # Use CSV spelling only for the same-order name (or a close OCR correction).
    if contact and (name_key(contact.name) == name_key(chosen.name) or
                    _similarity(normalize_compare(contact.name), normalize_compare(chosen.name)) >= 0.92):
        name = contact.name
    else:
        name = chosen.name
    title = chosen.title
    if title == UNKNOWN:
        # Title from the document declaration, if it matches this holder.
        for item in sorted(candidates, key=lambda c: c.priority, reverse=True):
            if item.title != UNKNOWN and (name_key(item.name) == name_key(name) or
                                          contact_score(item.name, name) >= 0.93):
                title = item.title
                break

    warnings = []
    if note:
        warnings.append(note)
    if contact and contact.title != UNKNOWN:
        if title == UNKNOWN:
            title = contact.title
        else:
            title_similarity = _similarity(normalize_compare(title), normalize_compare(contact.title))
            if title_similarity >= 0.86:
                # Minor spelling/OCR issues: use the verified contact spelling.
                title = contact.title
            elif title_similarity < 0.75:
                warnings.append("Document title differs from contacts.csv; kept the document title")

    # If header and declaration disagree substantially, do not hide it.
    primary = [c for c in candidates if c.source in ("header", "declaration")]
    for other in primary:
        if other is chosen:
            continue
        if name_key(other.name) != name_key(chosen.name) and contact_score(other.name, chosen.name) < 0.90:
            warnings.append("Header and declaration names disagree")
            break

    if kind in {"ambiguous", "uncertain"}:
        warnings.append("Contact not confirmed")
    if not supporting and not contact:
        warnings.append("Name appears in only one reliable field; verify manually")
    if chosen.source == "end_user" and not contact and not supporting:
        warnings.append("Name taken from signature section only")

    # Never silently classify a disputed identity as verified.
    status = REVIEW if warnings else OK
    return Resolution(name, title, chosen.source, kind, status, "; ".join(dict.fromkeys(warnings)))


def unique_output_path(directory: Path, base: str, reserved: set[str]) -> Path:
    base = base.rstrip(" .")
    suffix = 0
    while True:
        stem = base if suffix == 0 else f"{base}_{suffix}"
        filename = stem + ".pdf"
        target = directory / filename
        if filename.casefold() not in reserved and not target.exists():
            reserved.add(filename.casefold())
            return target
        suffix += 1


def unique_report_path(directory: Path) -> Path:
    number = 0
    while True:
        p = directory / ("split_report.csv" if number == 0 else f"split_report_{number}.csv")
        if not p.exists():
            return p
        number += 1


def run(input_pdf: Path, contacts_path: Path, output_dir: Path, dry_run: bool = False,
        debug: bool = False) -> int:
    if not input_pdf.is_file():
        print(f"ERROR: Input PDF not found: {input_pdf}")
        return 2
    contacts = load_contacts(contacts_path)
    try:
        reader = PdfReader(str(input_pdf))
        if reader.is_encrypted and not reader.decrypt(""):
            print("ERROR: PDF is encrypted. Unlock it first.")
            return 2
        page_count = len(reader.pages)
    except Exception as exc:
        print(f"ERROR: Cannot open PDF: {exc}")
        return 2
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Input: {input_pdf.name} ({page_count} page(s))")
    print(f"Output: {output_dir}" + (" [DRY RUN; no files written]" if dry_run else ""))
    reserved: set[str] = set()
    results = []
    for index, page in enumerate(reader.pages, start=1):
        filename = ""
        try:
            text = page.extract_text() or ""
            doc_type = detect_document_type(text)
            result = choose_best_holder(text, contacts)
            warnings = [result.notes] if result.notes else []
            status = result.status
            if not text.strip():
                warnings.append("No searchable text; scanned page or unsupported text encoding")
                status = REVIEW
            if doc_type == "Unknown Document Type":
                warnings.append("Unknown document type")
                status = REVIEW
            base = (f"{safe_piece(result.name)} ({safe_piece(result.title)}) - "
                    f"{safe_piece(doc_type)}")
            output_path = unique_output_path(output_dir, base, reserved)
            filename = output_path.name
            if not dry_run:
                # Exclusive creation prevents overwriting an earlier run's PDFs.
                # A failed write is removed to avoid leaving corrupt partial PDFs.
                created = False
                try:
                    with output_path.open("xb") as stream:
                        created = True
                        writer = PdfWriter()
                        writer.add_page(page)
                        writer.write(stream)
                except Exception:
                    if created and output_path.exists():
                        output_path.unlink()
                    raise
            detail = "; ".join(w for w in warnings if w)
            results.append({"page": index, "status": status, "employee_name": result.name,
                            "job_title": result.title, "document_type": doc_type,
                            "filename": filename, "name_source": result.source,
                            "contact_match": result.contact_match, "notes": detail})
            print(f"{'REVIEW' if status == REVIEW else 'OK'} Page {index} -> {filename}"
                  + (f" | {detail}" if detail else ""))
            if debug:
                for cand in extract_holder_candidates(text):
                    print(f"   candidate[{cand.source}]: {cand.name} / {cand.title}")
        except Exception as exc:
            results.append({"page": index, "status": "ERROR", "employee_name": "",
                            "job_title": "", "document_type": "", "filename": filename,
                            "name_source": "", "contact_match": "", "notes": str(exc)})
            print(f"ERROR Page {index}: {exc}")
    if not dry_run:
        report_path = unique_report_path(output_dir)
        with report_path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=["page", "status", "employee_name",
                "job_title", "document_type", "filename", "name_source", "contact_match", "notes"])
            writer.writeheader()
            writer.writerows(results)
        print(f"Report: {report_path}")
    counts = {key: sum(row["status"] == key for row in results) for key in (OK, REVIEW, "ERROR")}
    print(f"Done: {counts[OK]} OK, {counts[REVIEW]} REVIEW, {counts['ERROR']} ERROR")
    return 1 if counts["ERROR"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Split and accurately label PDF allocation pages")
    parser.add_argument("--input", type=Path, help="PDF to split (overrides environment configuration)")
    parser.add_argument("--contacts", type=Path, help="Contact CSV (overrides environment configuration)")
    parser.add_argument("--output", type=Path, help="Output folder (overrides environment configuration)")
    parser.add_argument("--dry-run", action="store_true", help="Preview filenames without writing files")
    parser.add_argument("--debug", action="store_true", default=DEBUG, help="Print name candidate diagnostics")
    args = parser.parse_args()
    try:
        config = load_file_config()
    except (OSError, ValueError) as exc:
        print(f"ERROR: Invalid file configuration: {exc}", file=sys.stderr)
        return 2

    # Explicit CLI paths follow normal shell behavior (relative to the current
    # working directory). .env paths are always relative to the project folder.
    input_pdf = resolve_cli_path(args.input) if args.input is not None else config.input_pdf
    contacts_csv = resolve_cli_path(args.contacts) if args.contacts is not None else config.contacts_csv
    output_dir = resolve_cli_path(args.output) if args.output is not None else config.output_dir
    return run(input_pdf, contacts_csv, output_dir, args.dry_run, args.debug)


if __name__ == "__main__":
    sys.exit(main())
