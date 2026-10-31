import { Link, useNavigate } from "react-router";

import { titleCase } from "@/lib/format";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useApi } from "@/lib/hooks";

export function UserBar() {
  const { user, state, logout } = useAuth();
  const navigate = useNavigate();
  const unread = useApi<{ unread: number }>(state === "authenticated" ? "/notifications" : null, { limit: 1 }, { refetchInterval: 60_000 });
  if (!user || state !== "authenticated") return null;
  const count = unread.data?.unread ?? 0;
  return (
    <div className="flex flex-wrap items-center justify-end gap-3 text-sm">
      <Link to="/notifications" className="font-semibold text-on-brand">
        Notifications
        {count > 0 ? (
          <span className="ml-1 rounded-sm bg-on-brand px-1.5 text-brand-deep">
            {count}
            <span className="sr-only"> unread</span>
          </span>
        ) : null}
      </Link>
      <span className="text-on-brand-muted" title={user.roles.map(titleCase).join(", ")}>
        {user.full_name}
        <span className="sr-only">, roles: {user.roles.map(titleCase).join(", ")}</span>
      </span>
      <Link to="/account/password" className="text-on-brand">
        Change password
      </Link>
      <button
        type="button"
        className="rounded-sm border border-on-brand-muted px-2 py-0.5 font-semibold text-on-brand"
        onClick={async () => {
          await logout();
          navigate("/login", { replace: true });
        }}
      >
        Sign out
      </button>
    </div>
  );
}
