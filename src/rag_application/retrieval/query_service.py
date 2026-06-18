from rag_application.retrieval.retriever import Retriever

class QueryService:
    def __init__(
            self, 
            retriever: Retriever
    ):
        self.retriever = retriever

    def search(
            self, 
            query: str, 
            top_k: int = 5
    ):
        return self.retriever.retrieve(
            query=query, 
            top_k=top_k
        )