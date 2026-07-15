import logging
from pathlib import Path
from typing import List

from pypdf import PdfReader

from rag_application.utils.exceptions import PDFLoadError

logger = logging.getLogger(__name__)


class DocumentLoader:

    def load(self, file_path: str | Path) -> List[str]:

        try:
            reader = PdfReader(file_path)

            pages = []

            for page in reader.pages:
                text = page.extract_text()

                if text:
                    pages.append(text)

            if not pages:
                raise PDFLoadError(
                    f"No text found in PDF: {file_path}"
                )

            logger.info(
                "Loaded %d pages from %s",
                len(pages),
                file_path
            )

            return pages

        except Exception as e:
            logger.exception(
                "Failed to load PDF: %s",
                file_path
            )

            raise PDFLoadError(
                f"Failed to load PDF: {file_path}"
            ) from e
