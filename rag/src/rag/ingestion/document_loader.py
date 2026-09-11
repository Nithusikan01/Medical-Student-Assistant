import logging
import uuid
from pathlib import Path

from pypdf import PdfReader

from rag.ingestion.schemas import (
    LoadedDocument,
    LoadedPage,
)
from rag.utils.exceptions import PDFLoadError

logger = logging.getLogger(__name__)


class DocumentLoader:

    def load(
        self,
        file_path: str | Path,
        document_id: str | None = None,
        filename: str | None = None,
    ) -> LoadedDocument:
        """
        Load a PDF document and extract text from each page.

        Passing document_id lets the caller mint the id up front, so a
        registry row can exist before ingestion starts. Passing filename
        keeps the original name in chunk metadata when the file on disk is a
        temporary upload with a generated name - otherwise every citation
        would show that generated name. Both default to the file itself.

        Returns
        -------
        LoadedDocument
            A structured representation of the document.
        """

        file_path = Path(file_path)

        try:
            reader = PdfReader(file_path)

            document = LoadedDocument(
                document_id=document_id or str(uuid.uuid4()),
                filename=filename or file_path.name,
                source_path=str(file_path.resolve()),
                pages=[],
            )

            for page_number, page in enumerate(reader.pages, start=1):

                text = page.extract_text()

                if not text or not text.strip():
                    continue

                document.pages.append(
                    LoadedPage(
                        page_number=page_number,
                        text=text.strip(),
                    )
                )

            if not document.pages:
                raise PDFLoadError(f"No text found in PDF: {file_path}")

            logger.info(
                "Loaded '%s' (%d pages)",
                document.filename,
                len(document.pages),
            )

            return document

        except Exception as exc:
            logger.exception(
                "Failed to load PDF: %s",
                file_path,
            )

            raise PDFLoadError(f"Failed to load PDF: {file_path}") from exc
