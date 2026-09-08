"""
Streaming builder for the BM25 corpus.

This component incrementally builds the BM25 corpus while the
ingestion pipeline processes document chunks in batches.

The builder is responsible only for persisting BM25 corpus records.
Transformation from DocumentChunk to BM25CorpusRecord is delegated
to the serializer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TextIO

from rag_application.ingestion.schemas import DocumentChunk

from .schemas import BM25CorpusRecord

logger = logging.getLogger(__name__)


class BM25CorpusBuilder:
    """
    Incrementally builds the BM25 corpus.

    Example
    -------
    with BM25CorpusBuilder(output_path) as builder:

        builder.add_batch(chunk_batch)
        builder.add_batch(chunk_batch)
    """

    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.temp_path = output_path.with_suffix(".tmp")

        self._file: TextIO | None = None
        self._document_count = 0
        self._first_record = True

    # ------------------------------------------------------------------
    # Context Manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "BM25CorpusBuilder":
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        if exc_type is None:
            self.finish()
        else:
            self.abort()

        # Never suppress exceptions
        return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start writing a new BM25 corpus.
        """

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._file = self.temp_path.open(
            mode="w",
            encoding="utf-8",
        )

        self._file.write("[\n")

        self._document_count = 0
        self._first_record = True

        logger.info(
            "Started BM25 corpus build: %s",
            self.output_path,
        )

    def add_batch(
        self,
        chunks: list[DocumentChunk],
    ) -> None:
        """
        Serialize and persist one batch of document chunks.
        """

        if self._file is None:
            raise RuntimeError(
                "BM25CorpusBuilder has not been started."
            )

        for chunk in chunks:

            if not self._first_record:
                self._file.write(",\n")

            record = BM25CorpusRecord.from_chunk(chunk)

            self._file.write(
                record.model_dump_json(indent=None)
            )

            self._first_record = False
            self._document_count += 1

        logger.debug(
            "Added %d BM25 records.",
            len(chunks),
        )

    def finish(self) -> None:
        """
        Finish writing the BM25 corpus.
        """

        if self._file is None:
            return

        try:
            self._file.write("\n]")
            self._file.close()

            self.temp_path.replace(self.output_path)

            logger.info(
                "Finished BM25 corpus build (%d records).",
                self._document_count,
            )

        finally:
            self._file = None

            if self.temp_path.exists():
                try:
                    self.temp_path.unlink()
                except OSError:
                    pass

    def abort(self) -> None:
        """
        Close and remove the temporary corpus after a failed build.
        """

        if self._file is not None:
            self._file.close()
            self._file = None

        if self.temp_path.exists():
            try:
                self.temp_path.unlink()
            except OSError:
                logger.warning(
                    "Failed to remove temporary BM25 corpus: %s",
                    self.temp_path,
                )
