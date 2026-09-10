from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

logger = logging.getLogger(__name__)


class UploadService:
    """
    Handles saving uploaded files to temporary storage
    and cleaning them up after ingestion.
    """

    def __init__(self, upload_directory: str | Path = "storage/uploads") -> None:
        self.upload_directory = Path(upload_directory)
        self.upload_directory.mkdir(parents=True, exist_ok=True)

    def save(self, upload_file: UploadFile) -> Path:
        """
        Save an uploaded file to temporary storage.

        Returns:
            Path to the saved file.
        """

        extension = Path(upload_file.filename or "").suffix.lower()

        unique_filename = f"{uuid4().hex}{extension}"

        destination = self.upload_directory / unique_filename

        try:
            with destination.open("wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)

            logger.info("Saved uploaded file to %s", destination)

            return destination

        except Exception:
            logger.exception("Failed to save uploaded file.")

            if destination.exists():
                destination.unlink(missing_ok=True)

            raise

    def delete(self, file_path: str | Path) -> None:
        """
        Delete a temporary uploaded file.
        """

        path = Path(file_path)

        try:
            if path.exists():
                path.unlink()
                logger.info("Deleted temporary file %s", path)

        except Exception:
            logger.exception("Failed to delete temporary file %s", path)