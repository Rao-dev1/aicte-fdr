"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import { api, API_URL, getSession, Institution, money, Role } from "@/lib/api";

type RowResult = { line: number; data: Record<string, string>; errors: string[] };
type Preview = {
  institution: { id: number; name: string; code: string };
  total: number;
  valid: number;
  invalid: number;
  rows: RowResult[];
};

type DocResult = {
  attached: number;
  unmatched: number;
  rejected: number;
  results: { filename: string; status: "attached" | "unmatched" | "rejected"; reason?: string }[];
};

const inputClass = "mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";

export default function ImportPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionId, setInstitutionId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<number | null>(null);

  useEffect(() => {
    const session = getSession();
    if (session) setRole(session.role);
    if (session?.role === "ADMIN") {
      api<Institution[]>("/institutions").then(setInstitutions).catch(() => setError("Could not load institutions"));
    }
  }, []);

  function formFor(target: File, extra?: Record<string, string>) {
    const form = new FormData();
    form.append("file", target);
    if (role === "ADMIN" && institutionId) form.append("institution_id", institutionId);
    Object.entries(extra ?? {}).forEach(([k, v]) => form.append(k, v));
    return form;
  }

  async function runPreview(chosen: File | undefined) {
    if (!chosen) return;
    setFile(chosen);
    setPreview(null);
    setDone(null);
    setError(null);
    setBusy(true);
    try {
      setPreview(await api<Preview>("/deposits/import/preview", { method: "POST", body: formFor(chosen) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the file");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!file || !preview) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ created: number }>("/deposits/import/confirm", { method: "POST", body: formFor(file) });
      setDone(result.created);
      setPreview(null);
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed. Nothing was saved.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadTemplate() {
    try {
      const res = await fetch(`${API_URL}/api/deposits/import/template`, {
        headers: { Authorization: `Bearer ${getSession()?.token ?? ""}` },
      });
      if (!res.ok) throw new Error("Could not download the template");
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "fdr-import-template.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not download the template");
    }
  }

  const [docBusy, setDocBusy] = useState(false);
  const [docResult, setDocResult] = useState<DocResult | null>(null);
  const [docError, setDocError] = useState<string | null>(null);

  async function uploadDocuments(chosen: FileList | null) {
    if (!chosen || chosen.length === 0) return;
    setDocBusy(true);
    setDocError(null);
    setDocResult(null);
    try {
      const form = new FormData();
      Array.from(chosen).forEach((f) => form.append("files", f));
      setDocResult(await api<DocResult>("/documents/bulk", { method: "POST", body: form }));
    } catch (err) {
      setDocError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setDocBusy(false);
    }
  }

  const canImport = !!preview && preview.invalid === 0 && preview.total > 0;
  const needsInstitution = role === "ADMIN" && !institutionId;

  return (
    <Shell>
      <PageTitle title="Import FDRs" subtitle="Add many FDRs at once from a CSV or Excel file. You check every row before anything is saved." />

      {error && <Notice kind="error">{error}</Notice>}
      {done !== null && (
        <Notice kind="ok">
          {done} FDR(s) imported. <button className="underline" onClick={() => router.push("/deposits")}>View deposits</button>
        </Notice>
      )}

      <div className="max-w-4xl space-y-6">
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="font-semibold text-[#0f2d52]">1. Get the template</h2>
          <p className="text-sm text-slate-600">
            Columns: <code>reference_no, bank_name, amount, issue_date, maturity_date</code>. Dates can be YYYY-MM-DD or DD/MM/YYYY. Up to 500 rows, 5 MB.
          </p>
          <button onClick={downloadTemplate} className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50">
            Download CSV template
          </button>
        </section>

        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="font-semibold text-[#0f2d52]">2. Choose the file</h2>
          {role === "ADMIN" && (
            <label className="block text-sm font-medium">
              Institution
              <select className={`${inputClass} block w-full sm:w-96`} value={institutionId} onChange={(e) => setInstitutionId(e.target.value)}>
                <option value="">Select…</option>
                {institutions.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name} ({i.code})
                  </option>
                ))}
              </select>
            </label>
          )}
          <input
            type="file"
            accept=".csv,.xlsx"
            disabled={busy || needsInstitution}
            onChange={(e) => runPreview(e.target.files?.[0])}
            className="block text-sm"
          />
          {needsInstitution && <p className="text-sm text-slate-500">Choose an institution first.</p>}
          {busy && <p className="text-sm text-blue-700">Checking the file…</p>}
        </section>

        {preview && (
          <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-[#0f2d52]">3. Check the preview</h2>
            <p className="text-sm text-slate-700">
              {preview.institution.name}: {preview.total} row(s), <span className="font-medium text-emerald-700">{preview.valid} ready</span>,{" "}
              <span className="font-medium text-red-700">{preview.invalid} with problems</span>.
            </p>
            {preview.invalid > 0 && (
              <Notice kind="error">Fix the rows marked below in your file and upload it again. Nothing is saved until every row is valid.</Notice>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="bg-slate-100 text-xs uppercase text-slate-600">
                  <tr>
                    <th className="px-3 py-2">Line</th>
                    <th className="px-3 py-2">FDR number</th>
                    <th className="px-3 py-2">Bank</th>
                    <th className="px-3 py-2">Amount</th>
                    <th className="px-3 py-2">Issue</th>
                    <th className="px-3 py-2">Maturity</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.line} className={`border-t border-slate-100 ${r.errors.length ? "bg-red-50" : ""}`}>
                      <td className="px-3 py-2">{r.line}</td>
                      <td className="px-3 py-2">{r.data.reference_no || "—"}</td>
                      <td className="px-3 py-2">{r.data.bank_name || "—"}</td>
                      <td className="px-3 py-2">{money(r.data.amount)}</td>
                      <td className="px-3 py-2">{r.data.issue_date}</td>
                      <td className="px-3 py-2">{r.data.maturity_date}</td>
                      <td className="px-3 py-2 text-xs">
                        {r.errors.length === 0 ? <span className="text-emerald-700">OK</span> : <span className="text-red-700">{r.errors.join("; ")}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              onClick={confirm}
              disabled={!canImport || busy}
              className="rounded-lg bg-[#0f2d52] px-5 py-2.5 font-medium text-white hover:bg-[#123a6b] disabled:opacity-50"
            >
              {busy ? "Importing…" : `Import ${preview.valid} FDR(s)`}
            </button>
          </section>
        )}

        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="font-semibold text-[#0f2d52]">Attach scanned documents to existing FDRs</h2>
          <p className="text-sm text-slate-600">
            Name each scan with its FDR number, for example <code>FDR-2026-0001.pdf</code>. Each file is attached to the FDR with that number.
            Up to 50 files at once, 10 MB each. Files that do not match an FDR are listed below so you can rename and send them again.
          </p>
          <input
            type="file"
            multiple
            accept="application/pdf,image/png,image/jpeg"
            disabled={docBusy || needsInstitution}
            onChange={(e) => uploadDocuments(e.target.files)}
            className="block text-sm"
          />
          {docBusy && <p className="text-sm text-blue-700">Attaching files…</p>}
          {docError && <Notice kind="error">{docError}</Notice>}
          {docResult && (
            <div className="space-y-3">
              <p className="text-sm text-slate-700">
                <span className="font-medium text-emerald-700">{docResult.attached} attached</span>,{" "}
                <span className="font-medium text-amber-700">{docResult.unmatched} with no matching FDR</span>,{" "}
                <span className="font-medium text-red-700">{docResult.rejected} rejected</span>.
              </p>
              <ul className="divide-y divide-slate-100 text-sm">
                {docResult.results.map((r, i) => (
                  <li key={`${r.filename}-${i}`} className="flex flex-wrap justify-between gap-2 py-2">
                    <span className="font-medium">{r.filename}</span>
                    <span className={r.status === "attached" ? "text-emerald-700" : r.status === "unmatched" ? "text-amber-700" : "text-red-700"}>
                      {r.status === "attached" ? "Attached" : r.reason}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}
