"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import { api, dateTime, Notif } from "@/lib/api";

const KIND_LABELS: Record<string, string> = {
  REMINDER_60: "60-day reminder",
  REMINDER_30: "30-day reminder",
  REMINDER_7: "7-day reminder",
  OVERDUE: "Overdue escalation",
};

export default function NotificationsPage() {
  const [items, setItems] = useState<Notif[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api<Notif[]>("/notifications"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load notifications");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function markRead(id: number) {
    try {
      await api(`/notifications/${id}/read`, { method: "PATCH" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update notification");
    }
  }

  return (
    <Shell>
      <PageTitle title="Notifications" subtitle="Maturity reminders and escalations for your role." />

      {error && <Notice kind="error">{error}</Notice>}

      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          No notifications yet. Reminders appear when the daily maturity check runs.
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((n) => (
            <li
              key={n.id}
              className={`flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4 text-sm ${
                n.is_read ? "border-slate-200 bg-white" : "border-indigo-200 bg-indigo-50"
              }`}
            >
              <div>
                <p className="font-medium">
                  {KIND_LABELS[n.kind] ?? n.kind}{" "}
                  {!n.is_read && <span className="ml-2 rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white">New</span>}
                </p>
                <p className="mt-1 text-slate-700">{n.message}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {dateTime(n.created_at)} ·{" "}
                  <Link href={`/deposits/${n.deposit_id}`} className="text-indigo-700 hover:underline">
                    Open deposit
                  </Link>
                </p>
              </div>
              {!n.is_read && (
                <button onClick={() => markRead(n.id)} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50">
                  Mark as read
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}
