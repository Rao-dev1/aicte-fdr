"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import { api, CalEvent } from "@/lib/api";

function ymd(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function CalendarPage() {
  // The current date is read in the browser only, so the page can be prerendered safely.
  const [month, setMonth] = useState<Date | null>(null);
  const [todayKey, setTodayKey] = useState("");
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const now = new Date();
    setTodayKey(ymd(now));
    setMonth(new Date(now.getFullYear(), now.getMonth(), 1));
  }, []);

  const days = useMemo(() => {
    if (!month) return [];
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const lead = (first.getDay() + 6) % 7; // Monday first
    const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    const cells: (Date | null)[] = Array(lead).fill(null);
    for (let i = 1; i <= count; i++) cells.push(new Date(month.getFullYear(), month.getMonth(), i));
    while (cells.length % 7 !== 0) cells.push(null);
    return cells;
  }, [month]);

  useEffect(() => {
    if (!month) return;
    const start = ymd(new Date(month.getFullYear(), month.getMonth(), 1));
    const end = ymd(new Date(month.getFullYear(), month.getMonth() + 1, 0));
    api<CalEvent[]>(`/calendar?start=${start}&end=${end}`)
      .then((list) => {
        setEvents(list);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load calendar"));
  }, [month]);

  const byDay = useMemo(() => {
    const map: Record<string, CalEvent[]> = {};
    for (const e of events) (map[e.on_date] ??= []).push(e);
    return map;
  }, [events]);

  const label = month ? month.toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : "";

  return (
    <Shell>
      <PageTitle title="Maturity calendar" subtitle="Maturity dates and renewals due. Renewal-due items are highlighted." />

      {error && <Notice kind="error">{error}</Notice>}

      <div className="mb-4 flex items-center justify-between">
        <button
          disabled={!month}
          onClick={() => month && setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-white disabled:opacity-40"
        >
          ← Previous
        </button>
        <h2 className="font-semibold">{label}</h2>
        <button
          disabled={!month}
          onClick={() => month && setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-white disabled:opacity-40"
        >
          Next →
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="grid min-w-[640px] grid-cols-7 border-b border-slate-200 bg-slate-50 text-center text-xs font-medium text-slate-600">
          {WEEKDAYS.map((w) => (
            <div key={w} className="py-2">
              {w}
            </div>
          ))}
        </div>
        <div className="grid min-w-[640px] grid-cols-7">
          {days.map((day, i) => {
            if (!day) return <div key={`empty-${i}`} className="min-h-28 border-b border-r border-slate-100 bg-slate-50/50" />;
            const key = ymd(day);
            const dayEvents = byDay[key] ?? [];
            const isToday = key === todayKey;
            return (
              <div key={key} className="min-h-28 border-b border-r border-slate-100 p-1.5">
                <p className={`text-xs ${isToday ? "inline-block rounded-full bg-blue-600 px-1.5 text-white" : "text-slate-500"}`}>{day.getDate()}</p>
                <ul className="mt-1 space-y-1">
                  {dayEvents.map((e) => (
                    <li key={`${e.deposit_id}-${e.on_date}`}>
                      <Link
                        href={`/deposits/${e.deposit_id}`}
                        className={`block truncate rounded px-1.5 py-0.5 text-xs ${
                          e.renewal_due ? "bg-amber-100 text-amber-900 hover:bg-amber-200" : "bg-blue-50 text-blue-800 hover:bg-blue-100"
                        }`}
                        title={`${e.reference_no} · ${e.status}`}
                      >
                        {e.renewal_due ? "Renew: " : "Matures: "}
                        {e.reference_no}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-500">Amber items are expiring or matured and still need renewal or release.</p>
    </Shell>
  );
}
