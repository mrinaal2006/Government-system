import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type TextScale = "normal" | "large" | "larger";
export type Contrast = "standard" | "high";

interface Preferences {
  textScale: TextScale;
  contrast: Contrast;
  setTextScale: (value: TextScale) => void;
  setContrast: (value: Contrast) => void;
}

const STORAGE_KEY = "dgimews.a11y";
const PreferencesContext = createContext<Preferences | null>(null);

function load(): { textScale: TextScale; contrast: Contrast } {
  const fallback = { textScale: "normal" as TextScale, contrast: "standard" as Contrast };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<{ textScale: string; contrast: string }>;
    return {
      textScale: ["normal", "large", "larger"].includes(parsed.textScale ?? "") ? (parsed.textScale as TextScale) : "normal",
      contrast: parsed.contrast === "high" ? "high" : "standard",
    };
  } catch {
    return fallback; // storage blocked or corrupt: use defaults
  }
}

/**
 * Viewer display preferences (GIGW: text resize and contrast). Stored only in this
 * browser; contains no personal data.
 */
export function AccessibilityPreferencesProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(load);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.textScale = state.textScale;
    root.dataset.contrast = state.contrast;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* storage unavailable: preference applies for this page view only */
    }
  }, [state]);

  const setTextScale = useCallback((textScale: TextScale) => setState((s) => ({ ...s, textScale })), []);
  const setContrast = useCallback((contrast: Contrast) => setState((s) => ({ ...s, contrast })), []);
  const value = useMemo(() => ({ ...state, setTextScale, setContrast }), [state, setTextScale, setContrast]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function useAccessibilityPreferences(): Preferences {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("useAccessibilityPreferences must be used inside AccessibilityPreferencesProvider");
  return ctx;
}
