import type { SourceChunk } from "../types";

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
        {sources.length} source{sources.length === 1 ? "" : "s"}
      </summary>

      <ol className="source-list">
        {sources.map((source) => (
          <li key={source.id} className="source">
            <div className="source-head">
              <span className="source-file">{source.metadata.filename}</span>

              {source.metadata.page_number !== null && (
                <span className="source-tag">p. {source.metadata.page_number}</span>
              )}

              <span className="source-tag">chunk {source.metadata.chunk_index}</span>

              {source.retrieval_method && (
                <span className="source-tag">{source.retrieval_method}</span>
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
