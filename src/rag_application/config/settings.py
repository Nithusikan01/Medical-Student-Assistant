import os
from dataclasses import dataclass
from rag_application.config.component_configs import (
    PineconeConfig,
    EmbeddingConfig,
    GenerationConfig,
    ChunkingConfig
)

@dataclass(frozen=True)
class Settings:
    pinecone_api_key: str
    pinecone_index_name: str
    gemini_api_key: str 

    chunk_size: int = 500
    chunk_overlap: int = 50

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
        gemini_api_key=gemini_api_key
    )