import { useTheme } from "../theme/useTheme";
import { Moon, Sun } from "./Icons";

interface ThemeToggleProps {
  /** Icon-only, for tight spots like the chat header. */
  compact?: boolean;
}

export function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className={compact ? "theme-toggle theme-toggle-compact" : "theme-toggle"}
      role="group"
      aria-label="Colour theme"
    >
      <button
        type="button"
        aria-pressed={theme === "light"}
        title="Light theme"
        onClick={() => setTheme("light")}
      >
        <Sun />
        {!compact && "Light"}
      </button>

      <button
        type="button"
        aria-pressed={theme === "dark"}
        title="Dark theme"
        onClick={() => setTheme("dark")}
      >
        <Moon />
        {!compact && "Dark"}
      </button>
    </div>
  );
}
