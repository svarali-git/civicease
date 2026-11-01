"""Turn the sample .txt scheme documents into real PDFs (text-based, multi-line).

Usage (from the project root):  python scripts/make_sample_pdfs.py
Also creates samples/sample_scanned_like.pdf, a PDF with no readable text, for error-handling demos.
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "backend" / "tests" / "fixtures"


def text_to_pdf(src: Path, dest: Path) -> None:
    c = canvas.Canvas(str(dest), pagesize=A4)
    width, height = A4
    y = height - 56
    for raw in src.read_text(encoding="utf-8").splitlines():
        heading = bool(raw.strip()) and not raw.startswith((" ", "-", "1", "2", "3", "4", "5")) and len(raw) < 40
        c.setFont("Helvetica-Bold" if heading else "Helvetica", 12 if heading else 10.5)
        # wrap long lines at roughly 95 characters
        words, line = raw.split(" "), ""
        for w in words:
            if len(line) + len(w) + 1 > 95:
                c.drawString(56, y, line)
                y -= 15
                line = w
            else:
                line = (line + " " + w).strip()
        c.drawString(56, y, line)
        y -= 15 if raw.strip() else 9
        if y < 56:
            c.showPage()
            y = height - 56
    c.save()


def main() -> None:
    for txt in SAMPLES.glob("sample_*_scheme.txt"):
        text_to_pdf(txt, txt.with_suffix(".pdf"))
        print("wrote", txt.with_suffix(".pdf").name)
    blank = canvas.Canvas(str(SAMPLES / "sample_scanned_like.pdf"), pagesize=A4)
    blank.rect(100, 100, 300, 300)  # a drawing only, no text layer
    blank.save()
    print("wrote sample_scanned_like.pdf")


if __name__ == "__main__":
    main()
