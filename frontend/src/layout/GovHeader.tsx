import { Link } from "react-router";

import { useSystemInfo } from "@/lib/api/system";

import { AccessibilityControls } from "./AccessibilityControls";

const APP_TITLE = "District Grievance Intelligence, Monitoring & Early Warning System";

/**
 * Official header. The district and state names come from deployment
 * configuration (/api/v1/system/info) and are never hard-coded. National or state
 * emblems are intentionally not bundled: their use is governed by law and must
 * be supplied and approved by the district administration.
 */
export function GovHeader() {
  const { data, isError } = useSystemInfo();
  const d = data?.deployment;
  const government = d?.state_name ? `Government of ${d.state_name}` : "State government not configured";
  const nonProduction = data && data.environment !== "production";

  return (
    <header className="on-dark">
      <div className="bg-brand-deep text-on-brand">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-2 px-4 py-1.5">
          <p className="m-0 text-sm">
            <span>{government}</span>
            {d?.state_name_local ? (
              <span lang="hi" className="ml-2 text-on-brand-muted">
                {d.state_name_local}
              </span>
            ) : null}
          </p>
          <AccessibilityControls />
        </div>
      </div>

      <div className="border-b-4 border-accent bg-brand text-on-brand">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link to="/" className="text-on-brand no-underline">
            <p className="m-0 text-sm font-semibold tracking-wide text-on-brand-muted uppercase">
              {d?.district_name ? `District Administration, ${d.district_name}` : "District Administration"}
              {d?.district_name_local ? (
                <span lang="hi" className="ml-2 normal-case">
                  {d.district_name_local}
                </span>
              ) : null}
            </p>
            <p className="m-0 text-lg leading-snug font-semibold md:text-xl">{APP_TITLE}</p>
          </Link>
          <div className="flex flex-col items-end gap-1 text-sm">
            {nonProduction ? (
              <span className="rounded-sm border border-on-brand bg-brand-deep px-2 py-0.5 font-semibold uppercase">
                {data.environment} environment, not for official use
              </span>
            ) : null}
            {data && !d?.district_name ? (
              <span className="text-on-brand-muted">Deployment identity not configured</span>
            ) : null}
            {isError ? <span className="text-on-brand-muted">Deployment details unavailable</span> : null}
          </div>
        </div>
      </div>
    </header>
  );
}
