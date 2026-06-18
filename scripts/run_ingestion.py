from dotenv import load_dotenv
from pathlib import Path
import logging

from rag_application.config.settings import load_settings
from rag_application.utils.logger import setup_logging

from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.vectorstore.pinecone_store import VectorStore


def main():
    load_dotenv()
    setup_logging()

    logger = logging.getLogger(__name__)

    settings = load_settings()

    file_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "cv.pdf"

    document_loader = DocumentLoader()

    chunker = TextChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap
    )

    embedder = Embedder(settings.embedding_model_name)

    # temporary embedder init to get dimension
    dim = len(embedder.model.encode("test"))

    vector_data_processor = VectorDataProcessor()

    vector_store = VectorStore(
        settings=settings,
        dimension=dim
    )

    pipeline = IngestionPipeline(
        document_loader=document_loader,  # Initialize properly in main.py
        chunker=chunker,          # Initialize properly in main.py
        embedder=embedder,
        vector_data_processor=vector_data_processor,  # Initialize properly in main.py
        vector_store=vector_store
    )

    pipeline.run(str(file_path))

    logger.info("Pipeline execution finished")


if __name__ == "__main__":
    main()