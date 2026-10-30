"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Notice, PageTitle, Shell, StatusBadge } from "@/components/Shell";
import { api, dateOnly, Deposit, DepositPage, downloadFile, GROUPS, Institution, getSession, money } from "@/lib/api";

const EXPORT_ROLES = ["REGULATOR_OFFICER", "APPROVING_AUTHORITY", "ADMIN"];
const PAGE_SIZE = 20;

function DepositsList() {
  const router = useRouter();
  const params = useSearchParams();
  const group = params.get("group") ?? "all";
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DepositPage | null>(null);
  const [institutions, setInstitutions] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [canExport, setCanExport] = useState(false);
  const [canCreate, setCanCreate] = useState(false);

  useEffect(() => {
    const role = getSession()?.role;
    setCanExport(role !== undefined && EXPORT_ROLES.includes(role));
    setCanCreate(role === "INSTITUTION_USER" || role === "ADMIN");
    api<Institution[]>("/institutions")
      .then((list) => setInstitutions(Object.fromEntries(list.map((i) => [i.id, i.name]))))
      .catch(() => setInstitutions({}));
  }, []);

  const load = useCallback(async () => {
    try {
      setData(await api<DepositPage>(`/deposits?group=${group}&page=${page}&page_size=${PAGE_SIZE}`));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load deposits");
    }
  }, [group, page]);

  useEffect(() => {
    setPage(1);
  }, [group]);

  useEffect(() => {
    load();
  }, [load]);

  async function exportReport(fmt: "csv" | "xlsx" | "pdf") {
    try {
      await downloadFile(`/reports/deposits?group=${group}&format=${fmt}`, `fdr-${group}.${fmt}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Shell>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageTitle title="Deposits" subtitle="Filter by status and export the list." />
        <div className="flex flex-wrap gap-2">
          {canExport &&
            (["xlsx", "pdf", "csv"] as const).map((fmt) => (
              <button
                key={fmt}
                onClick={() => exportReport(fmt)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50"
              >
                Export {fmt === "xlsx" ? "Excel" : fmt.toUpperCase()}
              </button>
            ))}
          {canCreate && (
            <Link href="/deposits/new" className="rounded-lg bg-[#0c2340] px-4 py-1.5 text-xs font-bold text-white shadow-xs transition hover:bg-[#123a6b]">
              + New FDR
            </Link>
          )}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {GROUPS.map((g) => (
          <button
            key={g.key}
            onClick={() => router.push(`/deposits?group=${g.key}`)}
            className={`rounded-full px-3.5 py-1 text-xs font-semibold transition ${
              group === g.key
                ? "bg-[#0c2340] text-white shadow-xs"
                : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            {g.label}
          </button>
        ))}
      </div>

      {error && <Notice kind="error">{error}</Notice>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-xs">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-4 py-3">FDR number</th>
              <th className="px-4 py-3">Institution</th>
              <th className="px-4 py-3">Bank</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Maturity</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((d: Deposit) => (
              <tr key={d.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link href={`/deposits/${d.id}`} className="font-medium text-blue-700 hover:underline">
                    {d.reference_no}
                  </Link>
                  {d.mismatch_fields.length > 0 && <span className="ml-2 text-xs text-red-600">mismatch</span>}
                </td>
                <td className="px-4 py-3">{institutions[d.institution_id] ?? `#${d.institution_id}`}</td>
                <td className="px-4 py-3">{d.bank_name}</td>
                <td className="px-4 py-3">{money(d.amount)}</td>
                <td className="px-4 py-3">{dateOnly(d.confirmed_maturity_date ?? d.maturity_date)}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={d.status} />
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No deposits in this view.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages} · {data.total} total
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </Shell>
  );
}

export default function DepositsPage() {
  return (
    <Suspense fallback={null}>
      <DepositsList />
    </Suspense>
  );
}
