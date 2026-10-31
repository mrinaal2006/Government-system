import { useEffect, useRef } from "react";
import { Outlet, useLocation, useMatches } from "react-router";

import { Breadcrumbs, type Crumb } from "@/design-system";

import { Footer } from "./Footer";
import { GovHeader } from "./GovHeader";
import { Sidebar } from "./Sidebar";
import { MAIN_CONTENT_ID, SkipLink } from "./SkipLink";

export interface RouteHandle {
  title: string;
  crumbs?: Crumb[];
}

const APP_SHORT = "DG-IMEWS";

function useRouteHandle(): RouteHandle | undefined {
  const matches = useMatches();
  for (let i = matches.length - 1; i >= 0; i -= 1) {
    const handle = matches[i]?.handle as RouteHandle | undefined;
    if (handle?.title) return handle;
  }
  return undefined;
}

export function AppShell() {
  const handle = useRouteHandle();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const firstRender = useRef(true);

  // On client-side navigation: update the document title and move focus to the
  // main region so screen-reader and keyboard users start at the new content.
  useEffect(() => {
    document.title = handle ? `${handle.title} | ${APP_SHORT}` : APP_SHORT;
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.focus();
  }, [location.pathname, handle]);

  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <GovHeader />
      <div className="mx-auto flex w-full max-w-screen-2xl flex-1 flex-col md:flex-row">
        <Sidebar />
        <main id={MAIN_CONTENT_ID} ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 px-4 py-5 focus:outline-none md:px-6">
          <Breadcrumbs items={handle?.crumbs ?? []} />
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  );
}
