export const MAIN_CONTENT_ID = "main-content";

/** First focusable element on every page (GIGW / WCAG 2.4.1 Bypass Blocks). */
export function SkipLink() {
  return (
    <a
      href={`#${MAIN_CONTENT_ID}`}
      className="sr-only bg-surface px-4 py-2 font-semibold text-brand focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
    >
      Skip to main content
    </a>
  );
}
