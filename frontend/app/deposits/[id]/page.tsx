"use client";

import Link from "next/link";
import { VersionHistory } from "@/components/VersionHistory";
import { useParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { Notice, PageTitle, Shell, StatusBadge } from "@/components/Shell";
import {
  api,
  apiJson,
  apiUpload,
  DeficiencyItem,
  DeficiencyReportPreview,
  Deposit,
  dateOnly,
  dateTime,
  Doc,
  downloadFile,
  getApiBaseUrl,
  getSession,
  HistoryEntry,
  MATCH_FIELDS,
  money,
  ReadinessResponse,
  Role,
  TraceResponse,
} from "@/lib/api";

const RELEASABLE = ["ACTIVE", "EXPIRING", "MATURED"];
const RENEWABLE = ["VERIFIED", "ACTIVE", "EXPIRING", "MATURED"];
const VERIFIABLE = ["SUBMITTED", "DISCREPANCY"];

type VerifyForm = Record<string, string>;

type SnapshotItem = {
  id: number;
  rule_code: string;
  rule_version: string;
  assessment_type: string;
  is_replay: boolean;
  evaluation_result: string;
  conditions: {
    condition_id: string;
    title: string;
    passed: boolean;
    reason: string;
  }[];
  assessed_by: string;
  assessed_at: string;
};

export default function DepositDetailPage() {
  return (
    <Suspense fallback={null}>
      <DepositDetail />
    </Suspense>
  );
}

function DepositDetail() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [role, setRole] = useState<Role | null>(null);
  const [deposit, setDeposit] = useState<Deposit | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);

  const [activeTab, setActiveTab] = useState<"overview" | "trace" | "readiness" | "regulations">("overview");

  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [verifyForm, setVerifyForm] = useState<VerifyForm>({});
  const [observations, setObservations] = useState("");
  const [renewForm, setRenewForm] = useState<Record<string, string>>({});
  const [showRenew, setShowRenew] = useState(false);

  // FEATURE 3: Deficiency Report Generator State
  const [showDeficiencyModal, setShowDeficiencyModal] = useState(false);
  const [deficiencyPreview, setDeficiencyPreview] = useState<DeficiencyReportPreview | null>(null);
  const [loadingDeficiency, setLoadingDeficiency] = useState(false);
  const [selectedDeficiencyIds, setSelectedDeficiencyIds] = useState<string[]>([]);
  const [customDirective, setCustomDirective] = useState("");
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  async function openDeficiencyReport() {
    setLoadingDeficiency(true);
    setShowDeficiencyModal(true);
    setError(null);
    try {
      const preview = await api<DeficiencyReportPreview>(`/deposits/${id}/deficiency-report/preview`);
      setDeficiencyPreview(preview);
      setSelectedDeficiencyIds(preview.deficiencies.map((d) => d.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not evaluate deficiencies");
      setShowDeficiencyModal(false);
    } finally {
      setLoadingDeficiency(false);
    }
  }

  function toggleDeficiency(defId: string) {
    setSelectedDeficiencyIds((prev) =>
      prev.includes(defId) ? prev.filter((i) => i !== defId) : [...prev, defId]
    );
  }

  async function downloadDeficiencyPdf() {
    setDownloadingPdf(true);
    try {
      const baseUrl = getApiBaseUrl();
      const token = getSession()?.token;
      const res = await fetch(`${baseUrl}/api/deposits/${id}/deficiency-report`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          confirmed_deficiency_ids: selectedDeficiencyIds,
          additional_comments: customDirective.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || "Could not generate report");
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `AICTE_Deficiency_Report_${deposit?.reference_no.replace(/[\/\\]/g, "_") || id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      setOk("Deficiency report PDF generated and downloaded successfully.");
      setShowDeficiencyModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF download failed");
    } finally {
      setDownloadingPdf(false);
    }
  }

  const load = useCallback(async () => {
    try {
      const [d, h, documents, tr, rd, sn] = await Promise.all([
        api<Deposit>(`/deposits/${id}`),
        api<HistoryEntry[]>(`/deposits/${id}/history`),
        api<Doc[]>(`/deposits/${id}/documents`),
        api<TraceResponse>(`/deposits/${id}/trace`).catch(() => null),
        api<ReadinessResponse>(`/deposits/${id}/readiness`).catch(() => null),
        api<SnapshotItem[]>(`/regulations/snapshots/${id}`).catch(() => []),
      ]);
      setDeposit(d);
      setHistory(h);
      setDocs(documents);
      setTrace(tr);
      setReadiness(rd);
      setSnapshots(sn || []);

      setVerifyForm({
        confirmed_reference_no: d.confirmed_reference_no ?? d.reference_no,
        confirmed_bank_name: d.confirmed_bank_name ?? d.bank_name,
        confirmed_amount: d.confirmed_amount ?? d.amount,
        confirmed_issue_date: d.confirmed_issue_date ?? d.issue_date,
        confirmed_maturity_date: d.confirmed_maturity_date ?? d.maturity_date,
      });
      setRenewForm({ reference_no: "", bank_name: d.bank_name, amount: d.amount, issue_date: "", maturity_date: "" });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this deposit");
    }
  }, [id]);

  useEffect(() => {
    setRole(getSession()?.role ?? null);
    load();
    if (typeof window !== "undefined" && window.location.hash) {
      const hash = window.location.hash.replace("#", "");
      if (["overview", "trace", "readiness", "regulations"].includes(hash)) {
        setActiveTab(hash as "overview" | "trace" | "readiness" | "regulations");
      }
    }
  }, [load]);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      await action();
      setOk(success);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  function submitVerify(e: FormEvent) {
    e.preventDefault();
    run(
      () =>
        apiJson(`/deposits/${id}/verify`, "POST", {
          confirmed_reference_no: verifyForm.confirmed_reference_no,
          confirmed_bank_name: verifyForm.confirmed_bank_name,
          confirmed_amount: verifyForm.confirmed_amount,
          confirmed_issue_date: verifyForm.confirmed_issue_date,
          confirmed_maturity_date: verifyForm.confirmed_maturity_date,
          observations,
        }),
      "Verification recorded.",
    );
  }

  function submitRenew(e: FormEvent) {
    e.preventDefault();
    if (!deposit) return;
    run(
      () =>
        apiJson(`/deposits/${id}/renew`, "POST", {
          institution_id: deposit.institution_id,
          reference_no: renewForm.reference_no,
          bank_name: renewForm.bank_name,
          amount: renewForm.amount,
          issue_date: renewForm.issue_date,
          maturity_date: renewForm.maturity_date,
        }),
      "Renewal sent for approval. The current FDR stays as it is until an approver accepts the renewal.",
    ).then(() => setShowRenew(false));
  }

  async function onUpload(file: File | undefined) {
    if (!file) return;
    run(() => apiUpload(`/deposits/${id}/documents`, file), "Document uploaded.");
  }

  if (error && !deposit) {
    return (
      <Shell>
        <Notice kind="error">{error}</Notice>
        <Link href="/deposits" className="text-blue-700 hover:underline">
          Back to deposits
        </Link>
      </Shell>
    );
  }

  if (!deposit || !role) {
    return <Shell>Loading…</Shell>;
  }

  const canVerify = (role === "REGULATOR_OFFICER" || role === "ADMIN") && VERIFIABLE.includes(deposit.status);
  const canRelease = (role === "INSTITUTION_USER" || role === "ADMIN") && RELEASABLE.includes(deposit.status);
  const canRenew = (role === "INSTITUTION_USER" || role === "ADMIN") && RENEWABLE.includes(deposit.status);
  const canUpload = role === "INSTITUTION_USER" || role === "REGULATOR_OFFICER" || role === "ADMIN";
  const canDecide = role === "APPROVING_AUTHORITY" || role === "ADMIN";

  const field = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";

  return (
    <Shell>
      <div className="mb-2">
        <Link href="/deposits" className="text-sm text-blue-700 hover:underline">
          ← All deposits
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
        <div className="flex items-center gap-3">
          <PageTitle title={deposit.reference_no} />
          <StatusBadge status={deposit.status} />
        </div>

        {/* Quick Links & Deficiency Report Action */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={openDeficiencyReport}
            className="rounded-lg bg-[#0c2340] px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-[#123a6b] flex items-center gap-1.5"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span>Generate Deficiency Report</span>
          </button>

          {readiness && (
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                readiness.overall_status === "READY_FOR_APPROVAL"
                  ? "bg-emerald-100 text-emerald-800"
                  : readiness.overall_status === "BLOCKED"
                  ? "bg-red-100 text-red-800"
                  : "bg-amber-100 text-amber-800"
              }`}
            >
              Release Readiness: {readiness.overall_status.replace(/_/g, " ")}
            </span>
          )}
          <Link
            href={`/integrity`}
            className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Check Anomalies
          </Link>
        </div>
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}

      {deposit.mismatch_fields.length > 0 && (
        <div className="my-3 flex flex-col justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-900 sm:flex-row sm:items-center">
          <div>
            <p className="font-bold">Scrutiny Discrepancies Recorded:</p>
            <p className="mt-0.5">
              Bank-confirmed values differ from submitted values for:{" "}
              {deposit.mismatch_fields.join(", ").replace(/_/g, " ")}.
            </p>
          </div>
          <button
            type="button"
            onClick={openDeficiencyReport}
            className="shrink-0 rounded-lg bg-red-700 px-3 py-1.5 font-bold text-white shadow-xs hover:bg-red-800 transition"
          >
            Generate Deficiency Notice →
          </button>
        </div>
      )}

      {/* Feature Tabs */}
      <div className="my-5 flex gap-2 border-b border-slate-200">
        <button
          onClick={() => setActiveTab("overview")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === "overview" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Overview & Verification
        </button>
        <button
          onClick={() => setActiveTab("trace")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === "trace" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          FDR TRACE (Lineage & Journal)
        </button>
        <button
          onClick={() => setActiveTab("readiness")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === "readiness" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Release Readiness Graph
        </button>
        <button
          onClick={() => setActiveTab("regulations")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            activeTab === "regulations" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Regulations & Replay ({snapshots.length})
        </button>
      </div>

      {/* TAB 1: OVERVIEW & VERIFICATION (PRESERVED ORIGINAL FUNCTIONALITY) */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <h2 className="border-b border-slate-100 px-5 py-3 font-semibold text-slate-900">Submitted vs bank-confirmed</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-600">
                  <tr>
                    <th className="px-5 py-3">Field</th>
                    <th className="px-5 py-3">Submitted</th>
                    <th className="px-5 py-3">Bank-confirmed</th>
                    <th className="px-5 py-3">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {MATCH_FIELDS.map((f) => {
                    const submitted = deposit[f.submitted] as string;
                    const confirmed = deposit[f.confirmed] as string | null;
                    const mismatch = deposit.mismatch_fields.includes(f.key);
                    const format = (v: string | null) =>
                      f.key === "amount" ? money(v) : f.key.endsWith("date") ? dateOnly(v) : v || "—";
                    return (
                      <tr key={f.key} className={`border-t border-slate-100 ${mismatch ? "bg-red-50" : ""}`}>
                        <td className="px-5 py-3 font-medium text-slate-800">{f.label}</td>
                        <td className="px-5 py-3">{format(submitted)}</td>
                        <td className="px-5 py-3">{confirmed == null ? <span className="text-slate-400">not checked</span> : format(confirmed)}</td>
                        <td className="px-5 py-3">
                          {confirmed == null ? "—" : mismatch ? <span className="font-medium text-red-700">Mismatch</span> : <span className="text-emerald-700">Match</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              {canVerify && (
                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <h2 className="font-semibold text-slate-900">Record bank verification</h2>
                  <p className="mt-1 text-sm text-slate-600">Enter values confirmed by the bank. Any difference from submitted values is flagged.</p>
                  <form onSubmit={submitVerify} className="mt-4 grid gap-4 sm:grid-cols-2">
                    {MATCH_FIELDS.map((f) => (
                      <label key={f.key} className="block text-sm">
                        <span className="font-medium text-slate-700">{f.label}</span>
                        <input
                          className={field}
                          type={f.key.endsWith("date") ? "date" : "text"}
                          value={verifyForm[f.confirmed] ?? ""}
                          onChange={(e) => setVerifyForm((v) => ({ ...v, [f.confirmed]: e.target.value }))}
                        />
                      </label>
                    ))}
                    <label className="block text-sm sm:col-span-2">
                      <span className="font-medium text-slate-700">Observations</span>
                      <textarea className={field} rows={2} value={observations} onChange={(e) => setObservations(e.target.value)} />
                    </label>
                    <button disabled={busy} className="rounded-lg bg-[#0f2d52] px-4 py-2 text-sm font-medium text-white hover:bg-[#1a3d6b] disabled:opacity-60 sm:col-span-2 sm:w-fit">
                      Save verification
                    </button>
                  </form>
                </section>
              )}

              {canRenew && (
                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900">Renew FDR</h2>
                    <button onClick={() => setShowRenew((s) => !s)} className="text-sm text-blue-700 hover:underline">
                      {showRenew ? "Hide" : "Start renewal"}
                    </button>
                  </div>
                  {showRenew && (
                    <form onSubmit={submitRenew} className="mt-4 grid gap-4 sm:grid-cols-2">
                      {[
                        ["reference_no", "New FDR number", "text"],
                        ["bank_name", "Bank", "text"],
                        ["amount", "Amount (₹)", "text"],
                        ["issue_date", "Issue date", "date"],
                        ["maturity_date", "Maturity date", "date"],
                      ].map(([name, label, type]) => (
                        <label key={name} className="block text-sm">
                          <span className="font-medium text-slate-700">{label}</span>
                          <input
                            required
                            type={type}
                            className={field}
                            value={renewForm[name] ?? ""}
                            onChange={(e) => setRenewForm((r) => ({ ...r, [name]: e.target.value }))}
                          />
                        </label>
                      ))}
                      <button disabled={busy} className="rounded-lg bg-[#0f2d52] px-4 py-2 text-sm font-medium text-white hover:bg-[#1a3d6b] disabled:opacity-60 sm:col-span-2 sm:w-fit">
                        Submit renewal
                      </button>
                    </form>
                  )}
                </section>
              )}

              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="font-semibold text-slate-900">Documents</h2>
                {docs.length === 0 && <p className="mt-2 text-sm text-slate-500">No documents uploaded yet.</p>}
                <ul className="mt-3 divide-y divide-slate-100">
                  {docs.map((doc) => (
                    <li key={doc.id} className="flex flex-wrap items-center justify-between py-3 text-sm">
                      <div>
                        <p className="font-medium text-slate-900">{doc.filename}</p>
                        <p className="text-xs text-slate-500">
                          {(doc.size_bytes / 1024).toFixed(0)} KB · {doc.uploaded_by} · {dateTime(doc.uploaded_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-500">v{doc.version ?? 1}</span>
                        <button onClick={() => downloadFile(`/documents/${doc.id}/download`, doc.filename)} className="text-blue-700 hover:underline">
                          Download
                        </button>
                      </div>
                      <div className="mt-2 w-full">
                        <VersionHistory depositId={Number(id)} doc={doc} canUpload={canUpload} onChanged={load} />
                      </div>
                    </li>
                  ))}
                </ul>
                {canUpload && (
                  <label className="mt-4 inline-block cursor-pointer rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50">
                    Upload document
                    <input
                      type="file"
                      accept="application/pdf,image/png,image/jpeg"
                      className="hidden"
                      onChange={(e) => onUpload(e.target.files?.[0])}
                    />
                  </label>
                )}
              </section>
            </div>

            <div className="space-y-6">
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="font-semibold text-slate-900">Actions</h2>
                <div className="mt-3 space-y-3 text-sm">
                  {canRelease && (
                    <button
                      disabled={busy}
                      onClick={() => run(() => apiJson(`/deposits/${id}/release`, "POST", {}), "Release requested. An approving authority will review it.")}
                      className="w-full rounded-lg bg-violet-600 px-4 py-2 font-medium text-white hover:bg-violet-700 disabled:opacity-60"
                    >
                      Request release
                    </button>
                  )}
                  {canDecide && deposit.status === "RELEASE_REQUESTED" && (
                    <p className="text-slate-600">
                      A release is waiting for a decision.{" "}
                      <Link href="/approvals" className="text-blue-700 hover:underline">
                        Open approvals
                      </Link>
                    </p>
                  )}
                  {!canVerify && !canRelease && !canRenew && !canDecide && (
                    <p className="text-slate-500">No actions are available for your role at this status.</p>
                  )}
                </div>
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="font-semibold text-slate-900">Activity Log</h2>
                <ol className="mt-3 space-y-4 border-l border-slate-200 pl-4">
                  {history.map((h) => (
                    <li key={h.id} className="text-sm">
                      <p className="font-medium text-slate-800">{h.action.replace(/_/g, " ").toLowerCase()}</p>
                      <p className="text-slate-600">{h.detail}</p>
                      <p className="text-xs text-slate-500">
                        {h.actor} · {dateTime(h.at)}
                      </p>
                    </li>
                  ))}
                  {history.length === 0 && <li className="text-sm text-slate-500">No activity yet.</li>}
                </ol>
              </section>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: FDR TRACE (FEATURE 1) */}
      {activeTab === "trace" && (
        <div className="space-y-6">
          {trace ? (
            <>
              {/* Lineage Visual Cluster */}
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col justify-between gap-2 border-b border-slate-200 pb-3 sm:flex-row sm:items-center">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">Unified FDR Lineage Cluster</h3>
                    <p className="text-xs text-slate-500">
                      Total connected nodes: {trace.lineage.total_nodes} · Total relationships: {trace.lineage.total_edges}
                    </p>
                  </div>
                  <div className="text-xs">
                    <span className="font-mono text-slate-500">Root Deposit ID: #{trace.lineage.root_id}</span>
                  </div>
                </div>

                {/* Lineage visual nodes */}
                <div className="mt-5 flex flex-wrap items-center gap-4">
                  {trace.lineage.nodes.map((node, idx) => (
                    <div key={node.id} className="flex items-center gap-4">
                      <div
                        className={`min-w-[200px] rounded-xl border p-4 shadow-xs transition-all ${
                          node.is_current
                            ? "border-blue-600 bg-blue-50/50 ring-2 ring-blue-600/30"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono font-bold text-slate-900">FDR #{node.id}</span>
                          <StatusBadge status={node.status} />
                        </div>
                        <p className="mt-1 font-mono text-xs font-semibold text-blue-700">{node.reference_no}</p>
                        <p className="text-xs text-slate-600">{node.bank_name}</p>
                        <p className="mt-1 text-xs font-bold text-slate-900">{money(node.amount)}</p>
                        <p className="text-[11px] text-slate-500">Maturity: {dateOnly(node.maturity_date)}</p>

                        {!node.is_current && (
                          <Link
                            href={`/deposits/${node.id}#trace`}
                            className="mt-2 block text-xs font-semibold text-blue-700 hover:underline"
                          >
                            Open this FDR →
                          </Link>
                        )}
                        {node.is_current && (
                          <span className="mt-2 block text-[11px] font-bold text-blue-800">● CURRENT RECORD</span>
                        )}
                      </div>
                      {idx < trace.lineage.nodes.length - 1 && (
                        <span className="text-xl font-bold text-slate-400">→</span>
                      )}
                    </div>
                  ))}
                </div>

                {/* Accessible Table Alternative */}
                <div className="mt-6 border-t border-slate-100 pt-4">
                  <h4 className="text-xs font-semibold uppercase text-slate-500">Lineage Relationships Table</h4>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 font-semibold text-slate-600">
                        <tr>
                          <th className="px-3 py-2">Predecessor (Source)</th>
                          <th className="px-3 py-2">Relationship</th>
                          <th className="px-3 py-2">Successor (Target)</th>
                          <th className="px-3 py-2">Recorded By</th>
                          <th className="px-3 py-2">Timestamp</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {trace.lineage.edges.map((edge) => (
                          <tr key={edge.id}>
                            <td className="px-3 py-2 font-mono">FDR #{edge.source}</td>
                            <td className="px-3 py-2 font-bold text-purple-700">{edge.relation_type}</td>
                            <td className="px-3 py-2 font-mono">FDR #{edge.target}</td>
                            <td className="px-3 py-2">{edge.actor}</td>
                            <td className="px-3 py-2 text-slate-500">{new Date(edge.created_at).toLocaleString("en-IN")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Cryptographic Lifecycle Timeline Journal */}
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col justify-between gap-2 border-b border-slate-200 pb-3 sm:flex-row sm:items-center">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">Cryptographically Chained Lifecycle Journal</h3>
                    <p className="text-xs text-slate-500">
                      Append-only chronological audit journal with SHA-256 hash chaining for tamper-evident verification.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-md border px-2.5 py-0.5 text-xs font-semibold ${
                        trace.timeline.integrity.valid
                          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                          : "bg-red-50 text-red-800 border-red-200"
                      }`}
                    >
                      {trace.timeline.integrity.valid ? "Tamper-Check Passed" : "Integrity Verification Failed"}
                    </span>
                  </div>
                </div>

                <div className="mt-5 space-y-4">
                  {trace.timeline.events.map((evt) => (
                    <div key={evt.id} className="relative border-l-2 border-blue-200 pl-4 text-xs">
                      <div className="absolute -left-1.5 top-1 h-3 w-3 rounded-full border-2 border-blue-600 bg-white" />
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-900">{evt.summary}</span>
                        <span className="text-slate-500">{new Date(evt.created_at).toLocaleString("en-IN")}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-slate-600">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium">{evt.event_type}</span>
                        <span>by <strong>{evt.actor}</strong> ({evt.actor_role || "system"})</span>
                      </div>
                      {evt.event_hash && (
                        <p className="mt-1 font-mono text-[10px] text-slate-400">
                          Hash: {evt.event_hash.slice(0, 24)}… | Prev: {evt.prev_hash?.slice(0, 16) || "GENESIS"}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="p-10 text-center text-sm text-slate-500">Loading FDR TRACE data…</div>
          )}
        </div>
      )}

      {/* TAB 3: RELEASE READINESS GRAPH (FEATURE 2) */}
      {activeTab === "readiness" && (
        <div className="space-y-6">
          {readiness ? (
            <>
              {/* Overall Readiness Header Card */}
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
                  <div>
                    <div className="flex items-center gap-3">
                      <span
                        className={`rounded-full px-3 py-1 text-sm font-bold ${
                          readiness.overall_status === "READY_FOR_APPROVAL"
                            ? "bg-emerald-100 text-emerald-800"
                            : readiness.overall_status === "BLOCKED"
                            ? "bg-red-100 text-red-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {readiness.overall_status.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs text-slate-500">
                        Evaluated at: {new Date(readiness.evaluated_at).toLocaleString("en-IN")}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-600">
                      {readiness.is_ready_for_decision
                        ? "All mandatory prerequisites are satisfied. Release request is eligible for Approving Authority decision."
                        : "Release readiness is currently blocked or pending prerequisites. See actionable blockers below."}
                    </p>
                  </div>

                  <div className="text-right">
                    <p className="text-xs text-slate-500">Prerequisite Completion</p>
                    <p className="text-2xl font-bold text-slate-900">{readiness.completion_percentage}%</p>
                    <p className="text-[11px] text-slate-400">
                      {readiness.satisfied_count} of {readiness.total_prerequisites} satisfied
                    </p>
                  </div>
                </div>

                {/* Blocking reasons banner */}
                {readiness.blocking_reasons.length > 0 && (
                  <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-900">
                    <div className="flex items-center gap-1.5 font-bold text-red-950">
                      <svg className="h-4 w-4 shrink-0 text-red-600" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                      <span>Blocking Reasons (Mandatory):</span>
                    </div>
                    <ul className="mt-2 list-inside list-disc space-y-1">
                      {readiness.blocking_reasons.map((b, idx) => (
                        <li key={idx}>{b}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Recommended Next Actions */}
                {readiness.next_actions.length > 0 && (
                  <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50/50 p-4 text-xs text-blue-950">
                    <div className="flex items-center gap-1.5 font-bold text-blue-950">
                      <svg className="h-4 w-4 shrink-0 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clipRule="evenodd" />
                      </svg>
                      <span>Recommended Next Actions:</span>
                    </div>
                    <div className="mt-2 space-y-2">
                      {readiness.next_actions.map((act, idx) => (
                        <div key={idx} className="flex items-start justify-between rounded-lg bg-white p-2.5 shadow-xs">
                          <div>
                            <span className="font-bold text-slate-900">{act.node}: </span>
                            <span className="text-slate-700">{act.action}</span>
                          </div>
                          <span className="rounded bg-blue-100 px-2 py-0.5 text-[11px] font-semibold text-blue-800">
                            {act.role}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Prerequisite Nodes Checklist / Dependency Graph */}
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="border-b border-slate-200 pb-3 text-base font-bold text-slate-900">
                  Prerequisites Dependency Graph Nodes ({readiness.nodes.length})
                </h3>

                <div className="mt-4 space-y-3">
                  {readiness.nodes.map((node) => {
                    const statusColor =
                      node.status === "SATISFIED"
                        ? "border-emerald-200 bg-emerald-50/30 text-emerald-950"
                        : node.status === "BLOCKED"
                        ? "border-red-200 bg-red-50/40 text-red-950"
                        : node.status === "MISSING"
                        ? "border-orange-200 bg-orange-50/30 text-orange-950"
                        : "border-amber-200 bg-amber-50/30 text-amber-950";

                    return (
                      <div key={node.id} className={`rounded-xl border p-4 text-xs shadow-xs ${statusColor}`}>
                        <div className="flex flex-col justify-between gap-1 sm:flex-row sm:items-center">
                          <div className="flex items-center gap-2">
                            <span
                              className={`rounded px-2 py-0.5 font-bold ${
                                node.status === "SATISFIED"
                                  ? "bg-emerald-100 text-emerald-800"
                                  : node.status === "BLOCKED"
                                  ? "bg-red-100 text-red-800"
                                  : "bg-amber-100 text-amber-800"
                              }`}
                            >
                              {node.status}
                            </span>
                            <h4 className="text-sm font-bold text-slate-900">{node.title}</h4>
                            <span className="text-[11px] font-mono text-slate-400">({node.category})</span>
                          </div>
                          <span className="font-semibold text-slate-600">Action Role: {node.responsible_role}</span>
                        </div>

                        <p className="mt-2 text-slate-800">{node.explanation}</p>

                        <div className="mt-2 rounded-lg bg-white/80 p-2.5 font-medium text-slate-700">
                          <span className="font-bold text-slate-900">Next Action:</span> {node.next_action}
                        </div>

                        {node.evidence && Object.keys(node.evidence).length > 0 && (
                          <div className="mt-2 font-mono text-[11px] text-slate-500">
                            Evidence: {JSON.stringify(node.evidence)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          ) : (
            <div className="p-10 text-center text-sm text-slate-500">Evaluating Release Readiness Graph…</div>
          )}
        </div>
      )}

      {/* TAB 4: REGULATIONS & REPLAY (FEATURE 3) */}
      {activeTab === "regulations" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
              <div>
                <h3 className="text-base font-bold text-slate-900">Compliance Assessment Snapshots</h3>
                <p className="text-xs text-slate-500">
                  Immutable historical snapshots recorded whenever this deposit was assessed under AICTE regulations.
                </p>
              </div>
              <Link
                href="/regulations"
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#0f2d52] px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-[#1a3d6b]"
              >
                Open Replay Simulator →
              </Link>
            </div>

            {snapshots.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">
                No compliance snapshots recorded yet for this deposit.
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                {snapshots.map((snap) => (
                  <div key={snap.id} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-blue-800">
                          {snap.rule_code} v{snap.rule_version}
                        </span>
                        {snap.is_replay && (
                          <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-bold text-purple-800">
                            REPLAY SIMULATION
                          </span>
                        )}
                      </div>
                      <span
                        className={`rounded px-2 py-0.5 font-bold ${
                          snap.evaluation_result === "COMPLIANT"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-red-100 text-red-800"
                        }`}
                      >
                        {snap.evaluation_result}
                      </span>
                    </div>

                    <p className="mt-1 text-slate-500">
                      Assessed by {snap.assessed_by} on {new Date(snap.assessed_at).toLocaleString("en-IN")}
                    </p>

                    <div className="mt-3 space-y-1.5">
                      {snap.conditions?.map((c) => (
                        <div key={c.condition_id} className="rounded bg-white p-2 text-[11px] shadow-2xs">
                          <div className="flex justify-between">
                            <span className="font-semibold text-slate-800">{c.title}</span>
                            <span className={c.passed ? "font-bold text-emerald-600" : "font-bold text-red-600"}>
                              {c.passed ? "✓ Passed" : "✗ Failed"}
                            </span>
                          </div>
                          <p className="text-slate-600">{c.reason}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* FEATURE 3: Deficiency Report Generator Modal */}
      {showDeficiencyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 overflow-y-auto">
          <div className="relative my-8 flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-4">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#0c2340] text-white">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </span>
                <div>
                  <h3 className="text-base font-bold text-[#0c2340]">Deficiency Report Generator</h3>
                  <p className="text-xs text-slate-500">
                    FDR Reference: <span className="font-semibold text-slate-800">{deposit.reference_no}</span> · Scrutiny Findings Assessment
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowDeficiencyModal(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs text-slate-700">
              {loadingDeficiency ? (
                <div className="py-12 flex flex-col items-center justify-center gap-3 text-sm text-slate-500">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#0c2340] border-t-transparent" />
                  <span>Evaluating authentic deposit records, missing documents, and recorded scrutiny discrepancies…</span>
                </div>
              ) : deficiencyPreview && !deficiencyPreview.has_deficiencies ? (
                /* No Deficiencies Found State */
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center space-y-3">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                    <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <h4 className="text-base font-bold text-emerald-900">No Deficiencies Identified</h4>
                  <p className="max-w-lg mx-auto text-xs text-emerald-800 leading-relaxed">
                    This FDR record currently complies with all AICTE documentation and scrutiny requirements.
                    There are no missing documents, field discrepancies, or open integrity flags recorded.
                  </p>
                  <p className="text-[11px] text-emerald-700 font-medium">
                    In accordance with statutory guidelines, official deficiency reports are only generated for applications with active defects. A deficiency report is not applicable for this compliant record.
                  </p>
                </div>
              ) : deficiencyPreview ? (
                /* Deficiencies Found State: Interactive Confirmation & Review */
                <div className="space-y-6">
                  {/* Summary Callout Banner */}
                  <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                    <div className="flex items-start gap-2.5">
                      <span className="text-red-700 shrink-0 mt-0.5">
                        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                      </span>
                      <div>
                        <h4 className="font-bold text-red-900 text-xs">
                          Actionable Deficiencies Found ({deficiencyPreview.deficiencies.length})
                        </h4>
                        <p className="mt-0.5 text-xs text-red-800 leading-relaxed">
                          Review and confirm the identified discrepancies below. You can select specific items and append
                          officer directives before generating the official PDF notice.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* 1. Institution & FDR Summary Details */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                      1. Institution & Record Summary
                    </h4>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs">
                      <div>
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">Institution</span>
                        <span className="font-bold text-slate-800">{deficiencyPreview.institution_name}</span>
                        <span className="text-[10px] text-slate-500 block">({deficiencyPreview.institution_code})</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">Bank Name</span>
                        <span className="font-bold text-slate-800">{deficiencyPreview.bank_name}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">Deposit Amount</span>
                        <span className="font-bold text-slate-800">{money(deficiencyPreview.amount)}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">Maturity Date</span>
                        <span className="font-bold text-slate-800">{dateOnly(deficiencyPreview.maturity_date)}</span>
                      </div>
                    </div>
                  </div>

                  {/* 2. Confirmed Deficiencies Checklist */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                        2. Identified Deficiencies (Select to Include in Notice)
                      </h4>
                      <span className="text-[11px] text-slate-500">
                        {selectedDeficiencyIds.length} of {deficiencyPreview.deficiencies.length} selected
                      </span>
                    </div>

                    <div className="space-y-3">
                      {deficiencyPreview.deficiencies.map((d) => {
                        const isSelected = selectedDeficiencyIds.includes(d.id);
                        return (
                          <div
                            key={d.id}
                            onClick={() => toggleDeficiency(d.id)}
                            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition ${
                              isSelected
                                ? "border-red-300 bg-red-50/40 shadow-xs"
                                : "border-slate-200 bg-slate-50 opacity-60"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {}}
                              className="mt-1 h-4 w-4 rounded border-slate-300 text-red-600 focus:ring-red-500"
                            />
                            <div className="flex-1 space-y-1">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="font-bold text-slate-900">{d.title}</span>
                                <div className="flex items-center gap-1.5">
                                  <span
                                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                      d.severity === "CRITICAL"
                                        ? "bg-red-100 text-red-800"
                                        : "bg-amber-100 text-amber-800"
                                    }`}
                                  >
                                    {d.severity}
                                  </span>
                                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                                    {d.category.replace("_", " ")}
                                  </span>
                                </div>
                              </div>

                              <p className="text-slate-600 leading-snug">{d.explanation}</p>

                              {(d.submitted_value || d.verified_value) && (
                                <div className="mt-1 flex flex-wrap gap-4 text-[11px]">
                                  <span className="text-slate-500">
                                    Submitted: <b className="text-slate-800">{d.submitted_value || "—"}</b>
                                  </span>
                                  <span className="text-slate-500">
                                    Required: <b className="text-red-700">{d.verified_value || "—"}</b>
                                  </span>
                                </div>
                              )}

                              <div className="mt-1.5 rounded-lg bg-white border border-slate-200 p-2 text-[11px] text-slate-800 font-medium">
                                <span className="text-blue-800 font-bold uppercase text-[10px] block">
                                  Required Corrective Action:
                                </span>
                                {d.required_action}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* 3. Reviewer Observations from Audit Trail */}
                  {deficiencyPreview.reviewer_comments && deficiencyPreview.reviewer_comments.length > 0 && (
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                        3. Recorded Scrutiny Observations
                      </h4>
                      <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs text-slate-700">
                        {deficiencyPreview.reviewer_comments.map((comment, idx) => (
                          <p key={idx} className="leading-snug">
                            • {comment}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 4. Custom Reviewer Directives Textarea */}
                  <div>
                    <label htmlFor="custom-directives" className="text-xs font-bold uppercase tracking-wider text-slate-700 block mb-1">
                      4. Additional Officer Remarks & Statutory Instructions (Optional)
                    </label>
                    <textarea
                      id="custom-directives"
                      rows={3}
                      value={customDirective}
                      onChange={(e) => setCustomDirective(e.target.value)}
                      placeholder="Add specific instructions for the institution (e.g. 'Must provide bank manager signed confirmation letter with IFSC STAT0001234 before next Standing Hearing')."
                      className="w-full rounded-xl border border-slate-300 p-3 text-xs text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                    />
                  </div>
                </div>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4">
              {deficiencyPreview && deficiencyPreview.has_deficiencies ? (
                <>
                  <span className="text-xs font-medium text-slate-500">
                    {selectedDeficiencyIds.length} item(s) will be included in the official PDF report.
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setShowDeficiencyModal(false)}
                      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={downloadingPdf || selectedDeficiencyIds.length === 0}
                      onClick={downloadDeficiencyPdf}
                      className="rounded-lg bg-[#0c2340] px-5 py-2 text-xs font-bold text-white shadow-xs transition hover:bg-[#123a6b] disabled:opacity-60 flex items-center gap-1.5"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      <span>{downloadingPdf ? "Generating Official PDF…" : "Download Official PDF Notice"}</span>
                    </button>
                  </div>
                </>
              ) : (
                <div className="w-full flex justify-end">
                  <button
                    type="button"
                    onClick={() => setShowDeficiencyModal(false)}
                    className="rounded-lg bg-[#0c2340] px-5 py-2 text-xs font-bold text-white shadow-xs hover:bg-[#123a6b] transition"
                  >
                    Close
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
