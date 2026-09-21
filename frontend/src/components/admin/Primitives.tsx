/**
 * Formatting shared by the admin pages.
 *
 * Pulled out when the library and the user roster became separate pages:
 * both date every row, and a copy each would drift the moment one of them
 * gained a time or a relative format.
 */

export function formatSize(bytes: number | null): string {
  if (bytes === null) {
    return "—";
  }

  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
