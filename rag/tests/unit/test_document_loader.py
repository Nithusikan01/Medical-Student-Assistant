from unittest.mock import MagicMock, patch

from rag.ingestion.document_loader import DocumentLoader


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
