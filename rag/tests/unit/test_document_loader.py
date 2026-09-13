from pathlib import Path
from unittest.mock import MagicMock, patch

from rag.ingestion.document_loader import DocumentLoader

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "cv.pdf"


@patch("rag.ingestion.document_loader.PdfReader")
def test_load_pdf(mock_pdf_reader):
    page1 = MagicMock()
    page1.extract_text.return_value = "This is the first page."

    page2 = MagicMock()
    page2.extract_text.return_value = "This is the second page."

    mock_pdf_reader.return_value.pages = [
        page1,
        page2,
    ]

    result = DocumentLoader().load("dummy_path.pdf")

    assert result.filename == "dummy_path.pdf"
    assert len(result.pages) == 2
    assert result.pages[0].text == "This is the first page."
    assert result.pages[1].page_number == 2


def test_load_a_real_pdf():
    """
    The test above mocks PdfReader, so it would pass even if pypdf were
    misused. This one reads an actual PDF from the fixtures directory.
    """

    document = DocumentLoader().load(str(FIXTURE_PATH))

    assert document.filename == "cv.pdf"
    assert document.pages
    assert any(page.text.strip() for page in document.pages)
    assert document.pages[0].page_number == 1


def test_the_caller_may_supply_the_document_id():
    """
    The API mints the id and inserts the registry row before ingestion, so
    the loader has to accept one rather than always generating its own.
    """

    document = DocumentLoader().load(str(FIXTURE_PATH), document_id="fixed-id")

    assert document.document_id == "fixed-id"


def test_a_display_filename_overrides_the_path():
    """
    Uploads are saved under a generated name; without this the citations
    would show '9b0f2c4a-....pdf' instead of the document's real title.
    """

    document = DocumentLoader().load(
        str(FIXTURE_PATH),
        filename="Curriculum Vitae.pdf",
    )

    assert document.filename == "Curriculum Vitae.pdf"
