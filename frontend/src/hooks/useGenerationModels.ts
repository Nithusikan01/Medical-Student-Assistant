import { useCallback, useEffect, useState } from "react";

import { getGenerationModels } from "../api/conversations";
import type { GenerationModelInfo } from "../types";

const STORAGE_KEY = "msa-generation-model";

function readStoredModel(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private windows and blocked site data throw on access.
    return null;
  }
}

function storeModel(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // A preference that cannot be stored still applies for this visit.
  }
}

export function useGenerationModels() {
  const [models, setModels] = useState<GenerationModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    getGenerationModels()
      .then((response) => {
        if (cancelled) {
          return;
        }

        setModels(response.models);

        const stored = readStoredModel();
        const isStoredStillOffered = response.models.some(
          (model) => model.id === stored,
        );

        setSelectedModel(isStoredStillOffered ? stored : response.default);
      })
      .catch(() => {
        // The composer still works with the server's default model when the
        // list can't be fetched - just without a picker.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const selectModel = useCallback((id: string) => {
    setSelectedModel(id);
    storeModel(id);
  }, []);

  return { models, selectedModel, selectModel };
}
