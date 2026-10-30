"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import { api, apiJson, ReadinessResponse, Release } from "@/lib/api";
import { RenewalApprovals } from "@/components/RenewalApprovals";

export default function ApprovalsPage() {
  const [items, setItems] = useState<Release[]>([]);
  const [readinessMap, setReadinessMap] = useState<Record<number, ReadinessResponse>>({});
  const [remarks, setRemarks] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const requests = await api<Release[]>("/release-requests?status=PENDING");
      setItems(requests);

      // Load readiness evaluation for each pending request
      const rMap: Record<number, ReadinessResponse> = {};
      await Promise.all(
        requests.map(async (r) => {
          try {
            const rd = await api<ReadinessResponse>(`/release-requests/${r.id}/readiness`);
            rMap[r.id] = rd;
          } catch {}
        })
      );
      setReadinessMap(rMap);
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
      <PageTitle
        title="Release Approvals"
        subtitle="Pending requests to release or refund a deposit with integrated Release Readiness Graph evaluation."
      />

      <RenewalApprovals />

      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}

      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          No release requests are waiting for a decision.
        </div>
      ) : (
        <div className="grid gap-4">
          {items.map((r) => {
            const rd = readinessMap[r.id];
            const isReady = rd?.is_ready_for_decision;

            return (
              <article key={r.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-slate-900">
                        Request #{r.id} for{" "}
                        <Link href={`/deposits/${r.deposit_id}`} className="text-blue-700 hover:underline">
                          deposit #{r.deposit_id}
                        </Link>
                      </p>
                      {rd && (
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                            rd.overall_status === "READY_FOR_APPROVAL"
                              ? "bg-emerald-100 text-emerald-800"
                              : rd.overall_status === "BLOCKED"
                              ? "bg-red-100 text-red-800"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          Readiness: {rd.overall_status.replace(/_/g, " ")} ({rd.completion_percentage}%)
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-slate-600">
                      Requested by {r.requested_by} · status before request: {r.status_before.replace(/_/g, " ").toLowerCase()}
                    </p>
                  </div>

                  <Link
                    href={`/deposits/${r.deposit_id}#readiness`}
                    className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Inspect Readiness Graph →
                  </Link>
                </div>

                {/* Inline Blockers Notice */}
                {rd && rd.blocking_reasons.length > 0 && (
                  <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900">
                    <div className="flex items-center gap-1.5 font-bold text-red-950">
                      <svg className="h-4 w-4 shrink-0 text-red-600" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                      <span>Unmet Mandatory Release Prerequisites:</span>
                    </div>
                    <ul className="mt-1 list-inside list-disc space-y-0.5">
                      {rd.blocking_reasons.map((b, idx) => (
                        <li key={idx}>{b}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <textarea
                  className="mt-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  rows={2}
                  placeholder="Approving Authority Remarks..."
                  value={remarks[r.id] ?? ""}
                  onChange={(e) => setRemarks((m) => ({ ...m, [r.id]: e.target.value }))}
                />

                <div className="mt-3 flex items-center justify-between">
                  <div className="flex gap-2">
                    <button
                      disabled={busyId === r.id}
                      onClick={() => decide(r.id, true)}
                      className={`rounded-lg px-4 py-2 text-sm font-medium text-white shadow-xs disabled:opacity-60 ${
                        isReady
                          ? "bg-emerald-600 hover:bg-emerald-700"
                          : "bg-amber-600 hover:bg-amber-700"
                      }`}
                    >
                      {isReady ? "Approve Release" : "Approve (With Blocker Override)"}
                    </button>
                    <button
                      disabled={busyId === r.id}
                      onClick={() => decide(r.id, false)}
                      className="rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                    >
                      Reject Request
                    </button>
                  </div>

                  {!isReady && (
                    <span className="text-xs text-amber-700 font-medium">
                      Notice: Release readiness is currently {rd?.overall_status || "PENDING"}
                    </span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </Shell>
  );
}
