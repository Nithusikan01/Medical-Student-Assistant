import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "msa-sidebar-collapsed";

/** Must match the breakpoint in index.css where the sidebar becomes a drawer. */
const NARROW_QUERY = "(max-width: 900px)";

function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    // Private windows and blocked site data throw on access.
    return false;
  }
}

function storeCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(collapsed));
  } catch {
    // A preference that cannot be stored still applies for this visit.
  }
}

function matchesNarrow(): boolean {
  return typeof window !== "undefined" && window.matchMedia(NARROW_QUERY).matches;
}

/**
 * The chat sidebar's two states, one per layout.
 *
 * Wide screens dock the sidebar and let it be collapsed; that choice is a
 * preference and is remembered. Narrow screens hide it behind a drawer; that
 * is a moment, not a preference, so it always starts closed. Keeping the two
 * apart means opening the drawer on a phone never collapses the sidebar on
 * the laptop, and the one hamburger button does whichever the layout needs.
 */
export function useSidebar() {
  const [narrow, setNarrow] = useState(matchesNarrow);
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const query = window.matchMedia(NARROW_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      setNarrow(event.matches);
      // A drawer left open while the window widens would reappear, stale,
      // the next time it narrows.
      setDrawerOpen(false);
    };

    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    if (narrow) {
      setDrawerOpen((open) => !open);
      return;
    }

    setCollapsed((current) => {
      storeCollapsed(!current);
      return !current;
    });
  }, [narrow]);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && drawerOpen) {
        setDrawerOpen(false);
      }

      if (
        (event.ctrlKey || event.metaKey) &&
        !event.altKey &&
        !event.shiftKey &&
        event.key.toLowerCase() === "b"
      ) {
        event.preventDefault();
        toggle();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen, toggle]);

  return {
    narrow,
    /** Docked sidebar hidden. Only meaningful on wide screens. */
    collapsed: !narrow && collapsed,
    /** Drawer showing. Only ever true on narrow screens. */
    drawerOpen: narrow && drawerOpen,
    toggle,
    closeDrawer,
  };
}
