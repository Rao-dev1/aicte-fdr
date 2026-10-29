"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Shell, Notice } from "@/components/Shell";
import { api, apiJson, getSession, IntegrityFinding, IntegrityFindingsResponse, IntegrityNetworkResponse } from "@/lib/api";

export default function IntegrityPage() {
  const [tab, setTab] = useState<"findings" | "network">("findings");
  const [findings, setFindings] = useState<IntegrityFinding[]>([]);
  const [summary, setSummary] = useState<IntegrityFindingsResponse["summary"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<string>("");

  // Selected finding for detailed review modal
  const [activeFinding, setActiveFinding] = useState<IntegrityFinding | null>(null);
  const [reviewAction, setReviewAction] = useState<string>("STATUS_CHANGE");
  const [newStatus, setNewStatus] = useState<string>("UNDER_REVIEW");
  const [reviewNotes, setReviewNotes] = useState<string>("");
  const [assignee, setAssignee] = useState<string>("");
  const [actionLoading, setActionLoading] = useState(false);

  // Network graph state
  const [networkData, setNetworkData] = useState<IntegrityNetworkResponse | null>(null);
  const [networkLoading, setNetworkLoading] = useState(false);

  const session = getSession();
  const isOfficerOrAdmin = session?.role === "REGULATOR_OFFICER" || session?.role === "ADMIN" || session?.role === "APPROVING_AUTHORITY";

  async function loadFindings() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (severityFilter) params.set("severity", severityFilter);
      params.set("limit", "100");

      const res = await api<IntegrityFindingsResponse>(`/integrity/findings?${params.toString()}`);
      setFindings(res.items);
      setSummary(res.summary);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load integrity findings");
    } finally {
      setLoading(false);
    }
  }

  async function loadNetwork() {
    setNetworkLoading(true);
    try {
      const res = await api<IntegrityNetworkResponse>("/integrity/network");
      setNetworkData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load network graph");
    } finally {
      setNetworkLoading(false);
    }
  }

  useEffect(() => {
    loadFindings();
  }, [statusFilter, severityFilter]);

  useEffect(() => {
    if (tab === "network") {
      loadNetwork();
    }
  }, [tab]);

  async function triggerScan() {
    setScanning(true);
    setScanMessage(null);
    setError(null);
    try {
      const res = await api<{ findings_generated: number; findings_updated: number; total_active_deposits_checked: number }>(
        "/integrity/scan",
        { method: "POST" }
      );
      setScanMessage(
        `Integrity scan completed: ${res.total_active_deposits_checked} deposits analyzed. Found ${res.findings_generated} new anomalies, updated ${res.findings_updated} existing findings.`
      );
      loadFindings();
      if (tab === "network") loadNetwork();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Integrity scan failed");
    } finally {
      setScanning(false);
    }
  }

  async function openFindingDetail(findingId: number) {
    try {
      const detail = await api<IntegrityFinding>(`/integrity/findings/${findingId}`);
      setActiveFinding(detail);
      setNewStatus(detail.status);
      setAssignee(detail.assignee || "");
      setReviewNotes("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load finding details");
    }
  }

  async function submitAction(e: React.FormEvent) {
    e.preventDefault();
    if (!activeFinding) return;
    setActionLoading(true);
    try {
      await apiJson(`/integrity/findings/${activeFinding.id}/actions`, "POST", {
        action: reviewAction,
        new_status: reviewAction === "STATUS_CHANGE" ? newStatus : undefined,
        assignee: reviewAction === "ASSIGN" ? assignee : undefined,
        notes: reviewNotes,
      });
      // Refresh modal detail and list
      await openFindingDetail(activeFinding.id);
      loadFindings();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to record review action");
    } finally {
      setActionLoading(false);
    }
  }

  const severityBadge = (sev: string) => {
    const map: Record<string, string> = {
      CRITICAL: "bg-red-100 text-red-800 border-red-200",
      HIGH: "bg-orange-100 text-orange-800 border-orange-200",
      MEDIUM: "bg-amber-100 text-amber-800 border-amber-200",
      LOW: "bg-blue-100 text-blue-800 border-blue-200",
    };
    return (
      <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${map[sev] || "bg-slate-100 text-slate-700"}`}>
        {sev}
      </span>
    );
  };

  const statusBadge = (st: string) => {
    const map: Record<string, string> = {
      OPEN: "bg-rose-50 text-rose-700 border-rose-200",
      UNDER_REVIEW: "bg-amber-50 text-amber-700 border-amber-200",
      CONFIRMED_INCONSISTENCY: "bg-red-50 text-red-700 border-red-200",
      FALSE_POSITIVE: "bg-slate-100 text-slate-700 border-slate-200",
      RESOLVED: "bg-emerald-50 text-emerald-700 border-emerald-200",
      ESCALATED: "bg-purple-50 text-purple-700 border-purple-200",
    };
    return (
      <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${map[st] || "bg-slate-100 border-slate-200"}`}>
        {st.replace(/_/g, " ")}
      </span>
    );
  };

  return (
    <Shell>
      <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-[#0f2d52]">Cross-Record Integrity Network</h1>
          <p className="mt-1 text-sm text-slate-600">
            Multi-record anomaly detection, duplicate reconciliation, conflict investigation, and relationship analysis
          </p>
        </div>

        {isOfficerOrAdmin && (
          <button
            onClick={triggerScan}
            disabled={scanning}
            className="inline-flex items-center gap-2 rounded-lg bg-[#0f2d52] px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#1a3d6b] disabled:opacity-50"
          >
            {scanning ? "Scanning Repository…" : "Run Integrity Scan"}
          </button>
        )}
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {scanMessage && <Notice kind="ok">{scanMessage}</Notice>}

      {/* Summary KPI Cards */}
      {summary && (
        <div className="my-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Open Critical</p>
            <p className="mt-1 text-2xl font-bold text-red-600">{summary.by_severity.CRITICAL || 0}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Open High</p>
            <p className="mt-1 text-2xl font-bold text-orange-600">{summary.by_severity.HIGH || 0}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Under Review</p>
            <p className="mt-1 text-2xl font-bold text-amber-600">{summary.by_status.UNDER_REVIEW || 0}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Confirmed Inconsistent</p>
            <p className="mt-1 text-2xl font-bold text-rose-700">{summary.by_status.CONFIRMED_INCONSISTENCY || 0}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Resolved</p>
            <p className="mt-1 text-2xl font-bold text-emerald-600">{summary.by_status.RESOLVED || 0}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <p className="text-xs font-medium text-slate-500">False Positives</p>
            <p className="mt-1 text-2xl font-bold text-slate-600">{summary.by_status.FALSE_POSITIVE || 0}</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-6 flex gap-2 border-b border-slate-200">
        <button
          onClick={() => setTab("findings")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            tab === "findings" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Investigation Board ({findings.length})
        </button>
        <button
          onClick={() => setTab("network")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            tab === "network" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Network Graph Explorer
        </button>
      </div>

      {tab === "findings" && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-600">Filter Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs focus:border-blue-500 focus:outline-none"
              >
                <option value="">All Statuses</option>
                <option value="OPEN">Open</option>
                <option value="UNDER_REVIEW">Under Review</option>
                <option value="CONFIRMED_INCONSISTENCY">Confirmed Inconsistency</option>
                <option value="FALSE_POSITIVE">False Positive</option>
                <option value="RESOLVED">Resolved</option>
                <option value="ESCALATED">Escalated</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-600">Filter Severity:</span>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs focus:border-blue-500 focus:outline-none"
              >
                <option value="">All Severities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            {loading ? (
              <div className="p-10 text-center text-sm text-slate-500">Loading findings…</div>
            ) : findings.length === 0 ? (
              <div className="p-10 text-center text-sm text-slate-500">
                No integrity findings detected matching criteria. Click &quot;Run Integrity Scan&quot; to check the repository.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50/70 text-xs font-semibold uppercase tracking-wider text-slate-600">
                    <tr>
                      <th className="px-4 py-3">Severity</th>
                      <th className="px-4 py-3">Category</th>
                      <th className="px-4 py-3">Explanation & Colliding Values</th>
                      <th className="px-4 py-3">Related FDRs</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Assignee</th>
                      <th className="px-4 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {findings.map((f) => (
                      <tr key={f.id} className="transition-colors hover:bg-slate-50/70">
                        <td className="px-4 py-3.5">{severityBadge(f.severity)}</td>
                        <td className="px-4 py-3.5 font-medium text-slate-800">{f.category.replace(/_/g, " ")}</td>
                        <td className="max-w-md px-4 py-3.5 text-xs text-slate-700">
                          <p className="font-medium text-slate-900">{f.explanation}</p>
                          {f.trigger_values && Object.keys(f.trigger_values).length > 0 && (
                            <p className="mt-1 font-mono text-[11px] text-slate-500">
                              Values: {JSON.stringify(f.trigger_values)}
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-xs">
                          <div className="flex flex-wrap gap-1">
                            {f.related_deposit_ids.map((id: any) => (
                              <Link
                                key={id}
                                href={`/deposits/${id}`}
                                className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-blue-700 hover:underline"
                              >
                                #{id}
                              </Link>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">{statusBadge(f.status)}</td>
                        <td className="px-4 py-3.5 text-xs text-slate-600">{f.assignee || "—"}</td>
                        <td className="px-4 py-3.5 text-right">
                          <button
                            onClick={() => openFindingDetail(f.id)}
                            className="rounded-md bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                          >
                            Investigate
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "network" && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Cross-Record Relationship Graph</h2>
              <p className="text-xs text-slate-500">
                Visualizing relationships between Institutions (Green), FDR Deposits (Blue), and Detected Anomalies (Red)
              </p>
            </div>
            <button
              onClick={loadNetwork}
              className="rounded-lg border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
            >
              Refresh Graph
            </button>
          </div>

          {networkLoading ? (
            <div className="p-12 text-center text-sm text-slate-500">Generating network diagram…</div>
          ) : !networkData || networkData.nodes.length === 0 ? (
            <div className="p-12 text-center text-sm text-slate-500">No network nodes available to render.</div>
          ) : (
            <div className="space-y-4">
              {/* Interactive Visual Network Representation */}
              <div className="relative min-h-[350px] overflow-hidden rounded-xl border border-slate-200 bg-slate-50/60 p-6">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
                  {networkData.nodes.map((node) => {
                    const isFinding = node.type === "finding";
                    const isDeposit = node.type === "deposit";

                    const cardBg = isFinding
                      ? "border-red-300 bg-red-50/80 text-red-950"
                      : isDeposit
                      ? "border-blue-300 bg-blue-50/80 text-blue-950"
                      : "border-emerald-300 bg-emerald-50/80 text-emerald-950";

                    return (
                      <div key={node.id} className={`rounded-xl border p-4 shadow-sm transition-all hover:shadow-md ${cardBg}`}>
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-bold uppercase tracking-wider text-[11px]">
                            {isFinding ? "Anomaly Finding" : isDeposit ? "FDR Record" : "Institution"}
                          </span>
                          <span className="font-mono text-[10px] text-slate-500">{node.id}</span>
                        </div>
                        <p className="mt-2 text-sm font-semibold leading-tight">{node.label}</p>
                        {isFinding && (
                          <div className="mt-2 text-xs">
                            <span className="font-medium text-red-800">Severity: {String(node.severity)}</span>
                            <p className="mt-1 line-clamp-2 text-[11px] text-slate-600">{String(node.explanation)}</p>
                            <button
                              onClick={() => openFindingDetail(Number(node.finding_id))}
                              className="mt-2 text-xs font-semibold text-blue-700 underline"
                            >
                              Review Anomaly →
                            </button>
                          </div>
                        )}
                        {isDeposit && (
                          <div className="mt-2 text-xs">
                            <p className="text-slate-700">Bank: {String(node.bank_name)}</p>
                            <p className="font-semibold text-slate-900">₹{Number(node.amount || 0).toLocaleString("en-IN")}</p>
                            <Link href={`/deposits/${node.deposit_id}`} className="mt-2 inline-block text-xs font-semibold text-blue-700 underline">
                              Open FDR Detail →
                            </Link>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Connected Relationships Edge Table */}
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h3 className="text-xs font-semibold uppercase text-slate-600">Cross-Record Connected Links ({networkData.edges.length})</h3>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {networkData.edges.map((e, idx) => (
                    <span key={idx} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-700">
                      <span className="font-mono font-medium">{e.source}</span>
                      <span className="mx-1 font-bold text-blue-600">--[{e.relation}]--&gt;</span>
                      <span className="font-mono font-medium">{e.target}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Investigation Detail Modal / Drawer */}
      {activeFinding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-200 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  {severityBadge(activeFinding.severity)}
                  <span className="text-xs font-mono text-slate-500">{activeFinding.finding_code}</span>
                </div>
                <h2 className="mt-1 text-lg font-bold text-slate-900">
                  {activeFinding.category.replace(/_/g, " ")}
                </h2>
              </div>
              <button
                onClick={() => setActiveFinding(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 py-4 text-sm">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">Explanation</label>
                <p className="mt-0.5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-slate-800">
                  {activeFinding.explanation}
                </p>
              </div>

              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">Triggering Colliding Values</label>
                <pre className="mt-0.5 overflow-x-auto rounded-lg border border-slate-200 bg-slate-900 p-3 text-xs text-blue-200">
                  {JSON.stringify(activeFinding.trigger_values, null, 2)}
                </pre>
              </div>

              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">Related Deposits</label>
                <div className="mt-1 flex flex-wrap gap-2">
                  {activeFinding.related_deposit_ids.map((id: any) => (
                    <Link
                      key={id}
                      href={`/deposits/${id}`}
                      target="_blank"
                      className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                    >
                      FDR Deposit #{id} ↗
                    </Link>
                  ))}
                </div>
              </div>

              {/* Action History Audit Trail */}
              {activeFinding.actions && activeFinding.actions.length > 0 && (
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">Resolution History</label>
                  <div className="mt-1 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
                    {activeFinding.actions.map((act: any) => (
                      <div key={act.id} className="border-b border-slate-200 pb-2 text-xs last:border-0 last:pb-0">
                        <div className="flex justify-between text-slate-500">
                          <span className="font-semibold text-slate-800">{act.actor} ({act.action})</span>
                          <span>{new Date(act.created_at).toLocaleString("en-IN")}</span>
                        </div>
                        {act.notes && <p className="mt-1 text-slate-700">&quot;{act.notes}&quot;</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Officer Investigation Action Form */}
              {isOfficerOrAdmin && (
                <form onSubmit={submitAction} className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
                  <h3 className="text-sm font-semibold text-blue-950">Record Investigation Action</h3>
                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-xs font-medium text-slate-700">Action Type</label>
                      <select
                        value={reviewAction}
                        onChange={(e) => setReviewAction(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
                      >
                        <option value="STATUS_CHANGE">Change Investigation Status</option>
                        <option value="ASSIGN">Assign Reviewer</option>
                        <option value="COMMENT">Add Investigation Note</option>
                      </select>
                    </div>

                    {reviewAction === "STATUS_CHANGE" && (
                      <div>
                        <label className="block text-xs font-medium text-slate-700">New Status</label>
                        <select
                          value={newStatus}
                          onChange={(e) => setNewStatus(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
                        >
                          <option value="UNDER_REVIEW">Under Review</option>
                          <option value="CONFIRMED_INCONSISTENCY">Confirmed Inconsistency</option>
                          <option value="FALSE_POSITIVE">False Positive (requires reason)</option>
                          <option value="RESOLVED">Resolved (requires reason)</option>
                          <option value="ESCALATED">Escalated</option>
                        </select>
                      </div>
                    )}

                    {reviewAction === "ASSIGN" && (
                      <div>
                        <label className="block text-xs font-medium text-slate-700">Assignee Username</label>
                        <input
                          type="text"
                          placeholder="e.g. officer1"
                          value={assignee}
                          onChange={(e) => setAssignee(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                    )}
                  </div>

                  <div className="mt-3">
                    <label className="block text-xs font-medium text-slate-700">
                      Officer Notes / Resolution Justification <span className="text-red-500">*</span>
                    </label>
                    <textarea
                      required
                      rows={2}
                      placeholder="Explain findings, branch verification notes, or reason for status verdict..."
                      value={reviewNotes}
                      onChange={(e) => setReviewNotes(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveFinding(null)}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                    >
                      Close
                    </button>
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="rounded-lg bg-[#0f2d52] px-4 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-[#1a3d6b] disabled:opacity-50"
                    >
                      {actionLoading ? "Saving…" : "Save Action & Update Audit Trail"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
