import { BookMark } from "./Icons";

interface AuthPanelProps {
  quote: string;
  author: string;
  credit: string;
}

export function AuthPanel({ quote, author, credit }: AuthPanelProps) {
  return (
    <aside className="auth-panel">
      <svg className="auth-panel-trace" aria-hidden="true" focusable="false">
        <defs>
          <pattern
            id="auth-ecg"
            width="210"
            height="160"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 0 96 L 56 96 L 68 60 L 86 150 L 104 8 L 122 120 L 140 96 L 210 96"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#auth-ecg)" />
      </svg>

      <span className="wordmark">
        <BookMark size={22} />
        Anamnesis
      </span>

      <blockquote className="auth-quote">
        <p>{quote}</p>
        <footer>
          <span className="auth-quote-dash" aria-hidden="true" />
          <span className="auth-quote-name">{author}</span>
          <span className="auth-quote-credit">{credit}</span>
        </footer>
      </blockquote>

      <p className="auth-panel-facts">
        <span>One shared class library</span>
        <span className="auth-fact-dot" aria-hidden="true" />
        <span>Every answer cites its pages</span>
        <span className="auth-fact-dot" aria-hidden="true" />
        <span>Your chats stay private</span>
      </p>
    </aside>
  );
}
