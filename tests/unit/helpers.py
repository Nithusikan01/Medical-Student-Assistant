from rag_application.ingestion.schemas import (
    ChunkMetadata,
    DocumentChunk,
    EmbeddedChunk,
    LoadedDocument,
    LoadedPage,
)
from rag_application.retrieval.schemas import (
    RetrievedChunk,
    RetrievedChunkMetadata,
)
from rag_application.vectorstore.schemas import (
    SearchResult,
    VectorRecord,
    VectorRecordMetadata,
)


def make_chunk(
    index: int = 0,
    text: str = "chunk text",
    *,
    document_id: str = "doc",
    filename: str = "doc.pdf",
) -> DocumentChunk:
    return DocumentChunk(
        id=f"{document_id}_chunk_{index}",
        chunk_index=index,
        text=text,
        metadata=ChunkMetadata(
            document_id=document_id,
            filename=filename,
            source_path=f"/tmp/{filename}",
            page_number=1,
            chunk_size=len(text),
        ),
    )


def make_loaded_document(text: str = "Hello world " * 20) -> LoadedDocument:
    return LoadedDocument(
        document_id="doc",
        filename="doc.pdf",
        source_path="/tmp/doc.pdf",
        pages=[
            LoadedPage(
                page_number=1,
                text=text,
            )
        ],
    )


def make_embedded_chunk(
    index: int = 0,
    text: str = "chunk text",
    embedding: list[float] | None = None,
) -> EmbeddedChunk:
    chunk = make_chunk(index=index, text=text)
    return EmbeddedChunk(
        id=chunk.id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        metadata=chunk.metadata,
        embedding=embedding or [0.1, 0.2],
    )


def make_retrieved_chunk(
    chunk_id: str = "chunk_1",
    text: str = "retrieved text",
    score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        text=text,
        score=score,
        metadata=RetrievedChunkMetadata(
            document_id="doc",
            filename="doc.pdf",
            source_path="/tmp/doc.pdf",
            chunk_index=0,
        ),
    )


def make_search_result(
    chunk_id: str = "doc_chunk_0",
    text: str = "retrieved text",
    score: float = 0.95,
) -> SearchResult:
    return SearchResult(
        id=chunk_id,
        score=score,
        metadata=VectorRecordMetadata(
            document_id="doc",
            filename="doc.pdf",
            source_path="/tmp/doc.pdf",
            text=text,
            chunk_index=0,
        ),
    )


def make_vector_record() -> VectorRecord:
    metadata = VectorRecordMetadata(
        document_id="doc",
        filename="doc.pdf",
        source_path="/tmp/doc.pdf",
        text="chunk text",
        chunk_index=0,
    )
    return VectorRecord(
        id="doc_chunk_0",
        values=[0.1, 0.2],
        metadata=metadata,
    )
