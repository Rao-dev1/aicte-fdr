"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Notice } from "@/components/Shell";
import { api, apiJson, dateOnly, money } from "@/lib/api";

export type RenewalRequest = {
  id: number;
  old_deposit_id: number;
  status: string;
  new_reference_no: string;
  new_bank_name: string;
  new_amount: string;
  new_issue_date: string;
  new_maturity_date: string;
  requested_by: string;
};

export function RenewalApprovals() {
  const [items, setItems] = useState<RenewalRequest[]>([]);
  const [remarks, setRemarks] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api<RenewalRequest[]>("/renewal-requests?status=PENDING"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load renewals");
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
      await apiJson(`/renewal-requests/${id}`, "PATCH", { approve, remarks: remarks[id] ?? "" });
      setOk(approve ? "Renewal approved. The new FDR is now on the portal." : "Renewal rejected. The original FDR is unchanged.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="mb-8 space-y-4">
      <h2 className="text-lg font-semibold text-[#0f2d52]">Renewal approvals</h2>
      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">No renewals are waiting for a decision.</p>
      ) : (
        items.map((r) => (
          <article key={r.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="font-semibold">
              Renewal #{r.id} of{" "}
              <Link href={`/deposits/${r.old_deposit_id}`} className="text-blue-700 hover:underline">
                deposit #{r.old_deposit_id}
              </Link>
            </p>
            <p className="mt-1 text-sm text-slate-600">
              New FDR {r.new_reference_no} · {r.new_bank_name} · {money(r.new_amount)} · {dateOnly(r.new_issue_date)} to {dateOnly(r.new_maturity_date)}
            </p>
            <p className="text-xs text-slate-500">Requested by {r.requested_by}</p>
            <textarea
              className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
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
                Approve renewal
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
        ))
      )}
    </section>
  );
}
