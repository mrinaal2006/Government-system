import type { ReactNode } from "react";

import { GovHeader } from "@/layout/GovHeader";
import { MAIN_CONTENT_ID, SkipLink } from "@/layout/SkipLink";

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <GovHeader />
      <main id={MAIN_CONTENT_ID} tabIndex={-1} className="mx-auto w-full max-w-md flex-1 px-4 py-10 focus:outline-none">
        <div className="rounded-sm border border-line bg-surface p-6">
          <h1 className="m-0 mb-4 text-xl font-semibold text-brand">{title}</h1>
          {children}
        </div>
        <p className="mt-4 text-center text-sm text-ink-muted">For authorised officials only. All activity is recorded.</p>
      </main>
    </div>
  );
}
