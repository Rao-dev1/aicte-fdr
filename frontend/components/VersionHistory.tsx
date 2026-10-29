"use client";

import { useEffect, useState } from "react";
import { api, apiUpload, Comparison, dateTime, Doc, downloadFile, fetchBlob } from "@/lib/api";
import { Notice } from "@/components/Shell";

const inputClass = "rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm";

function PreviewFrame({ docId, filename, contentType }: { docId: number; filename: string; contentType: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let created: string | null = null;
    let cancelled = false;
    fetchBlob(`/documents/${docId}/download`)
      .then((blob) => {
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setUrl(created);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load file"));
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [docId]);

  return (
    <div className="min-w-0 flex-1">
      <p className="mb-2 truncate text-xs font-medium text-slate-600">{filename}</p>
      {error && <Notice kind="error">{error}</Notice>}
      {!url && !error && <p className="text-sm text-slate-500">Loading…</p>}
      {url && contentType.startsWith("image/") && <img src={url} alt={filename} className="max-h-[70vh] w-full rounded-lg border object-contain" />}
      {url && contentType === "application/pdf" && <iframe src={url} title={filename} className="h-[70vh] w-full rounded-lg border" />}
    </div>
  );
}

export function VersionHistory({
  depositId,
  doc,
  canUpload,
  onChanged,
}: {
  depositId: number;
  doc: Doc;
  canUpload: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState<Doc[]>([]);
  const [left, setLeft] = useState<number | null>(null);
  const [right, setRight] = useState<number | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadVersions() {
    try {
      const list = await api<Doc[]>(`/documents/${doc.id}/versions`);
      setVersions(list);
      if (list.length >= 2) {
        setLeft(list[list.length - 2].id);
        setRight(list[list.length - 1].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load versions");
    }
  }

  useEffect(() => {
    if (open) loadVersions();
  }, [open, doc.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function compare() {
    if (left === null || right === null) return;
    setBusy(true);
    setError(null);
    try {
      setComparison(await api<Comparison>(`/documents/compare?a=${left}&b=${right}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not compare");
    } finally {
      setBusy(false);
    }
  }

  async function uploadNewVersion(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await apiUpload(`/deposits/${depositId}/documents/${doc.id}/versions`, file);
      setMessage("New version uploaded. Earlier versions are kept.");
      setComparison(null);
      await loadVersions();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const leftDoc = versions.find((v) => v.id === left);
  const rightDoc = versions.find((v) => v.id === right);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-sm text-blue-700 hover:underline">
        Versions
      </button>
    );
  }

  return (
    <div className="mt-2 w-full space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
      <div className="flex items-center justify-between">
        <p className="font-medium">Version history</p>
        <button onClick={() => setOpen(false)} className="text-slate-600 hover:underline">
          Close
        </button>
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {message && <Notice kind="ok">{message}</Notice>}

      <ul className="divide-y divide-slate-200">
        {versions.map((v) => (
          <li key={v.id} className="flex items-center justify-between py-2">
            <span>
              <span className="font-medium">v{v.version ?? 1}</span> · {v.filename} · {dateTime(v.uploaded_at)} · {v.uploaded_by}
            </span>
            <button onClick={() => downloadFile(`/documents/${v.id}/download`, v.filename)} className="text-blue-700 hover:underline">
              Download
            </button>
          </li>
        ))}
      </ul>

      {canUpload && (
        <label className="inline-block cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-2 hover:bg-slate-100">
          {busy ? "Uploading…" : "Upload new version"}
          <input type="file" accept="application/pdf,image/png,image/jpeg" className="hidden" disabled={busy} onChange={(e) => uploadNewVersion(e.target.files?.[0])} />
        </label>
      )}

      {versions.length >= 2 && (
        <div className="space-y-3 border-t border-slate-200 pt-4">
          <p className="font-medium">Compare two versions</p>
          <div className="flex flex-wrap items-center gap-2">
            <select className={inputClass} value={left ?? ""} onChange={(e) => setLeft(Number(e.target.value))}>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>v{v.version ?? 1}</option>
              ))}
            </select>
            <span className="text-slate-500">with</span>
            <select className={inputClass} value={right ?? ""} onChange={(e) => setRight(Number(e.target.value))}>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>v{v.version ?? 1}</option>
              ))}
            </select>
            <button onClick={compare} disabled={busy || left === right} className="rounded-lg bg-[#0f2d52] px-3 py-1.5 text-white hover:bg-[#123a6b] disabled:opacity-60">
              Compare
            </button>
          </div>

          {comparison && (
            <div className="space-y-4">
              {comparison.identical_values ? (
                <Notice kind="ok">Both versions have the same recorded values.</Notice>
              ) : (
                <table className="w-full overflow-hidden rounded-lg border border-slate-200 bg-white text-left">
                  <thead className="bg-slate-100 text-xs uppercase text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Field</th>
                      <th className="px-3 py-2">Earlier</th>
                      <th className="px-3 py-2">Later</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.changes.map((c) => (
                      <tr key={c.field} className="border-t border-slate-100">
                        <td className="px-3 py-2 font-medium">{c.field.replace(/_/g, " ")}</td>
                        <td className="px-3 py-2 text-red-700">{c.old ?? "—"}</td>
                        <td className="px-3 py-2 text-emerald-700">{c.new ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <div className="flex flex-col gap-4 md:flex-row">
                {leftDoc && <PreviewFrame docId={leftDoc.id} filename={leftDoc.filename} contentType={leftDoc.content_type} />}
                {rightDoc && <PreviewFrame docId={rightDoc.id} filename={rightDoc.filename} contentType={rightDoc.content_type} />}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
