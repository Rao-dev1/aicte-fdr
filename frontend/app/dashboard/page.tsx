"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Notice, PageTitle, Shell, StatusBadge } from "@/components/Shell";
import { api, Dashboard, DeadlineItem, DeadlinesResponse, dateOnly, getSession, money } from "@/lib/api";

type JobInfo = {
  schedule: string;
  runs: { id: number; trigger: string; status: string; started_at: string }[];
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [jobs, setJobs] = useState<JobInfo | null>(null);

  // FEATURE 1: Smart Deadlines & Expiry Alerts State
  const [deadlines, setDeadlines] = useState<DeadlinesResponse | null>(null);
  const [deadlineFilter, setDeadlineFilter] = useState<"all" | "expiring" | "overdue" | "pending_actions">("all");
  const [deadlineThreshold, setDeadlineThreshold] = useState<"all" | "30" | "15" | "7" | "overdue">("all");
  const [loadingDeadlines, setLoadingDeadlines] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api<Dashboard>("/dashboard/summary"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dashboard");
    }
    if (getSession()?.role === "ADMIN") {
      api<JobInfo>("/admin/jobs?limit=5")
        .then(setJobs)
        .catch(() => setJobs(null));
    }
  }, []);

  const loadDeadlines = useCallback(async () => {
    setLoadingDeadlines(true);
    try {
      const res = await api<DeadlinesResponse>(
        `/deadlines?filter=${deadlineFilter}&threshold=${deadlineThreshold}&limit=50`
      );
      setDeadlines(res);
    } catch (err) {
      console.error("Could not load deadlines", err);
    } finally {
      setLoadingDeadlines(false);
    }
  }, [deadlineFilter, deadlineThreshold]);

  useEffect(() => {
    setIsAdmin(getSession()?.role === "ADMIN");
    load();
  }, [load]);

  useEffect(() => {
    loadDeadlines();
  }, [loadDeadlines]);

  async function runSweep() {
    try {
      const result = await api<{ status: string; changed?: number; notifications_created?: number; error?: string }>(
        "/admin/lifecycle-sweep",
        { method: "POST" },
      );
      if (result.status === "OK") {
        setMessage(`Daily check completed: ${result.changed} status changes, ${result.notifications_created} reminders generated.`);
      } else {
        setError(`Daily check failed: ${result.error ?? "unknown error"}`);
      }
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Daily check failed");
    }
  }

  // Calculate high-level summary KPI counts
  const totalSubmissions = data?.total ?? 0;
  const underVerification = (data?.counts["SUBMITTED"] ?? 0) + (data?.counts["RELEASE_REQUESTED"] ?? 0);
  const approvedActive = (data?.counts["VERIFIED"] ?? 0) + (data?.counts["ACTIVE"] ?? 0) + (data?.counts["RELEASED"] ?? 0);
  const pendingClarifications = (data?.counts["DISCREPANCY"] ?? 0) + (data?.counts["EXPIRING"] ?? 0) + (data?.counts["MATURED"] ?? 0);

  // Donut chart distribution
  const pieData = data
    ? [
        { name: "Approved / Active", value: approvedActive, color: "#10b981" },
        { name: "Under Verification", value: underVerification, color: "#f59e0b" },
        { name: "Clarification / Action", value: pendingClarifications, color: "#ef4444" },
      ].filter((d) => d.value > 0)
    : [];

  return (
    <Shell>
      <PageTitle
        title="Dashboard"
        subtitle="Real-time oversight of institutional security deposits, verification stages, and compliance."
      />

      {error && <Notice kind="error">{error}</Notice>}
      {message && <Notice kind="ok">{message}</Notice>}

      {/* 1. Official AICTE Welcome Banner (Option 2/3 Reference) */}
      <section className="relative mb-6 overflow-hidden rounded-xl bg-gradient-to-r from-[#0c2340] via-[#10325c] to-[#0f2d52] p-6 text-white shadow-sm sm:p-8">
        <div className="relative z-10 flex flex-col justify-between gap-6 md:flex-row md:items-center">
          <div className="max-w-xl">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-white/10 px-2.5 py-1 text-xs font-semibold text-[#f59e0b]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#f59e0b]" />
              National Technical Education Portal
            </span>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl leading-snug">
              Welcome to AICTE FDR Management Portal
            </h2>
            <p className="mt-2 text-xs sm:text-sm text-blue-100/90 leading-relaxed">
              Ensure compliance. Enable transparency. Simplify processes. Monitor deposits, track scrutiny, and verify statutory liens.
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Link
                href="/deposits/new"
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#f59e0b] px-4 py-2 text-xs font-bold text-[#0f172a] shadow-xs transition hover:bg-[#d97706]"
              >
                <span>+ Submit New FDR</span>
              </Link>
              <Link
                href="/deposits"
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 bg-white/10 px-4 py-2 text-xs font-medium text-white transition hover:bg-white/20"
              >
                <span>View All Deposits →</span>
              </Link>
            </div>
          </div>

          {/* Right Side: Building Artwork in Welcome Banner */}
          <div className="relative hidden shrink-0 md:block">
            <div className="relative h-32 w-52 overflow-hidden rounded-lg border border-white/10 shadow-md">
              <Image
                src="/assets/aicte_building_hero.png"
                alt="AICTE Headquarters"
                fill
                className="object-cover"
                priority
              />
              <div className="absolute inset-0 bg-gradient-to-t from-[#0c2340]/60 via-transparent to-transparent" />
            </div>
          </div>
        </div>
      </section>

      {/* 2. Four Primary Stat KPI Cards */}
      <section className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: Total Submissions */}
        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Submissions</p>
            <h3 className="mt-0.5 text-2xl font-bold text-[#0c2340]">{totalSubmissions}</h3>
          </div>
        </div>

        {/* Card 2: Under Verification */}
        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Under Verification</p>
            <h3 className="mt-0.5 text-2xl font-bold text-[#0c2340]">{underVerification}</h3>
          </div>
        </div>

        {/* Card 3: Approved / Active */}
        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Approved / Active</p>
            <h3 className="mt-0.5 text-2xl font-bold text-[#0c2340]">{approvedActive}</h3>
          </div>
        </div>

        {/* Card 4: Action / Clarifications */}
        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-700">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Action Required</p>
            <h3 className="mt-0.5 text-2xl font-bold text-[#0c2340]">{pendingClarifications}</h3>
          </div>
        </div>
      </section>

      {/* 3. Main Grid: Recent Submissions & Application Status Overview */}
      <div className="mb-8 grid gap-6 lg:grid-cols-12">
        {/* Left: FEATURE 1: Smart Deadline & Expiry Alerts Widget (8 cols) */}
        <div className="lg:col-span-8">
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            {/* Widget Title & Real-Time Indicators */}
            <div className="flex flex-col justify-between gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-center">
              <div>
                <div className="flex items-center gap-2">
                  <span className="flex h-2 w-2 rounded-full bg-blue-600" />
                  <h3 className="text-base font-bold text-[#0c2340]">Upcoming Deadlines & Expiry Alerts</h3>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Dynamic monitoring of FDR maturities, required renewals, and pending scrutiny actions.
                </p>
              </div>

              {/* Summary Counter Pills */}
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="rounded-md bg-slate-100 px-2.5 py-0.5 font-bold text-slate-700">
                  Total: {deadlines?.summary.total ?? 0}
                </span>
                <span className="rounded-md bg-red-50 border border-red-200 px-2.5 py-0.5 font-bold text-red-700">
                  Overdue: {deadlines?.summary.overdue ?? 0}
                </span>
                <span className="rounded-md bg-amber-50 border border-amber-200 px-2.5 py-0.5 font-bold text-amber-700">
                  Due Soon: {deadlines?.summary.due_soon ?? 0}
                </span>
                <span className="rounded-md bg-blue-50 border border-blue-200 px-2.5 py-0.5 font-bold text-blue-700">
                  Upcoming: {deadlines?.summary.upcoming ?? 0}
                </span>
              </div>
            </div>

            {/* Filter Tabs & Threshold Dropdown */}
            <div className="mt-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              {/* Category Filter Tabs */}
              <div className="flex flex-wrap items-center gap-1.5">
                {[
                  { id: "all", label: "All Deadlines" },
                  { id: "expiring", label: "Expiring FDRs" },
                  { id: "overdue", label: "Overdue Tasks" },
                  { id: "pending_actions", label: "My Pending Actions" },
                ].map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setDeadlineFilter(f.id as any)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                      deadlineFilter === f.id
                        ? "bg-[#0c2340] text-white shadow-xs"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {/* Alert Threshold Selector */}
              <div className="flex items-center gap-2">
                <label htmlFor="threshold-select" className="text-xs font-medium text-slate-500 shrink-0">
                  Threshold:
                </label>
                <select
                  id="threshold-select"
                  value={deadlineThreshold}
                  onChange={(e) => setDeadlineThreshold(e.target.value as any)}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 outline-none focus:border-blue-600"
                >
                  <option value="all">All Windows</option>
                  <option value="30">Within 30 Days (Standard)</option>
                  <option value="15">Within 15 Days (Urgent)</option>
                  <option value="7">Within 7 Days (Critical)</option>
                  <option value="overdue">Overdue (&lt; 0 Days)</option>
                </select>
              </div>
            </div>

            {/* Deadlines Table */}
            <div className="mt-4 overflow-x-auto">
              {loadingDeadlines ? (
                <div className="py-8 text-center text-xs text-slate-500">Recalculating deadlines from underlying dates…</div>
              ) : deadlines && deadlines.items.length > 0 ? (
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
                    <tr>
                      <th className="px-3.5 py-2.5">FDR & Institution</th>
                      <th className="px-3.5 py-2.5">Deadline & Action</th>
                      <th className="px-3.5 py-2.5">Target Date</th>
                      <th className="px-3.5 py-2.5">Remaining Days</th>
                      <th className="px-3.5 py-2.5">Status</th>
                      <th className="px-3.5 py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {deadlines.items.map((item) => {
                      const isOverdue = item.urgency === "overdue";
                      const isDueSoon = item.urgency === "due_soon";
                      const isCompleted = item.urgency === "completed";

                      return (
                        <tr key={item.alert_id} className="transition hover:bg-slate-50/70">
                          <td className="px-3.5 py-3">
                            <Link href={item.url} className="font-semibold text-slate-900 hover:text-blue-700 hover:underline">
                              {item.reference_no}
                            </Link>
                            <p className="text-[11px] text-slate-500 truncate max-w-[180px]">
                              {item.institution_name} ({item.institution_code})
                            </p>
                          </td>

                          <td className="px-3.5 py-3">
                            <span className="font-medium text-slate-800">{item.deadline_label}</span>
                            <p className="text-[10px] text-slate-400 uppercase tracking-wider">{item.deadline_type.replace("_", " ")}</p>
                          </td>

                          <td className="px-3.5 py-3 text-slate-600">
                            {dateOnly(item.deadline_date)}
                          </td>

                          <td className="px-3.5 py-3">
                            {isCompleted ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                                Resolved
                              </span>
                            ) : isOverdue ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-red-50 border border-red-200 px-2.5 py-0.5 text-[11px] font-semibold text-red-700">
                                {Math.abs(item.days_left)}d overdue
                              </span>
                            ) : isDueSoon ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 border border-amber-200 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700">
                                {item.days_left}d left {item.days_left <= 7 ? "(Critical)" : ""}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 border border-blue-200 px-2.5 py-0.5 text-[11px] font-semibold text-blue-700">
                                {item.days_left}d left
                              </span>
                            )}
                          </td>

                          <td className="px-3.5 py-3">
                            <StatusBadge status={item.status} />
                          </td>

                          <td className="px-3.5 py-3 text-right">
                            <Link
                              href={item.url}
                              className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                                item.is_my_action
                                  ? "bg-[#0c2340] text-white hover:bg-[#123a6b]"
                                  : "text-blue-700 hover:underline"
                              }`}
                            >
                              {item.is_my_action ? "Act Now →" : "View →"}
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="py-10 text-center text-xs text-slate-500">
                  <p className="font-semibold text-slate-700">No deadline alerts found matching this filter.</p>
                  <p className="mt-1 text-slate-400">All regulatory dates and compliance milestones are within authorized time limits.</p>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* Right: Application Status Overview Donut Chart (4 cols) */}
        <div className="lg:col-span-4">
          <section className="flex h-full flex-col justify-between rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <div>
              <h3 className="text-base font-bold text-[#0c2340]">Application Status Overview</h3>
              <p className="text-xs text-slate-500">Distribution across verification stages</p>
            </div>

            <div className="relative my-4 flex h-52 items-center justify-center">
              {pieData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={80}
                      paddingAngle={3}
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-slate-400">
                  Awaiting deposits
                </div>
              )}

              {/* Center Donut Value */}
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-[#0c2340]">{totalSubmissions}</span>
                <span className="text-[10px] font-semibold uppercase text-slate-400">Total FDRs</span>
              </div>
            </div>

            {/* Donut Legend */}
            <div className="space-y-1.5 border-t border-slate-100 pt-3 text-xs">
              <div className="flex items-center justify-between text-slate-700">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  <span>Approved / Active</span>
                </span>
                <span className="font-bold">{approvedActive}</span>
              </div>
              <div className="flex items-center justify-between text-slate-700">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                  <span>Under Verification</span>
                </span>
                <span className="font-bold">{underVerification}</span>
              </div>
              <div className="flex items-center justify-between text-slate-700">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
                  <span>Action / Clarification</span>
                </span>
                <span className="font-bold">{pendingClarifications}</span>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* 4. Admin Scheduled Job Automation Panel */}
      {isAdmin && (
        <section className="mb-6 rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-purple-700">
                System Administration
              </span>
              <h3 className="text-base font-bold text-[#0c2340]">Daily Maturity Sweep & Notification Engine</h3>
              <p className="mt-0.5 text-xs text-slate-500">
                Automated scheduler running daily at {jobs?.schedule ?? "08:00 Indian Standard Time (IST)"}.
              </p>
            </div>
            <button
              onClick={runSweep}
              className="rounded-lg bg-[#0c2340] px-4 py-2 text-xs font-bold text-white shadow-xs transition hover:bg-[#123a6b]"
            >
              Trigger Manual Sweep Now
            </button>
          </div>

          {jobs && jobs.runs.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-700">Recent Automatic Execution History:</p>
              <div className="mt-2 divide-y divide-slate-100 text-xs">
                {jobs.runs.map((r) => (
                  <div key={r.id} className="flex items-center justify-between py-2">
                    <span className="text-slate-600">
                      {new Date(r.started_at).toLocaleString("en-IN")} · Trigger: <span className="font-semibold text-slate-800">{r.trigger}</span>
                    </span>
                    <span
                      className={`font-bold ${
                        r.status === "OK" ? "text-emerald-700" : "text-red-700"
                      }`}
                    >
                      {r.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </Shell>
  );
}
