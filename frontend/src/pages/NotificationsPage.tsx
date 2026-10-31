import { Link } from "react-router";

import { Button, EmptyState, ErrorState, LoadingState, PageHeader } from "@/design-system";
import { formatShortIST, titleCase } from "@/lib/format";
import { useApi, useApiMutation } from "@/lib/hooks";

interface N { id: string; category: string; title: string; body: string | null; link: string | null; created_at: string; read_at: string | null }

export function NotificationsPage() {
  const list = useApi<{ items: N[]; total: number; unread: number }>("/notifications", { limit: 100 });
  const readAll = useApiMutation<Record<string, never>>("POST", "/notifications/read-all", ["/notifications"]);
  const readOne = useApiMutation<{ id: string }>("POST", (b) => `/notifications/${b.id}/read`, ["/notifications"]);
  return (
    <>
      <PageHeader title="Notifications" description={list.data ? `${list.data.unread} unread` : undefined}
        actions={list.data?.unread ? <Button variant="secondary" onClick={() => readAll.mutate({})}>Mark all as read</Button> : null} />
      {list.isLoading ? <LoadingState /> : list.isError ? <ErrorState message="Notifications could not be loaded." /> : !list.data?.items.length ? (
        <EmptyState title="No notifications" />
      ) : (
        <ul className="m-0 list-none p-0">
          {list.data.items.map((n) => (
            <li key={n.id} className={`mb-2 rounded-sm border border-line p-3 ${n.read_at ? "bg-surface" : "border-l-4 border-l-brand bg-brand-soft"}`}>
              <p className="m-0 font-semibold">{n.read_at ? null : <span className="sr-only">Unread: </span>}{n.title}</p>
              {n.body ? <p className="m-0 text-sm">{n.body}</p> : null}
              <p className="m-0 mt-1 flex flex-wrap gap-3 text-sm text-ink-muted">
                <span>{titleCase(n.category)}, {formatShortIST(n.created_at)}</span>
                {n.link ? <Link to={n.link} onClick={() => !n.read_at && readOne.mutate({ id: n.id })}>Open</Link> : null}
                {!n.read_at ? <button type="button" className="text-link underline" onClick={() => readOne.mutate({ id: n.id })}>Mark as read</button> : null}
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
