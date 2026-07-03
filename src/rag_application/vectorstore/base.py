from abc import ABC, abstractmethod
from typing import List, Dict


class VectorStoreInterface(ABC):
    @abstractmethod
    def store_vectors(self, vector_data: List[Dict]) -> str:
        """
        Store vectors in the vector database.
        """
        pass

    
    @abstractmethod
    def retrieve_vectors(self, query_vector, top_k: int = 5)-> List[Dict]:
        """
        Retrieve similar vectors from the vector database based on a query vector.
        """
        pass

    @abstractmethod
    def delete_vectors(self, vector_ids: List[str]) -> None:
        """
        Delete vectors from the vector database based on their IDs.
        """
        pass