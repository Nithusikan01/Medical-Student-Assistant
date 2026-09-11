class PDFLoadError(Exception):
    """Raised when a PDF file cannot be loaded."""


class ChunkingError(Exception):
    """Raised when an error occurs during the chunking process."""


class EmbeddingError(Exception):
    """Raised when an error occurs during the embedding process."""


class VectorStoreError(Exception):
    """Raised when an error occurs while interacting with the vector store."""
