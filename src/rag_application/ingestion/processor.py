from typing import Dict, List
import time
from rag_application.ingestion.schemas import DocumentChunk


class VectorDataProcessor:

    def prepare(
        self,
        vectors: List[List[float]],
        chunks: List[DocumentChunk]
    ) -> List[Dict]:

        if len(vectors) != len(chunks):
            raise ValueError("Mismatch between vectors and chunks")

        timestamp = int(time.time())

        vector_data = []

        for vector, chunk in zip(vectors, chunks):

            metadata = {
                "original_text": chunk.text,
                "chunk_id": chunk.chunk_index,
                "source": chunk.source,
                "timestamp": timestamp,
            }

            vector_data.append({
                "id": chunk.id,
                "vector": vector,
                "metadata": metadata
            })

        return vector_data