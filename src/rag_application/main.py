from dotenv import load_dotenv
from pathlib import Path
import logging

from rag_application.config.settings import load_settings
from rag_application.config.component_configs import ChunkingConfig, EmbeddingConfig
from rag_application.utils.logger import setup_logging

from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.vectorstore.pinecone_store import PineconeVectorStore as VectorStore


def main():

    # --------------------------------------------------
    # 1. Load environment + logging
    # --------------------------------------------------
    load_dotenv()
    setup_logging()

    logger = logging.getLogger(__name__)
    logger.info("Starting ingestion pipeline...")

    # --------------------------------------------------
    # 2. Load settings (single source of truth)
    # --------------------------------------------------
    settings = load_settings()

    # --------------------------------------------------
    # 3. Resolve file path (clean + portable)
    # --------------------------------------------------
    base_dir = Path(__file__).resolve().parents[2]
    file_path = base_dir / "data" / "raw" / "cv.pdf"

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"PDF not found at {file_path}")
    
    # -------------------------------------------------
    # 3. Initialize components
    # -------------------------------------------------
    document_loader = DocumentLoader()
    chunker = TextChunker(
        config=ChunkingConfig(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
    )
    vector_data_processor = VectorDataProcessor()

    # --------------------------------------------------
    # 4. Initialize embedder
    # --------------------------------------------------
    embedder = Embedder(
        config=EmbeddingConfig(
            model_name=settings.embedding_model_name,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
    )

    # --------------------------------------------------
    # 5. Vector store (dimension derived safely from embedder)
    # --------------------------------------------------
    sample_embedding = embedder.model.encode("dimension_check")
    dimension = len(sample_embedding)

    vector_store = VectorStore(
        settings=settings,
        dimension=dimension
    )

    # --------------------------------------------------
    # 6. Build ingestion pipeline
    # --------------------------------------------------
    pipeline = IngestionPipeline(
        document_loader=document_loader,
        chunker=chunker,
        embedder=embedder,
        vector_data_processor=vector_data_processor,
        vector_store=vector_store
    )

    # --------------------------------------------------
    # 7. Run pipeline
    # --------------------------------------------------
    logger.info("Running ingestion pipeline...")
    pipeline.run(str(file_path))

    logger.info("Pipeline execution finished successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Pipeline failed: {e}", exc_info=True)
        raise
