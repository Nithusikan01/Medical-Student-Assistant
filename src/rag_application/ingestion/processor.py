from typing import Dict
from typing import List
from typing import Optional

import time


class VectorDataProcessor:

    def prepare(
        self,
        vectors: List[List[float]],
        chunks: List[str],
        source: str = "unknown",
        page_numbers: Optional[List[int]] = None
    ) -> List[Dict]:

        if len(vectors) != len(chunks):
            raise ValueError(
                "vectors and chunks length mismatch"
            )

        if (
            page_numbers is not None
            and len(page_numbers) != len(chunks)
        ):
            raise ValueError(
                "page_numbers length mismatch"
            )

        timestamp = int(time.time())

        vector_data = []

        for i, (vector, chunk) in enumerate(
            zip(vectors, chunks)
        ):

            metadata = {
                "original_text": chunk,
                "chunk_id": i,
                "source": source,
                "timestamp": timestamp
            }

            if page_numbers:
                metadata["page_number"] = (
                    page_numbers[i]
                )

            vector_data.append(
                {
                    "id": f"{source}_chunk_{i}",
                    "vector": vector,
                    "metadata": metadata
                }
            )

        return vector_data