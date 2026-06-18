from unittest.mock import patch, MagicMock
from rag_application.ingestion.document_loader import DocumentLoader

@patch('rag_application.ingestion.document_loader.PdfReader')
def test_load_pdf(mock_pdf_reader):

    page1 = MagicMock()
    page1.extract_text.return_value = "This is the first page."

    page2 = MagicMock()
    page2.extract_text.return_value = "This is the second page."

    mock_pdf_reader.return_value.pages = [ 
        page1, 
        page2
    ]

    document_loader = DocumentLoader()
    result = document_loader.load("dummy_path.pdf")

    assert len(result) == 2
    assert result[0] == "This is the first page."
    assert result[1] == "This is the second page."
