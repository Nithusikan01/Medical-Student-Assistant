class PDFLoadError(Exception):
    """Raised when a PDF file cannot be loaded."""
    pass

class ChunkingError(Exception):
    """Raised when an error occurs during the chunking process."""
    pass

class EmbeddingError(Exception):
    """Raised when an error occurs during the embedding process."""
    pass

class VectorStoreError(Exception):
    """Raised when an error occurs while interacting with the vector store."""
    pass