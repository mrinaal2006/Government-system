import { Link } from "react-router";

import { EmptyState, PageHeader } from "@/design-system";
import type { ModuleDefinition } from "@/layout/navigation";

/**
 * Honest placeholder for modules scheduled in later phases. It shows no sample
 * figures or records: nothing appears until the backend module exists.
 */
export function ModulePlaceholderPage({ module }: { module: ModuleDefinition }) {
  return (
    <>
      <PageHeader title={module.label} description={module.summary} />
      <EmptyState
        title={`${module.label} is not yet available`}
        action={<Link to="/system-status">View system status</Link>}
      >
        <p className="m-0">
          This module is scheduled for development phase {module.phase}. No data is displayed until it is implemented and
          connected to live records.
        </p>
      </EmptyState>
    </>
  );
}
