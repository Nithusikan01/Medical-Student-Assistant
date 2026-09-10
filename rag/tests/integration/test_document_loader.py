from pathlib import Path

from rag_application.ingestion.document_loader import DocumentLoader

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "cv.pdf"


def test_load_pdf_fixture():
    document = DocumentLoader().load(str(FIXTURE_PATH))

    assert document.filename == "cv.pdf"
    assert document.pages
    assert all(page.text.strip() for page in document.pages)
