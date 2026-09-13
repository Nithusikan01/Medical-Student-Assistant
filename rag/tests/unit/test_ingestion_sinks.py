from unittest.mock import Mock

from rag.ingestion.bm25.corpus_builder import BM25CorpusBuilder
from rag.ingestion.pipeline import IngestionPipeline
from rag.ingestion.sinks import ChunkSink
from tests.unit.helpers import make_chunk


class RecordingSink:
    def __init__(self):
        self.batches = []
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        return False

    def add_batch(self, chunks):
        self.batches.append(list(chunks))


def build_pipeline(**kwargs):
    loader = Mock()
    chunker = Mock()
    embedder = Mock()
    processor = Mock()
    vector_store = Mock()

    document = Mock()
    document.filename = "cv.pdf"
    document.document_id = "doc-1"
    document.pages = [Mock()]
    loader.load.return_value = document

    chunks = [make_chunk(index=0, document_id="doc-1")]
    chunker.chunk_batches.return_value = iter([chunks])
    embedder.embed_batch.return_value = ["embedded"]
    processor.prepare.return_value = ["record"]

    pipeline = IngestionPipeline(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        processor=processor,
        vector_store=vector_store,
        batch_size=5,
        **kwargs,
    )

    return pipeline, chunks


def test_bm25_corpus_builder_satisfies_chunk_sink(tmp_path):
    builder = BM25CorpusBuilder(tmp_path / "corpus.json")

    assert isinstance(builder, ChunkSink)


def test_pipeline_passes_chunks_to_sink():
    sink = RecordingSink()
    pipeline, chunks = build_pipeline(chunk_sink=sink)

    pipeline.ingest("cv.pdf")

    assert sink.entered
    assert sink.exited
    assert sink.batches == [chunks]


def test_pipeline_prefers_sink_over_corpus_path(tmp_path):
    sink = RecordingSink()
    corpus = tmp_path / "corpus.json"
    pipeline, _ = build_pipeline(chunk_sink=sink, bm25_corpus_path=corpus)

    pipeline.ingest("cv.pdf")

    assert sink.batches
    assert not corpus.exists()


def test_pipeline_forwards_supplied_document_id():
    pipeline, _ = build_pipeline()

    pipeline.ingest("cv.pdf", document_id="chosen-id")

    pipeline.loader.load.assert_called_once_with(
        "cv.pdf",
        document_id="chosen-id",
        filename=None,
    )


def test_pipeline_forwards_the_original_filename():
    pipeline, _ = build_pipeline()

    pipeline.ingest("9f2c.pdf", filename="lecture-notes.pdf")

    pipeline.loader.load.assert_called_once_with(
        "9f2c.pdf",
        document_id=None,
        filename="lecture-notes.pdf",
    )


def test_ingest_summary_reports_document_id_and_pages():
    pipeline, _ = build_pipeline()

    summary = pipeline.ingest("cv.pdf")

    assert summary["document_id"] == "doc-1"
    assert summary["pages"] == 1
    assert summary["chunks"] == 1
