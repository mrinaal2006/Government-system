import { useState } from "react";
import { NavLink } from "react-router";

import { cn } from "@/design-system";

import { NAV_GROUPS } from "./navigation";

export function Sidebar() {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-line bg-surface md:w-64 md:shrink-0 md:border-r md:border-b-0">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 font-semibold text-brand md:hidden"
        aria-expanded={open}
        aria-controls="primary-navigation"
        onClick={() => setOpen((v) => !v)}
      >
        Menu
        <span aria-hidden="true">{open ? "▲" : "▼"}</span>
      </button>
      <nav
        id="primary-navigation"
        aria-label="Main navigation"
        className={cn("px-2 pb-4 md:block md:pt-4", open ? "block" : "hidden")}
      >
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            <h2 className="m-0 px-2 pb-1 text-xs font-semibold tracking-wider text-ink-muted uppercase">{group.label}</h2>
            <ul className="m-0 list-none p-0">
              {group.items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center justify-between gap-2 border-l-4 px-2 py-1.5 text-sm no-underline",
                        isActive
                          ? "border-brand bg-brand-soft font-semibold text-brand"
                          : "border-transparent text-ink hover:bg-surface-muted",
                      )
                    }
                  >
                    <span>{item.label}</span>
                    {item.phase ? (
                      <span className="shrink-0 text-xs whitespace-nowrap text-ink-muted">
                        <span className="sr-only">(not yet available, </span>Phase {item.phase}
                        <span className="sr-only">)</span>
                      </span>
                    ) : null}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  );
}
