import { Link } from "react-router";

import { useSystemInfo } from "@/lib/api/system";

export function Footer() {
  const { data } = useSystemInfo();
  return (
    <footer className="on-dark mt-8 border-t-4 border-accent bg-brand-deep text-on-brand">
      <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-3 px-4 py-4 text-sm">
        <ul className="m-0 flex list-none flex-wrap gap-4 p-0">
          <li>
            <Link to="/accessibility" className="text-on-brand">
              Accessibility statement
            </Link>
          </li>
          <li>
            <Link to="/system-status" className="text-on-brand">
              System status
            </Link>
          </li>
        </ul>
        <p className="m-0 text-on-brand-muted">
          {data ? `${data.application} version ${data.version}` : "DG-IMEWS"}. For official use by authorised personnel only.
        </p>
      </div>
    </footer>
  );
}
