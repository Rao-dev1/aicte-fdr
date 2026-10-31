"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { clearSession, getSession, ROLE_LABELS, Role, Session } from "@/lib/api";

type NavItem = {
  href: string;
  label: string;
  icon: (active: boolean) => ReactNode;
};

// SVG Icons for Navigation
function IconDashboard({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  );
}

function IconDeposits({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  );
}

function IconNew({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function IconTrace({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  );
}

function IconIntegrity({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  );
}

function IconRegulations({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  );
}

function IconApprovals({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

function IconCalendar({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function IconNotifications({ active }: { active: boolean }) {
  return (
    <svg className={`h-4 w-4 shrink-0 ${active ? "text-[#f59e0b]" : "text-slate-300"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  );
}

const NAV: Record<Role, NavItem[]> = {
  INSTITUTION_USER: [
    { href: "/dashboard", label: "Dashboard", icon: (a) => <IconDashboard active={a} /> },
    { href: "/deposits", label: "Deposits", icon: (a) => <IconDeposits active={a} /> },
    { href: "/deposits/new", label: "New FDR", icon: (a) => <IconNew active={a} /> },
    { href: "/deposits/import", label: "Import FDRs", icon: (a) => <IconNew active={a} /> },
    { href: "/trace", label: "FDR Trace", icon: (a) => <IconTrace active={a} /> },
    { href: "/regulations", label: "Regulations & Replay", icon: (a) => <IconRegulations active={a} /> },
    { href: "/calendar", label: "Calendar", icon: (a) => <IconCalendar active={a} /> },
    { href: "/notifications", label: "Notifications", icon: (a) => <IconNotifications active={a} /> },
  ],
  REGULATOR_OFFICER: [
    { href: "/dashboard", label: "Dashboard", icon: (a) => <IconDashboard active={a} /> },
    { href: "/deposits", label: "Deposits", icon: (a) => <IconDeposits active={a} /> },
    { href: "/trace", label: "FDR Trace", icon: (a) => <IconTrace active={a} /> },
    { href: "/integrity", label: "Integrity Network", icon: (a) => <IconIntegrity active={a} /> },
    { href: "/regulations", label: "Regulations & Replay", icon: (a) => <IconRegulations active={a} /> },
    { href: "/calendar", label: "Calendar", icon: (a) => <IconCalendar active={a} /> },
    { href: "/notifications", label: "Notifications", icon: (a) => <IconNotifications active={a} /> },
  ],
  APPROVING_AUTHORITY: [
    { href: "/dashboard", label: "Dashboard", icon: (a) => <IconDashboard active={a} /> },
    { href: "/deposits", label: "Deposits", icon: (a) => <IconDeposits active={a} /> },
    { href: "/approvals", label: "Approvals", icon: (a) => <IconApprovals active={a} /> },
    { href: "/trace", label: "FDR Trace", icon: (a) => <IconTrace active={a} /> },
    { href: "/integrity", label: "Integrity Network", icon: (a) => <IconIntegrity active={a} /> },
    { href: "/regulations", label: "Regulations & Replay", icon: (a) => <IconRegulations active={a} /> },
    { href: "/calendar", label: "Calendar", icon: (a) => <IconCalendar active={a} /> },
    { href: "/notifications", label: "Notifications", icon: (a) => <IconNotifications active={a} /> },
  ],
  ADMIN: [
    { href: "/dashboard", label: "Dashboard", icon: (a) => <IconDashboard active={a} /> },
    { href: "/deposits", label: "Deposits", icon: (a) => <IconDeposits active={a} /> },
    { href: "/deposits/new", label: "New FDR", icon: (a) => <IconNew active={a} /> },
    { href: "/deposits/import", label: "Import FDRs", icon: (a) => <IconNew active={a} /> },
    { href: "/approvals", label: "Approvals", icon: (a) => <IconApprovals active={a} /> },
    { href: "/trace", label: "FDR Trace", icon: (a) => <IconTrace active={a} /> },
    { href: "/integrity", label: "Integrity Network", icon: (a) => <IconIntegrity active={a} /> },
    { href: "/regulations", label: "Regulations & Replay", icon: (a) => <IconRegulations active={a} /> },
    { href: "/calendar", label: "Calendar", icon: (a) => <IconCalendar active={a} /> },
    { href: "/notifications", label: "Notifications", icon: (a) => <IconNotifications active={a} /> },
  ],
};

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSessionState] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const current = getSession();
    if (!current) {
      router.replace("/login");
    } else {
      setSessionState(current);
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500 text-sm">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#0c2340] border-t-transparent" />
          <span>Loading portal…</span>
        </div>
      </div>
    );
  }

  if (!session) return null;

  function signOut() {
    clearSession();
    router.push("/login");
  }

  const roleTheme: Record<Role, { badge: string; text: string }> = {
    INSTITUTION_USER: { badge: "bg-blue-100 text-blue-800 border-blue-200", text: "text-blue-400" },
    REGULATOR_OFFICER: { badge: "bg-amber-100 text-amber-800 border-amber-200", text: "text-amber-400" },
    APPROVING_AUTHORITY: { badge: "bg-emerald-100 text-emerald-800 border-emerald-200", text: "text-emerald-400" },
    ADMIN: { badge: "bg-purple-100 text-purple-800 border-purple-200", text: "text-purple-400" },
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      {/* Official Government Top Header Bar */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white shadow-xs">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Logo & Council Titles */}
          <Link href="/" className="flex items-center gap-3 transition hover:opacity-90">
            <div className="relative h-10 w-10 shrink-0">
              <Image
                src="/assets/aicte_official_logo.png"
                alt="All India Council for Technical Education Logo"
                width={40}
                height={40}
                className="h-10 w-10 object-contain drop-shadow-xs"
                priority
              />
            </div>
            <div>
              <p className="text-sm font-bold tracking-tight text-[#0c2340] sm:text-base leading-tight">
                All India Council for Technical Education
              </p>
              <p className="text-[11px] font-medium text-slate-500 leading-tight">
                अखिल भारतीय तकनीकी शिक्षा परिषद · FDR Nyasa
              </p>
            </div>
          </Link>

          {/* Right Header Navigation & User Profile */}
          <div className="hidden items-center gap-4 md:flex">
            <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 shadow-xs">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#0c2340] text-xs font-semibold text-white uppercase">
                {session.user.charAt(0)}
              </span>
              <div className="text-left text-xs">
                <span className="font-semibold text-slate-900">{session.user}</span>
                <span className="mx-1 text-slate-400">·</span>
                <span className={`inline-block font-medium ${roleTheme[session.role].text}`}>
                  {ROLE_LABELS[session.role]}
                </span>
              </div>
            </div>

            <Link
              href="/trace"
              className="text-xs font-medium text-slate-600 hover:text-[#0c2340] hover:underline"
            >
              FDR Trace
            </Link>

            <Link
              href="/calendar"
              className="text-xs font-medium text-slate-600 hover:text-[#0c2340] hover:underline"
            >
              Calendar
            </Link>

            <button
              onClick={signOut}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-xs transition hover:bg-slate-50 hover:text-slate-900"
            >
              Sign out
            </button>
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            aria-label="Toggle navigation menu"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </header>

      {/* Main Container with Sidebar & Content */}
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col md:flex-row">
        {/* Navy Sidebar with Gold Active Indicator */}
        <aside
          className={`${
            mobileMenuOpen ? "block" : "hidden"
          } w-full shrink-0 border-r border-slate-800 bg-[#0c2340] text-white md:block md:w-64`}
        >
          <div className="p-4">
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Portal Navigation
            </p>
            <nav className="mt-2 space-y-1">
              {NAV[session.role].map((item) => {
                const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                      active
                        ? "border-l-3 border-[#f59e0b] bg-white/10 text-white font-semibold pl-2.5"
                        : "text-slate-300 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {item.icon(active)}
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="mt-auto border-t border-white/10 p-4">
            <div className="rounded-lg border border-white/10 bg-white/5 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[#f59e0b]">
                Active Authority
              </p>
              <p className="mt-0.5 text-xs font-semibold text-white">{ROLE_LABELS[session.role]}</p>
              <p className="text-[11px] text-slate-400 truncate">{session.user}</p>
            </div>
          </div>
        </aside>

        {/* Page Content Body */}
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>

      {/* Official Government Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <p>© 2026 All India Council for Technical Education (AICTE), Ministry of Education, Govt. of India.</p>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Nelson Mandela Marg, Vasant Kunj, New Delhi - 110070 · FDR Nyasa – Intelligent Institutional Deposit Management System
          </p>
        </div>
      </footer>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const style = {
    SUBMITTED: "bg-blue-50 text-blue-700 border-blue-200",
    VERIFIED: "bg-sky-50 text-sky-700 border-sky-200",
    DISCREPANCY: "bg-red-50 text-red-700 border-red-200",
    ACTIVE: "bg-emerald-50 text-emerald-700 border-emerald-200",
    EXPIRING: "bg-amber-50 text-amber-700 border-amber-200",
    MATURED: "bg-orange-50 text-orange-700 border-orange-200",
    RENEWED: "bg-slate-100 text-slate-700 border-slate-200",
    RELEASE_REQUESTED: "bg-purple-50 text-purple-700 border-purple-200",
    RELEASED: "bg-teal-50 text-teal-700 border-teal-200",
    REJECTED: "bg-rose-50 text-rose-700 border-rose-200",
  }[status] ?? "bg-slate-50 text-slate-700 border-slate-200";

  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${style}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6 border-b border-slate-200 pb-4">
      <h1 className="text-2xl font-bold tracking-tight text-[#0c2340]">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-600 leading-normal">{subtitle}</p>}
    </div>
  );
}

export function Notice({ kind, children }: { kind: "error" | "ok" | "info"; children: ReactNode }) {
  const style = {
    error: "border-red-200 bg-red-50 text-red-900",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
    info: "border-blue-200 bg-blue-50 text-blue-900",
  }[kind];

  return (
    <div className={`mb-5 flex items-start gap-3 rounded-lg border p-3.5 text-sm ${style}`}>
      <span className="mt-0.5 shrink-0">
        {kind === "error" && (
          <svg className="h-4 w-4 text-red-600" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        )}
        {kind === "ok" && (
          <svg className="h-4 w-4 text-emerald-600" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )}
        {kind === "info" && (
          <svg className="h-4 w-4 text-blue-600" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
        )}
      </span>
      <div className="flex-1 leading-snug">{children}</div>
    </div>
  );
}
