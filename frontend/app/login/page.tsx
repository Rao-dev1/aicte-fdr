"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, getSession, LoginResult, ROLE_LABELS, Role, setSession } from "@/lib/api";

type RoleOption = {
  id: Role;
  label: string;
  subtitle: string;
  username: string;
  password: string;
  badgeBg: string;
  badgeText: string;
  cardBg: string;
  borderColor: string;
  icon: React.ReactNode;
};

const ROLES: RoleOption[] = [
  {
    id: "INSTITUTION_USER",
    label: "Institution",
    subtitle: "Submit and track FDRs",
    username: "institution1",
    password: "Institute@12345",
    badgeBg: "bg-blue-600",
    badgeText: "text-white",
    cardBg: "bg-[#f0f7ff]",
    borderColor: "border-blue-200",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    id: "REGULATOR_OFFICER",
    label: "Scrutiny Officer",
    subtitle: "Verify submissions and discrepancies",
    username: "officer1",
    password: "Officer@12345",
    badgeBg: "bg-[#f59e0b]",
    badgeText: "text-white",
    cardBg: "bg-[#fffbf0]",
    borderColor: "border-amber-200",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
  {
    id: "APPROVING_AUTHORITY",
    label: "Approving Authority",
    subtitle: "Review and approve release requests",
    username: "approver1",
    password: "Approver@12345",
    badgeBg: "bg-emerald-600",
    badgeText: "text-white",
    cardBg: "bg-[#f0fdf4]",
    borderColor: "border-emerald-200",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  {
    id: "ADMIN",
    label: "Administrator",
    subtitle: "Manage users and configuration",
    username: "admin",
    password: "Admin@12345",
    badgeBg: "bg-purple-600",
    badgeText: "text-white",
    cardBg: "bg-[#faf5ff]",
    borderColor: "border-purple-200",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [selectedRole, setSelectedRole] = useState<RoleOption>(ROLES[0]);
  const [username, setUsername] = useState(ROLES[0].username);
  const [password, setPassword] = useState(ROLES[0].password);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // If already logged in, redirect straight to dashboard
    const current = getSession();
    if (current) {
      router.replace("/dashboard");
    }
  }, [router]);

  function pickRole(r: RoleOption) {
    setSelectedRole(r);
    setUsername(r.username);
    setPassword(r.password);
    setError(null);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password) {
      setError("Please enter your username and password.");
      return;
    }
    setBusy(true);
    try {
      const result = await api<LoginResult>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      setSession({ token: result.access_token, role: result.role, user: result.name });
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError("Invalid username or password. Please verify your credentials.");
        } else if (err.status === 404) {
          setError("Authentication service endpoint not found (HTTP 404). Please verify that FastAPI is running on port 8001.");
        } else if (err.status === 502 || err.status === 503) {
          setError("Cannot reach backend service. Please check if FastAPI is running on port 8001.");
        } else if (err.status >= 500) {
          setError(`Backend server error (HTTP ${err.status}): ${err.message}. Please check backend logs.`);
        } else {
          setError(err.message || "Sign-in failed.");
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not sign in. Is the backend running?");
      }
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900 antialiased">
      {/* 1. Official Government Header */}
      <header className="border-b border-slate-200 bg-white shadow-xs">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3.5">
            <div className="relative h-12 w-12 shrink-0">
              <Image
                src="/assets/aicte_official_logo.png"
                alt="All India Council for Technical Education Logo"
                width={48}
                height={48}
                className="h-12 w-12 object-contain"
                priority
              />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-[#0c2340] sm:text-base md:text-lg leading-tight">
                All India Council for Technical Education
              </h1>
              <p className="text-xs font-semibold text-slate-500 leading-tight">
                अखिल भारतीय तकनीकी शिक्षा परिषद · Govt. of India
              </p>
            </div>
          </Link>

          <nav className="flex items-center gap-6">
            <Link href="/" className="text-sm font-medium text-slate-700 hover:text-[#0c2340]">
              Home
            </Link>
            <Link href="/regulations" className="text-sm font-medium text-slate-700 hover:text-[#0c2340]">
              Guidelines
            </Link>
            <span className="inline-flex items-center rounded-full bg-[#0c2340] px-3.5 py-1 text-xs font-bold text-white shadow-xs">
              Portal Sign In
            </span>
          </nav>
        </div>
      </header>

      {/* Main Option 3 Layout Container */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* 2. Hero Section with AICTE Building */}
        <section className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#071c33] via-[#0d2a4d] to-[#0c2340] text-white shadow-md">
          <div className="relative grid items-center gap-8 lg:grid-cols-12 lg:gap-6">
            <div className="p-6 sm:p-10 lg:col-span-7 lg:py-12">
              <span className="inline-block text-xs font-bold uppercase tracking-widest text-[#f59e0b]">
                AICTE FDR MANAGEMENT PORTAL
              </span>

              <h2 className="mt-2 text-3xl font-extrabold tracking-tight text-white sm:text-4xl leading-tight">
                Secure FDR Management
                <br />
                <span className="text-white">for a Stronger Education Ecosystem</span>
              </h2>

              <p className="mt-3 max-w-xl text-xs sm:text-sm leading-relaxed text-slate-300">
                Digitizing the submission, verification and release of security deposits for AICTE-approved institutions.
              </p>
            </div>

            {/* Right Side Building Image */}
            <div className="relative flex justify-center lg:col-span-5 lg:h-full lg:items-center lg:justify-end">
              <div className="relative h-56 w-full overflow-hidden sm:h-72 lg:h-full lg:min-h-[320px]">
                <Image
                  src="/assets/aicte_building_hero.png"
                  alt="AICTE Headquarters Building, Nelson Mandela Marg, New Delhi"
                  fill
                  className="object-cover object-center lg:object-right"
                  priority
                />
                <div className="absolute inset-0 bg-gradient-to-t from-[#071c33] via-transparent to-transparent lg:bg-gradient-to-r lg:from-[#071c33] lg:via-transparent lg:to-transparent" />
              </div>
            </div>
          </div>
        </section>

        {/* 3. Role-Based Access Options ("Login as") */}
        <section className="mt-8">
          <div className="mb-4">
            <h3 className="text-xl font-bold tracking-tight text-[#0c2340]">Login as</h3>
            <p className="text-xs text-slate-500">Select authority role to authenticate.</p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {ROLES.map((r) => {
              const active = selectedRole.id === r.id;
              return (
                <div
                  key={r.id}
                  onClick={() => pickRole(r)}
                  className={`group flex cursor-pointer flex-col justify-between rounded-xl border p-4.5 transition ${
                    r.cardBg
                  } ${r.borderColor} ${
                    active ? "ring-2 ring-blue-600 shadow-sm" : "shadow-xs hover:border-blue-400 hover:shadow-xs"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`flex h-10 w-10 items-center justify-center rounded-lg shadow-xs ${r.badgeBg} ${r.badgeText}`}>
                      {r.icon}
                    </span>
                    <span className="text-base font-bold text-slate-400 transition-transform group-hover:translate-x-1">
                      →
                    </span>
                  </div>

                  <div className="mt-4">
                    <h4 className="text-sm font-bold text-[#0c2340]">{r.label}</h4>
                    <p className="mt-0.5 text-xs text-slate-600">{r.subtitle}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* 4. Active Sign-In Form Card */}
        <section className="mt-6 mb-12">
          <div className="mx-auto max-w-xl rounded-xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
            <div className="border-b border-slate-200 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-[#0c2340]">Welcome back</h3>
                  <p className="text-xs text-slate-500">
                    Signing in as <span className="font-semibold text-blue-700">{selectedRole.label}</span> ({ROLE_LABELS[selectedRole.id]})
                  </p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${selectedRole.badgeBg} ${selectedRole.badgeText}`}>
                  {selectedRole.label}
                </span>
              </div>
            </div>

            {error && (
              <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs font-semibold text-red-800">
                {error}
              </div>
            )}

            <form onSubmit={submit} className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                  placeholder="e.g. institution1"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  placeholder="Enter your password"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              <button
                type="submit"
                disabled={busy}
                className="mt-2 w-full rounded-lg bg-[#0c2340] px-5 py-3 text-sm font-bold text-white shadow-md transition hover:bg-[#123a6b] disabled:opacity-60"
              >
                {busy ? "Signing in…" : "Sign In to Portal →"}
              </button>
            </form>

            <div className="mt-5 border-t border-slate-100 pt-3 flex flex-wrap items-center justify-between text-xs text-slate-500">
              <p>Demo credentials active for local review.</p>
              <Link href="/" className="font-semibold text-blue-700 hover:underline">
                Back to Portal Home
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Official Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        <p>© 2026 All India Council for Technical Education (AICTE), Ministry of Education, Govt. of India.</p>
        <p className="mt-0.5 text-[11px] text-slate-400">Nelson Mandela Marg, Vasant Kunj, New Delhi - 110070</p>
      </footer>
    </div>
  );
}
