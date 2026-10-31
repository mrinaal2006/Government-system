import { PageHeader, Panel } from "@/design-system";

/**
 * Factual description of implemented accessibility features. It deliberately makes
 * no conformance claim: GIGW 3.0 / WCAG 2.1 AA conformance requires an independent
 * audit, which has not been carried out.
 */
export function AccessibilityPage() {
  return (
    <>
      <PageHeader
        title="Accessibility statement"
        description="This application is being designed against GIGW 3.0 and WCAG 2.1 Level AA as its baseline."
      />
      <div className="grid grid-cols-1 gap-5">
        <Panel title="Features available">
          <ul className="m-0 list-disc pl-5">
            <li>A “Skip to main content” link as the first element on every page.</li>
            <li>Text size controls (A, A+, A++) and a high-contrast mode in the header, remembered in this browser.</li>
            <li>Full keyboard operation with a visible focus indicator.</li>
            <li>Labelled form fields with hints and error messages announced to screen readers.</li>
            <li>Status shown as text, never by colour alone.</li>
            <li>Data tables with captions and column headers.</li>
            <li>Layouts that adapt to small screens and to browser zoom up to 200%.</li>
          </ul>
        </Panel>
        <Panel title="Current limitations">
          <ul className="m-0 list-disc pl-5">
            <li>The interface is available in English only; Hindi and other official languages are planned.</li>
            <li>No independent accessibility audit has been carried out yet, so no conformance is claimed.</li>
          </ul>
        </Panel>
      </div>
    </>
  );
}
