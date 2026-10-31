import { useAccessibilityPreferences, type TextScale } from "@/lib/a11y/preferences";
import { cn } from "@/design-system";

const SCALES: Array<{ value: TextScale; label: string; name: string }> = [
  { value: "normal", label: "A", name: "normal text size" },
  { value: "large", label: "A+", name: "large text size" },
  { value: "larger", label: "A++", name: "larger text size" },
];

const toggle =
  "min-h-7 min-w-8 rounded-sm border border-on-brand-muted px-2 text-sm font-semibold text-on-brand " +
  "aria-pressed:bg-on-brand aria-pressed:text-brand-deep";

export function AccessibilityControls() {
  const { textScale, setTextScale, contrast, setContrast } = useAccessibilityPreferences();
  return (
    <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Accessibility controls">
      <div className="flex items-center gap-1" role="group" aria-label="Text size">
        <span className="mr-1 text-sm text-on-brand-muted" aria-hidden="true">
          Text size
        </span>
        {SCALES.map((s) => (
          <button
            key={s.value}
            type="button"
            aria-pressed={textScale === s.value}
            onClick={() => setTextScale(s.value)}
            className={toggle}
          >
            {/* Visible text leads the accessible name (WCAG 2.5.3 Label in Name). */}
            {s.label}
            <span className="sr-only"> ({s.name})</span>
          </button>
        ))}
      </div>
      <button
        type="button"
        aria-pressed={contrast === "high"}
        onClick={() => setContrast(contrast === "high" ? "standard" : "high")}
        className={cn(toggle, "px-3")}
      >
        High contrast
      </button>
    </div>
  );
}
