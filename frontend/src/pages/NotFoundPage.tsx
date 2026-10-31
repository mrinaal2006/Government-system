import { Link } from "react-router";

import { EmptyState, PageHeader } from "@/design-system";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState title="The page you requested does not exist" action={<Link to="/">Go to the command dashboard</Link>}>
        Check the address, or use the main navigation.
      </EmptyState>
    </>
  );
}
