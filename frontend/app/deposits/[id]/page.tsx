"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { Notice, PageTitle, Shell, StatusBadge } from "@/components/Shell";
import {
  api,
  apiJson,
  apiUpload,
  Deposit,
  dateOnly,
  dateTime,
  Doc,
  downloadFile,
  getSession,
  HistoryEntry,
  MATCH_FIELDS,
  money,
  Role,
} from "@/lib/api";

const RELEASABLE = ["ACTIVE", "EXPIRING", "MATURED"];
const RENEWABLE = ["VERIFIED", "ACTIVE", "EXPIRING", "MATURED"];
const VERIFIABLE = ["SUBMITTED", "DISCREPANCY"];

type VerifyForm = Record<string, string>;

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
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [verifyForm, setVerifyForm] = useState<VerifyForm>({});
  const [observations, setObservations] = useState("");
  const [renewForm, setRenewForm] = useState<Record<string, string>>({});
  const [showRenew, setShowRenew] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, h, documents] = await Promise.all([
        api<Deposit>(`/deposits/${id}`),
        api<HistoryEntry[]>(`/deposits/${id}/history`),
        api<Doc[]>(`/deposits/${id}/documents`),
      ]);
      setDeposit(d);
      setHistory(h);
      setDocs(documents);
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
      "Renewal submitted. The old FDR is marked as renewed.",
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
      <div className="flex flex-wrap items-center gap-3">
        <PageTitle title={deposit.reference_no} />
        <StatusBadge status={deposit.status} />
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {ok && <Notice kind="ok">{ok}</Notice>}

      {deposit.mismatch_fields.length > 0 && (
        <Notice kind="error">
          Bank-confirmed values differ from the submitted values for: {deposit.mismatch_fields.join(", ").replace(/_/g, " ")}.
          Review the comparison below.
        </Notice>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <h2 className="border-b border-slate-100 px-5 py-3 font-semibold">Submitted vs bank-confirmed</h2>
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
                const format = (v: string | null) => (f.key === "amount" ? money(v) : dateOnly(v));
                return (
                  <tr key={f.key} className={`border-t border-slate-100 ${mismatch ? "bg-red-50" : ""}`}>
                    <td className="px-5 py-3 font-medium">{f.label}</td>
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

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {canVerify && (
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">Record bank verification</h2>
              <p className="mt-1 text-sm text-slate-600">Enter the values confirmed by the bank. Any difference from the submitted values is flagged.</p>
              <form onSubmit={submitVerify} className="mt-4 grid gap-4 sm:grid-cols-2">
                {MATCH_FIELDS.map((f) => (
                  <label key={f.key} className="block text-sm">
                    <span className="font-medium">{f.label}</span>
                    <input
                      className={field}
                      type={f.key.endsWith("date") ? "date" : "text"}
                      value={verifyForm[f.confirmed] ?? ""}
                      onChange={(e) => setVerifyForm((v) => ({ ...v, [f.confirmed]: e.target.value }))}
                    />
                  </label>
                ))}
                <label className="block text-sm sm:col-span-2">
                  <span className="font-medium">Observations</span>
                  <textarea className={field} rows={2} value={observations} onChange={(e) => setObservations(e.target.value)} />
                </label>
                <button disabled={busy} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 sm:col-span-2 sm:w-fit">
                  Save verification
                </button>
              </form>
            </section>
          )}

          {canRenew && (
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">Renew FDR</h2>
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
                      <span className="font-medium">{label}</span>
                      <input
                        required
                        type={type}
                        className={field}
                        value={renewForm[name] ?? ""}
                        onChange={(e) => setRenewForm((r) => ({ ...r, [name]: e.target.value }))}
                      />
                    </label>
                  ))}
                  <button disabled={busy} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 sm:col-span-2 sm:w-fit">
                    Submit renewal
                  </button>
                </form>
              )}
            </section>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Documents</h2>
            {docs.length === 0 && <p className="mt-2 text-sm text-slate-500">No documents uploaded yet.</p>}
            <ul className="mt-3 divide-y divide-slate-100">
              {docs.map((doc) => (
                <li key={doc.id} className="flex items-center justify-between py-3 text-sm">
                  <div>
                    <p className="font-medium">{doc.filename}</p>
                    <p className="text-xs text-slate-500">
                      {(doc.size_bytes / 1024).toFixed(0)} KB · {doc.uploaded_by} · {dateTime(doc.uploaded_at)}
                    </p>
                  </div>
                  <button onClick={() => downloadFile(`/documents/${doc.id}/download`, doc.filename)} className="text-blue-700 hover:underline">
                    Download
                  </button>
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
            <h2 className="font-semibold">Actions</h2>
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
            <h2 className="font-semibold">Timeline</h2>
            <ol className="mt-3 space-y-4 border-l border-slate-200 pl-4">
              {history.map((h) => (
                <li key={h.id} className="text-sm">
                  <p className="font-medium">{h.action.replace(/_/g, " ").toLowerCase()}</p>
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
    </Shell>
  );
}
