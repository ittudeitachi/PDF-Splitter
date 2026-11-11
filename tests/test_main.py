"""Public, self-contained regression tests. No employee data required.

Run: python -m unittest discover -s tests -v
"""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


# Build an extractable-text PDF using only the declared pypdf dependency.
# All names, titles, and sample data below are fictional.
def create_sample_pdf(destination: Path) -> None:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    examples = [
        ["Allocation of Equipment", "Morgan Blake", "Alex Morgan",
         "Allocation of Company Phone", "Alex Morgan Title: Accountant",
         "End User: Alex Morgan", "Title: Accountant"],
        ["Allocation of Equipment", "Morgan Blake", "Jordan Taylor",
         "Allocation of Company Phone", "Jordan Taylor Title: Butler",
         "End User: Jordan Taylor", "Title: Butler"],
    ]
    for lines in examples:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        # ASCII content keeps the sample simple and portable.
        contents = "BT /F1 11 Tf 45 730 Td 15 TL " + " ".join(
            f"({line}) Tj T*" for line in lines
        ) + " ET"
        stream = DecodedStreamObject()
        stream.set_data(contents.encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(str(destination))


class ExtractionTests(unittest.TestCase):
    def test_name_title_and_type(self):
        text = ("Allocation of Equipment\nMorgan Blake\nAlex Morgan\n"
                "Allocation of Company Phone\nAlex Morgan Title: Accountant\n")
        result = main.choose_best_holder(text, [main.Contact("Alex Morgan", "Accountant")])
        self.assertEqual((result.name, result.title, result.status),
                         ("Alex Morgan", "Accountant", main.OK))
        self.assertEqual(main.detect_document_type(text), "Device Allocations")

    def test_director_of_sales_remains_plural(self):
        text = ("Allocation of Equipment\nMorgan Blake\nCasey Jordan\n"
                "Allocation of Company Phone\nCasey Jordan Title: Director of Sales\n")
        result = main.choose_best_holder(text, [main.Contact("Casey Jordan", "Director of Sales")])
        self.assertEqual(result.title, "Director of Sales")

    def test_historical_document_title_is_not_replaced_by_promotion(self):
        text = ("Allocation of Equipment\nMorgan Blake\nJordan Taylor\n"
                "Allocation of Company Phone\nJordan Taylor Title: Butler\n")
        result = main.choose_best_holder(text, [main.Contact("Jordan Taylor", "Senior Butler")])
        self.assertEqual(result.name, "Jordan Taylor")
        self.assertEqual(result.title, "Butler")

    def test_postpaid_type_precedes_generic_device(self):
        text = "Allocation of Equipment\nCompany Postpaid Number Allocation"
        self.assertEqual(main.detect_document_type(text), "Postpaid Number Allocations")

    def test_conflicting_header_and_declaration_is_review(self):
        text = ("Allocation of Equipment\nMorgan Blake\nAlex Morgan\n"
                "Allocation of Company Phone\nJordan Taylor Title: Accountant\n")
        result = main.choose_best_holder(text, [])
        self.assertEqual(result.status, main.REVIEW)
        self.assertIn("disagree", result.notes)

    def test_no_holder_requires_review(self):
        result = main.choose_best_holder("not a recognizable document", [])
        self.assertEqual((result.name, result.status), ("Unknown", main.REVIEW))

    def test_windows_filename_is_sanitized(self):
        self.assertEqual(main.safe_piece("  Kay / Lane: Team?  "), "Kay Lane Team")

    def test_contacts_name_order_is_preserved(self):
        text = ("Allocation of Equipment\nMorgan Blake\nAlex Jordan Morgan\n"
                "Allocation of Company Phone\nAlex Jordan Morgan Title: Butler\n")
        result = main.choose_best_holder(text, [main.Contact("Jordan Morgan Alex", "Butler")])
        self.assertEqual(result.name, "Alex Jordan Morgan")


class SplittingTests(unittest.TestCase):
    def test_split_and_rerun_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "sample.pdf"
            output = directory / "output"
            contacts_path = directory / "contacts.csv"
            create_sample_pdf(source)
            contacts_path.write_text("Name,Title\nAlex Morgan,Accountant\n"
                                     "Jordan Taylor,Senior Butler\n", encoding="utf-8")

            self.assertEqual(main.run(source, contacts_path, output), 0)
            files = sorted(output.glob("*.pdf"))
            self.assertEqual(len(files), 2)
            self.assertTrue((output / "split_report.csv").exists())
            pages = [p for path in files for p in PdfReader(str(path)).pages]
            self.assertEqual(len(pages), 2)
            originals = sorted((p.extract_text() or "") for p in PdfReader(str(source)).pages)
            actual = sorted((p.extract_text() or "") for p in pages)
            self.assertEqual(actual, originals)
            self.assertTrue(any("Jordan Taylor (Butler)" in p.name for p in files))

            with (output / "split_report.csv").open(newline="", encoding="utf-8-sig") as file:
                report = list(csv.DictReader(file))
            self.assertEqual([r["page"] for r in report], ["1", "2"])

            self.assertEqual(main.run(source, contacts_path, output), 0)
            self.assertEqual(len(list(output.glob("*.pdf"))), 4)
            self.assertTrue((output / "split_report_1.csv").exists())

    def test_dry_run_creates_no_files(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "sample.pdf"
            output = directory / "output"
            create_sample_pdf(source)
            self.assertEqual(main.run(source, directory / "missing.csv", output, dry_run=True), 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
