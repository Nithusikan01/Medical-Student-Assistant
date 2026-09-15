import { useEffect, useRef, useState } from "react";

import type { GenerationModelInfo } from "../types";
import { ChevronDown } from "./Icons";

interface ModelSelectProps {
  models: GenerationModelInfo[];
  selectedModel: string | null;
  onModelChange: (id: string) => void;
}

export function ModelSelect({
  models,
  selectedModel,
  onModelChange,
}: ModelSelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const disabled = models.length === 0;

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const currentLabel =
    models.find((model) => model.id === selectedModel)?.label ?? "Default";

  return (
    <div className="model-select" ref={containerRef}>
      <span className="model-select-label">Model</span>
      <button
        type="button"
        className="model-select-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {currentLabel}
        <ChevronDown />
      </button>

      {open && (
        <ul className="model-select-menu" role="listbox">
          {models.map((model) => (
            <li key={model.id}>
              <button
                type="button"
                role="option"
                aria-selected={model.id === selectedModel}
                className="model-select-option"
                data-selected={model.id === selectedModel}
                onClick={() => {
                  onModelChange(model.id);
                  setOpen(false);
                }}
              >
                {model.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
