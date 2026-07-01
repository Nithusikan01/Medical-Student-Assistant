import os
from dataclasses import dataclass
from rag_application.config.component_configs import (
    PineconeConfig,
    EmbeddingConfig,
    GenerationConfig,
    ChunkingConfig,
    RetrievalConfig
)

@dataclass(frozen=True)
class Settings:
    pinecone_api_key: str
    pinecone_index_name: str
    gemini_api_key: str 

    chunk_size: int = 500
    chunk_overlap: int = 50

    retrieval_top_k: int = 5
    initial_retrieval_k: int = 20
    reranking_k: int = 8
    final_context_k: int = 5
    similarity_threshold: float = 0.7

    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    generation_model_name: str = "gemini-3.1-flash-lite"

    def pinecone_config(self) -> PineconeConfig:
        return PineconeConfig(
            api_key=self.pinecone_api_key,
            index_name=self.pinecone_index_name
        )

    def embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_name=self.embedding_model_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

    def generation_config(self) -> GenerationConfig:
        return GenerationConfig(
            model_name=self.generation_model_name,
            api_key=self.gemini_api_key
        )

    def chunking_config(self) -> ChunkingConfig:
        return ChunkingConfig(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

    def retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            initial_retrieval_k=self.initial_retrieval_k,
            reranking_k=self.reranking_k,
            final_context_k=self.final_context_k,
            similarity_threshold=self.similarity_threshold
        )

def load_settings() -> Settings:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not pinecone_api_key:
        raise ValueError(
            "PINECONE_API_KEY environment variable is not set."
            )
    
    if not pinecone_index_name:
        raise ValueError(
            "PINECONE_INDEX_NAME environment variable is not set."
            )
    
    if not gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set."
            )

    return Settings(
        pinecone_api_key=pinecone_api_key, 
        pinecone_index_name=pinecone_index_name,
        gemini_api_key=gemini_api_key,
        chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
        retrieval_top_k=int(os.getenv("RETRIEVAL_TOP_K", "5")),
        initial_retrieval_k=int(os.getenv("INITIAL_RETRIEVAL_K", "20")),
        reranking_k=int(os.getenv("RERANKING_K", "8")),
        final_context_k=int(os.getenv("FINAL_CONTEXT_K", "5")),
        similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.7")),
        embedding_model_name=os.getenv(
            "EMBEDDING_MODEL_NAME",
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
        generation_model_name=os.getenv(
            "GENERATION_MODEL_NAME",
            "gemini-3.1-flash-lite"
        ),
    )
