import type { SourceChunk, SourceMetadata } from "../types";
import { ChevronDown, Document } from "./Icons";

function pageLabel({ page_number, end_page_number }: SourceMetadata) {
  if (page_number === null) {
    return null;
  }

  if (end_page_number == null || end_page_number === page_number) {
    return `p. ${page_number}`;
  }

  return `pp. ${page_number}–${end_page_number}`;
}

interface SourceListProps {
  sources: SourceChunk[];
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return null;
  }

  return (
    <details className="sources">
      <summary>
        <ChevronDown />
        {sources.length} source{sources.length === 1 ? "" : "s"}
      </summary>

      <ol className="source-list">
        {sources.map((source) => (
          <li key={source.id} className="source">
            <div className="source-head">
              <Document size={13} />
              {source.metadata.url ? (
                <a
                  className="source-file"
                  href={source.metadata.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {source.metadata.filename}
                </a>
              ) : (
                <span className="source-file">{source.metadata.filename}</span>
              )}

              {pageLabel(source.metadata) !== null && (
                <span className="chip">{pageLabel(source.metadata)}</span>
              )}

              {!source.metadata.url && (
                <span className="chip">chunk {source.metadata.chunk_index}</span>
              )}

              {source.retrieval_method && (
                <span className="chip chip-accent">
                  {source.retrieval_method}
                </span>
              )}

              <span className="source-score">{source.score.toFixed(3)}</span>
            </div>

            <p className="source-text">{source.preview ?? source.text}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}
