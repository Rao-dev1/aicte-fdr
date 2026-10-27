"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { clearSession, getSession, ROLE_LABELS, Role, Session } from "@/lib/api";

type NavItem = { href: string; label: string };

const COMMON: NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/deposits", label: "Deposits" },
  { href: "/calendar", label: "Calendar" },
  { href: "/notifications", label: "Notifications" },
];

const NAV: Record<Role, NavItem[]> = {
  INSTITUTION_USER: [...COMMON.slice(0, 2), { href: "/deposits/new", label: "New FDR" }, ...COMMON.slice(2)],
  REGULATOR_OFFICER: COMMON,
  APPROVING_AUTHORITY: [...COMMON.slice(0, 2), { href: "/approvals", label: "Approvals" }, ...COMMON.slice(2)],
  ADMIN: [...COMMON.slice(0, 2), { href: "/deposits/new", label: "New FDR" }, { href: "/approvals", label: "Approvals" }, ...COMMON.slice(2)],
};

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSessionState] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const current = getSession();
    if (!current) {
      router.replace("/login");
    } else {
      setSessionState(current);
    }
    setReady(true);
  }, [router]);

  if (!ready) return <div className="p-10 text-slate-500">Loading…</div>;
  if (!session) return null;

  function signOut() {
    clearSession();
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-slate-200 bg-white md:w-60 md:border-b-0 md:border-r">
        <div className="p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">AICTE FDR Portal</p>
          <p className="mt-1 text-sm font-medium">{session.user}</p>
          <p className="text-xs text-slate-500">{ROLE_LABELS[session.role]}</p>
        </div>
        <nav className="flex flex-wrap gap-1 px-3 pb-4 md:flex-col">
          {NAV[session.role].map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-2 text-sm ${
                  active ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <button onClick={signOut} className="rounded-lg px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-100">
            Sign out
          </button>
        </nav>
      </aside>
      <main className="flex-1 p-4 sm:p-6 md:p-10">{children}</main>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const style = {
    SUBMITTED: "bg-blue-100 text-blue-800",
    VERIFIED: "bg-sky-100 text-sky-800",
    DISCREPANCY: "bg-red-100 text-red-800",
    ACTIVE: "bg-emerald-100 text-emerald-800",
    EXPIRING: "bg-amber-100 text-amber-800",
    MATURED: "bg-orange-100 text-orange-800",
    RENEWED: "bg-slate-200 text-slate-700",
    RELEASE_REQUESTED: "bg-violet-100 text-violet-800",
    RELEASED: "bg-teal-100 text-teal-800",
    REJECTED: "bg-rose-100 text-rose-800",
  }[status] ?? "bg-slate-100 text-slate-700";
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>{status.replace(/_/g, " ")}</span>;
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
    </div>
  );
}

export function Notice({ kind, children }: { kind: "error" | "ok" | "info"; children: ReactNode }) {
  const style = {
    error: "border-red-200 bg-red-50 text-red-800",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
    info: "border-sky-200 bg-sky-50 text-sky-800",
  }[kind];
  return <div className={`mb-4 rounded-lg border px-4 py-3 text-sm ${style}`}>{children}</div>;
}
