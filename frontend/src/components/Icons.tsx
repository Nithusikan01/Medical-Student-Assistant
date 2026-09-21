interface IconProps {
  size?: number;
  strokeWidth?: number;
}

function base(size: number, strokeWidth: number) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

export function BookMark({ size = 20, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2.5H4Z" />
      <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H16a3 3 0 0 0-3 3v13a2.5 2.5 0 0 1 2.5-2.5H20Z" />
    </svg>
  );
}

export function Sun({ size = 15, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function Moon({ size = 15, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
    </svg>
  );
}

export function ArrowRight({ size = 16, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  );
}

export function ArrowLeft({ size = 15, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </svg>
  );
}

export function Plus({ size = 15, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function Pencil({ size = 14, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

export function Trash({ size = 14, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
    </svg>
  );
}

export function Document({ size = 15, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

export function Users({ size = 15, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

export function Activity({ size = 15, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}

export function SignOut({ size = 15, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

export function Upload({ size = 15, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M7 9l5-5 5 5M12 4v12" />
    </svg>
  );
}

export function Send({ size = 15, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M4 12l16-8-6 16-2.5-6.5L4 12Z" />
    </svg>
  );
}

export function ChevronDown({ size = 14, strokeWidth = 1.9 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function Spinner({ size = 16, strokeWidth = 2.4 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)} className="spin">
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}

export function ThumbUp({ size = 14, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M7 10v10H4.5A1.5 1.5 0 0 1 3 18.5v-7A1.5 1.5 0 0 1 4.5 10Z" />
      <path d="M7 10.5 11 3a2.2 2.2 0 0 1 2.2 2.6L12.5 9h5.2A2.3 2.3 0 0 1 20 11.7l-1.3 6A2.3 2.3 0 0 1 16.4 20H7Z" />
    </svg>
  );
}

export function ThumbDown({ size = 14, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg {...base(size, strokeWidth)}>
      <path d="M7 14V4H4.5A1.5 1.5 0 0 0 3 5.5v7A1.5 1.5 0 0 0 4.5 14Z" />
      <path d="M7 13.5 11 21a2.2 2.2 0 0 0 2.2-2.6L12.5 15h5.2A2.3 2.3 0 0 0 20 12.3l-1.3-6A2.3 2.3 0 0 0 16.4 4H7Z" />
    </svg>
  );
}
