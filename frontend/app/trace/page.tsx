"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Shell, PageTitle, StatusBadge, Notice } from "@/components/Shell";
import { api, money, dateOnly } from "@/lib/api";

type TraceSearchItem = {
  id: number;
  reference_no: string;
  bank_name: string;
  amount: number;
  status: string;
  issue_date: string;
  maturity_date: string;
  institution_id: number;
  has_predecessor: boolean;
  previous_deposit_id: number | null;
};

export default function TraceIndexPage() {
  const [items, setItems] = useState<TraceSearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [bankFilter, setBankFilter] = useState("");

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (statusFilter) params.set("status", statusFilter);
      if (bankFilter.trim()) params.set("bank_name", bankFilter.trim());
      params.set("page_size", "50");

      const res = await api<{ items: TraceSearchItem[]; total: number }>(`/trace/search?${params.toString()}`);
      setItems(res.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load trace records");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    loadData();
  }

  return (
    <Shell>
      <PageTitle
        title="FDR TRACE — Complete Lifecycle & Lineage"
        subtitle="End-to-end traceability, lineage relationship tracking, and append-only event journals for AICTE Security Deposits"
      />

      {error && <Notice kind="error">{error}</Notice>}

      {/* Info Banner */}
      <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50/60 p-4 text-sm text-blue-900 shadow-sm">
        <div className="flex items-start gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white">
            <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
          </span>
          <div>
            <p className="font-semibold text-blue-950">Unified FDR Lineage Architecture</p>
            <p className="mt-0.5 text-xs text-blue-800">
              Every FDR record maintains an append-only cryptographic event journal and explicit predecessor-successor
              lineage links (Originals, Renewals, Replacements, and Releases). Select any FDR record below to inspect its
              lineage graph and chronological audit trail.
            </p>
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <form onSubmit={handleSearch} className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div>
            <label className="block text-xs font-medium text-slate-700">FDR Reference / Keyword</label>
            <input
              type="text"
              placeholder="e.g. FDR-2025 or SBI..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700">Filter by Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">All Statuses</option>
              <option value="SUBMITTED">Submitted</option>
              <option value="VERIFIED">Verified</option>
              <option value="ACTIVE">Active</option>
              <option value="EXPIRING">Expiring</option>
              <option value="MATURED">Matured</option>
              <option value="RENEWED">Renewed</option>
              <option value="RELEASE_REQUESTED">Release Requested</option>
              <option value="RELEASED">Released</option>
              <option value="DISCREPANCY">Discrepancy</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700">Bank Name</label>
            <input
              type="text"
              placeholder="e.g. State Bank of India"
              value={bankFilter}
              onChange={(e) => setBankFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="w-full rounded-lg bg-[#0f2d52] px-4 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-[#1a3d6b]"
            >
              Filter Records
            </button>
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setStatusFilter("");
                setBankFilter("");
                loadData();
              }}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              Reset
            </button>
          </div>
        </form>
      </div>

      {/* Table Results */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-slate-50/70 px-5 py-3.5">
          <h2 className="text-sm font-semibold text-slate-900">
            FDR Records with Lineage Tracking ({items.length})
          </h2>
        </div>

        {loading ? (
          <div className="p-10 text-center text-sm text-slate-500">Loading trace records…</div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">
            No FDR records found matching current criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50/50 text-xs font-semibold uppercase tracking-wider text-slate-600">
                <tr>
                  <th className="px-5 py-3">FDR Reference</th>
                  <th className="px-4 py-3">Bank</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">Maturity Date</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Lineage Position</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr key={item.id} className="transition-colors hover:bg-blue-50/30">
                    <td className="px-5 py-3.5 font-medium text-slate-900">
                      <Link
                        href={`/deposits/${item.id}#trace`}
                        className="font-mono text-blue-700 hover:text-blue-900 hover:underline"
                      >
                        {item.reference_no}
                      </Link>
                    </td>
                    <td className="px-4 py-3.5 text-slate-700">{item.bank_name}</td>
                    <td className="px-4 py-3.5 font-medium text-slate-900">{money(item.amount)}</td>
                    <td className="px-4 py-3.5 text-slate-600">{dateOnly(item.maturity_date)}</td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3.5">
                      {item.has_predecessor ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-purple-50 px-2 py-0.5 text-xs font-semibold text-purple-700 border border-purple-200">
                          Successor (from #{item.previous_deposit_id})
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                          Root / Original Deposit
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        href={`/deposits/${item.id}#trace`}
                        className="inline-flex items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-medium text-[#0f2d52] border border-slate-300 hover:bg-slate-50"
                      >
                        Inspect TRACE →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Shell>
  );
}
