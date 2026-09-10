"""
Import a pre-registry ingest into the document registry.

Documents ingested before the registry existed have vectors in Pinecone and
rows in storage/bm25_corpus.json, but nothing in the database - so they are
invisible to the admin UI and cannot be deleted. This reads that corpus file
and creates the matching documents and document_chunks rows.

Safe to re-run: documents already present are skipped.

Run from the backend directory:

    python scripts/migrate_bm25_corpus.py            # report only
    python scripts/migrate_bm25_corpus.py --apply    # write the rows
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "backend" / "src"), str(_ROOT / "rag" / "src")]

load_dotenv(_ROOT / "backend" / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        default="storage/bm25_corpus.json",
        help="Path to the legacy BM25 corpus file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the rows. Without this the script only reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from api_app.db.models import STATUS_READY, Document, DocumentChunkRecord
    from api_app.db.session import get_session_factory
    from api_app.wiring.rag_factory import load_bm25_corpus

    corpus_path = Path(args.corpus)

    if not corpus_path.exists():
        print(f"No corpus file at {corpus_path}; nothing to migrate.")
        return 0

    chunks = load_bm25_corpus(corpus_path)

    if not chunks:
        print("Corpus file is empty; nothing to migrate.")
        return 0

    by_document: dict[str, list] = defaultdict(list)

    for chunk in chunks:
        by_document[chunk.metadata.document_id].append(chunk)

    print(f"Found {len(chunks)} chunks across {len(by_document)} document(s).")

    session_factory = get_session_factory()
    created = 0

    with session_factory() as session:
        for document_id, document_chunks in by_document.items():
            try:
                parsed_id = uuid.UUID(document_id)
            except ValueError:
                print(f"  skip {document_id!r}: not a uuid")
                continue

            if session.get(Document, parsed_id) is not None:
                print(f"  skip {document_id}: already registered")
                continue

            filename = document_chunks[0].metadata.filename
            pages = {
                chunk.metadata.page_number
                for chunk in document_chunks
                if chunk.metadata.page_number is not None
            }

            print(
                f"  import {filename} ({document_id}): "
                f"{len(document_chunks)} chunks"
            )

            if not args.apply:
                continue

            session.add(
                Document(
                    id=parsed_id,
                    filename=filename,
                    status=STATUS_READY,
                    page_count=len(pages) or None,
                    chunk_count=len(document_chunks),
                )
            )
            session.flush()

            session.add_all(
                [
                    DocumentChunkRecord(
                        id=chunk.id,
                        document_id=parsed_id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        page_number=chunk.metadata.page_number,
                        section_title=chunk.metadata.section_title,
                        heading_level=chunk.metadata.heading_level,
                        start_char=chunk.metadata.start_char,
                        end_char=chunk.metadata.end_char,
                        chunk_size=chunk.metadata.chunk_size,
                        overlap_size=chunk.metadata.overlap_size,
                        language=chunk.metadata.language,
                    )
                    for chunk in document_chunks
                ]
            )
            created += 1

        if args.apply:
            session.commit()

    if args.apply:
        print(f"\nImported {created} document(s).")
        print("Restart the API (or ingest/delete anything) to refresh BM25.")
    else:
        print("\nDry run. Re-run with --apply to write these rows.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
