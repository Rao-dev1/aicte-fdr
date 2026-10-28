"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import { api, apiJson, Release } from "@/lib/api";

export default function ApprovalsPage() {
  const [items, setItems] = useState<Release[]>([]);
  const [remarks, setRemarks] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api<Release[]>("/release-requests?status=PENDING"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load approvals");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function decide(id: number, approve: boolean) {
    setBusyId(id);
    setError(null);
    setOk(null);
    try {
      await apiJson(`/release-requests/${id}`, "PATCH", { approve, remarks: remarks[id] ?? "" });
      setOk(approve ? "Release approved." : "Release rejected. The deposit returns to its previous status.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Shell>
      <PageTitle title="Release approvals" subtitle="Pending requests to release or refund a deposit." />

      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}

      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          No release requests are waiting for a decision.
        </div>
      ) : (
        <div className="grid gap-4">
          {items.map((r) => (
            <article key={r.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-semibold">
                    Request #{r.id} for{" "}
                    <Link href={`/deposits/${r.deposit_id}`} className="text-blue-700 hover:underline">
                      deposit #{r.deposit_id}
                    </Link>
                  </p>
                  <p className="text-sm text-slate-600">
                    Requested by {r.requested_by} · status before request: {r.status_before.replace(/_/g, " ").toLowerCase()}
                  </p>
                </div>
              </div>

              <textarea
                className="mt-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                rows={2}
                placeholder="Remarks (optional)"
                value={remarks[r.id] ?? ""}
                onChange={(e) => setRemarks((m) => ({ ...m, [r.id]: e.target.value }))}
              />

              <div className="mt-3 flex gap-2">
                <button
                  disabled={busyId === r.id}
                  onClick={() => decide(r.id, true)}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                >
                  Approve
                </button>
                <button
                  disabled={busyId === r.id}
                  onClick={() => decide(r.id, false)}
                  className="rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                >
                  Reject
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </Shell>
  );
}
