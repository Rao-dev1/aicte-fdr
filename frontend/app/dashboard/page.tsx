"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Notice, PageTitle, Shell, StatusBadge } from "@/components/Shell";
// StatusBadge is used by nothing here now; keep the import list honest.
import { api, Dashboard, dateOnly, getSession, money } from "@/lib/api";

const CARDS: { key: string; label: string; statuses: string[] }[] = [
  { key: "active", label: "Active", statuses: ["ACTIVE", "VERIFIED"] },
  { key: "expiring", label: "Expiring (30 days)", statuses: ["EXPIRING"] },
  { key: "matured", label: "Matured", statuses: ["MATURED"] },
  { key: "released", label: "Released", statuses: ["RELEASED"] },
  { key: "pending", label: "Pending", statuses: ["SUBMITTED", "DISCREPANCY", "RELEASE_REQUESTED"] },
];

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api<Dashboard>("/dashboard/summary"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dashboard");
    }
  }, []);

  useEffect(() => {
    setIsAdmin(getSession()?.role === "ADMIN");
    load();
  }, [load]);

  async function runSweep() {
    try {
      const result = await api<{ changed: number; notifications_created: number }>("/admin/lifecycle-sweep", {
        method: "POST",
      });
      setMessage(`Daily check done: ${result.changed} status changes, ${result.notifications_created} new reminders.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Daily check failed");
    }
  }

  const chartData = data
    ? Object.entries(data.counts)
        .filter(([, count]) => count > 0)
        .map(([status, count]) => ({ status: status.replace(/_/g, " "), count }))
    : [];

  const upcomingData = data?.upcoming.map((u) => ({ name: u.reference_no, days: u.days_left })) ?? [];

  return (
    <Shell>
      <PageTitle title="Dashboard" subtitle="Status of every security deposit and FDR in the system." />

      {error && <Notice kind="error">{error}</Notice>}
      {message && <Notice kind="ok">{message}</Notice>}

      {isAdmin && (
        <button onClick={runSweep} className="mb-6 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50">
          Run daily maturity check
        </button>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            {CARDS.map((card) => {
              const count = card.statuses.reduce((sum, s) => sum + (data.counts[s] ?? 0), 0);
              return (
                <Link
                  key={card.key}
                  href={`/deposits?group=${card.key}`}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-indigo-300"
                >
                  <p className="text-sm text-slate-600">{card.label}</p>
                  <p className="mt-2 text-3xl font-bold">{count}</p>
                </Link>
              );
            })}
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-sm text-slate-600">Total deposits</p>
              <p className="mt-2 text-3xl font-bold">{data.total}</p>
            </div>
            <Link href="/approvals" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-indigo-300">
              <p className="text-sm text-slate-600">Release requests awaiting approval</p>
              <p className="mt-2 text-3xl font-bold">{data.pending_approvals}</p>
            </Link>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">Status split</h2>
              <div className="mt-4 h-72">
                {chartData.length === 0 ? (
                  <p className="text-sm text-slate-500">No deposits yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="status" tick={{ fontSize: 11 }} interval={0} angle={-25} textAnchor="end" height={70} />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">Upcoming maturities (next 90 days)</h2>
              <div className="mt-4 h-72">
                {upcomingData.length === 0 ? (
                  <p className="text-sm text-slate-500">No maturities in the next 90 days.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={upcomingData} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v) => `${v} days left`} />
                      <Bar dataKey="days" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>
          </div>

          {data.upcoming.length > 0 && (
            <section className="mt-8 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-600">
                  <tr>
                    <th className="px-4 py-3">FDR</th>
                    <th className="px-4 py-3">Amount</th>
                    <th className="px-4 py-3">Maturity</th>
                    <th className="px-4 py-3">Days left</th>
                  </tr>
                </thead>
                <tbody>
                  {data.upcoming.map((u) => (
                    <tr key={u.deposit_id} className="border-t border-slate-100">
                      <td className="px-4 py-3">
                        <Link href={`/deposits/${u.deposit_id}`} className="text-indigo-700 hover:underline">
                          {u.reference_no}
                        </Link>
                      </td>
                      <td className="px-4 py-3">{money(u.amount)}</td>
                      <td className="px-4 py-3">{dateOnly(u.maturity_date)}</td>
                      <td className="px-4 py-3">
                        <span className={u.days_left <= 7 ? "text-red-700" : u.days_left <= 30 ? "text-amber-700" : ""}>
                          {u.days_left}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </Shell>
  );
}
