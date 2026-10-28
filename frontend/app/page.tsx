"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, clearSession, getSession, LoginResult, ROLE_LABELS, Role, Session, setSession } from "@/lib/api";

type RoleCard = {
  id: Role;
  title: string;
  subtitle: string;
  demoUser: string;
  demoPass: string;
  theme: {
    bg: string;
    border: string;
    hoverBorder: string;
    iconBg: string;
    iconText: string;
    arrowColor: string;
  };
  icon: React.ReactNode;
};

const ROLE_CARDS: RoleCard[] = [
  {
    id: "INSTITUTION_USER",
    title: "Institution",
    subtitle: "Submit and track FDRs",
    demoUser: "institution1",
    demoPass: "Institute@12345",
    theme: {
      bg: "bg-[#f0f7ff]",
      border: "border-blue-200/80",
      hoverBorder: "hover:border-blue-400 hover:shadow-md",
      iconBg: "bg-blue-600",
      iconText: "text-white",
      arrowColor: "text-blue-600",
    },
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    id: "REGULATOR_OFFICER",
    title: "Scrutiny Officer",
    subtitle: "Verify submissions and discrepancies",
    demoUser: "officer1",
    demoPass: "Officer@12345",
    theme: {
      bg: "bg-[#fffbf0]",
      border: "border-amber-200/80",
      hoverBorder: "hover:border-amber-400 hover:shadow-md",
      iconBg: "bg-[#f59e0b]",
      iconText: "text-white",
      arrowColor: "text-amber-600",
    },
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
  {
    id: "APPROVING_AUTHORITY",
    title: "Approving Authority",
    subtitle: "Review and approve release requests",
    demoUser: "approver1",
    demoPass: "Approver@12345",
    theme: {
      bg: "bg-[#f0fdf4]",
      border: "border-emerald-200/80",
      hoverBorder: "hover:border-emerald-400 hover:shadow-md",
      iconBg: "bg-emerald-600",
      iconText: "text-white",
      arrowColor: "text-emerald-600",
    },
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  {
    id: "ADMIN",
    title: "Administrator",
    subtitle: "Manage users and configuration",
    demoUser: "admin",
    demoPass: "Admin@12345",
    theme: {
      bg: "bg-[#faf5ff]",
      border: "border-purple-200/80",
      hoverBorder: "hover:border-purple-400 hover:shadow-md",
      iconBg: "bg-purple-600",
      iconText: "text-white",
      arrowColor: "text-purple-600",
    },
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

export default function Home() {
  const router = useRouter();
  const [session, setSessionState] = useState<Session | null>(null);
  const [selectedRole, setSelectedRole] = useState<RoleCard>(ROLE_CARDS[0]);
  const [username, setUsername] = useState(ROLE_CARDS[0].demoUser);
  const [password, setPassword] = useState(ROLE_CARDS[0].demoPass);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSessionState(getSession());
  }, []);

  function selectRole(rc: RoleCard) {
    setSelectedRole(rc);
    setUsername(rc.demoUser);
    setPassword(rc.demoPass);
    setError(null);
    setShowLoginModal(true);
    // Smooth scroll to login section on mobile
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      document.getElementById("signin-section")?.scrollIntoView({ behavior: "smooth" });
    }
  }

  async function handleLogin(e: FormEvent) {
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
          setError("Cannot reach backend server. Please verify FastAPI is running on port 8001.");
        } else {
          setError(`Login failed: ${err.message}`);
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
      <header className="sticky top-0 z-40 border-b border-slate-200/90 bg-white shadow-xs">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Logo & Council Title */}
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

          {/* Right Navigation & Login Action */}
          <nav className="flex items-center gap-6">
            <div className="hidden items-center gap-6 text-sm font-medium text-slate-700 md:flex">
              <Link href="/" className="text-[#0c2340] font-semibold hover:text-blue-800 transition">
                Home
              </Link>
              <a href="#about" className="hover:text-[#0c2340] transition">
                About
              </a>
              <Link href="/deposits" className="hover:text-[#0c2340] transition">
                FDR Portal
              </Link>
              <Link href="/regulations" className="hover:text-[#0c2340] transition">
                Guidelines
              </Link>
              <a href="#contact" className="hover:text-[#0c2340] transition">
                Contact
              </a>
            </div>

            {session ? (
              <div className="flex items-center gap-3">
                <Link
                  href="/dashboard"
                  className="rounded-lg bg-[#0c2340] px-4 py-2 text-xs font-semibold text-white shadow-xs transition hover:bg-[#123a6b]"
                >
                  Go to Dashboard →
                </Link>
                <button
                  onClick={() => {
                    clearSession();
                    setSessionState(null);
                  }}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  Sign out
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  setShowLoginModal(true);
                  document.getElementById("signin-section")?.scrollIntoView({ behavior: "smooth" });
                }}
                className="rounded-lg bg-[#0c2340] px-6 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-[#123a6b]"
              >
                Login
              </button>
            )}
          </nav>
        </div>
      </header>

      {/* Main Container matching Reference Option 3 */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* 2. Hero Section with AICTE Building and Clean Government Aesthetic */}
        <section id="about" className="relative overflow-hidden rounded-xl bg-gradient-to-r from-[#071c33] via-[#0d2a4d] to-[#0c2340] text-white shadow-md">
          <div className="relative grid items-center gap-8 lg:grid-cols-12 lg:gap-6">
            {/* Left Content */}
            <div className="p-6 sm:p-10 lg:col-span-7 lg:py-14 xl:py-16">
              <span className="inline-block text-xs font-bold uppercase tracking-widest text-[#f59e0b]">
                AICTE FDR MANAGEMENT PORTAL
              </span>

              <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-white sm:text-4xl lg:text-5xl leading-tight">
                Secure FDR Management
                <br />
                <span className="text-white">for a Stronger Education Ecosystem</span>
              </h2>

              <p className="mt-4 max-w-xl text-sm sm:text-base leading-relaxed text-slate-300">
                Digitizing the submission, verification and release of security deposits for AICTE-approved institutions.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-4">
                <button
                  onClick={() => {
                    setShowLoginModal(true);
                    document.getElementById("signin-section")?.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#f59e0b] px-6 py-3 text-sm font-bold text-[#0f172a] shadow-md transition hover:bg-[#d97706]"
                >
                  <span>Sign In to Portal</span>
                  <span className="text-base font-bold">→</span>
                </button>

                <Link
                  href="/regulations"
                  className="rounded-lg border border-white/20 bg-white/10 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/15"
                >
                  View Regulations & APH
                </Link>
              </div>
            </div>

            {/* Right Side: Authentic AICTE Headquarters Building Photograph */}
            <div className="relative flex justify-center lg:col-span-5 lg:h-full lg:items-center lg:justify-end">
              <div className="relative h-64 w-full overflow-hidden sm:h-80 lg:h-full lg:min-h-[380px]">
                <Image
                  src="/assets/aicte_building_hero.png"
                  alt="AICTE Headquarters Building, Nelson Mandela Marg, New Delhi"
                  fill
                  className="object-cover object-center lg:object-right"
                  priority
                />
                {/* Clean gradient overlay for seamless blending on left side */}
                <div className="absolute inset-0 bg-gradient-to-t from-[#071c33] via-transparent to-transparent lg:bg-gradient-to-r lg:from-[#071c33] lg:via-transparent lg:to-transparent" />
              </div>
            </div>
          </div>
        </section>

        {/* 3. "Login as" Role-Based Access Cards Section */}
        <section className="mt-8" id="role-selection">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-xl font-bold tracking-tight text-[#0c2340]">Login as</h3>
            <span className="text-xs text-slate-500">Select authority role to authenticate</span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {ROLE_CARDS.map((rc) => {
              const isSelected = selectedRole.id === rc.id;
              return (
                <div
                  key={rc.id}
                  onClick={() => selectRole(rc)}
                  className={`group relative flex cursor-pointer flex-col justify-between rounded-xl border p-5 transition ${
                    rc.theme.bg
                  } ${rc.theme.border} ${rc.theme.hoverBorder} ${
                    isSelected ? "ring-2 ring-blue-600 shadow-sm" : "shadow-xs"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <span className={`flex h-10 w-10 items-center justify-center rounded-lg shadow-xs ${rc.theme.iconBg} ${rc.theme.iconText}`}>
                      {rc.icon}
                    </span>
                    <span className={`text-base font-bold transition-transform group-hover:translate-x-1 ${rc.theme.arrowColor}`}>
                      →
                    </span>
                  </div>

                  <div className="mt-4">
                    <h4 className="text-base font-bold text-[#0c2340] group-hover:text-blue-900">{rc.title}</h4>
                    <p className="mt-1 text-xs text-slate-600 leading-snug">{rc.subtitle}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* 4. Interactive Sign-in Panel (Opens when role selected or on demand) */}
        <section id="signin-section" className="mt-8 mb-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-blue-700">
                  Authentication Portal
                </span>
                <h3 className="text-xl font-bold text-[#0c2340]">
                  Sign in as {selectedRole.title}
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  Enter your credentials to access the AICTE FDR management interface.
                </p>
              </div>

              {/* Quick Role Switcher Pills */}
              <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 p-1">
                {ROLE_CARDS.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => selectRole(r)}
                    className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                      selectedRole.id === r.id
                        ? "bg-[#0c2340] text-white shadow-xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {r.title}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs font-medium text-red-800">
                {error}
              </div>
            )}

            <form onSubmit={handleLogin} className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-12">
              <div className="lg:col-span-5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                  placeholder="Enter username"
                  required
                />
              </div>

              <div className="lg:col-span-5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
                  placeholder="Enter password"
                  required
                />
              </div>

              <div className="flex items-end lg:col-span-2">
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-lg bg-[#0c2340] px-5 py-2.5 text-sm font-bold text-white shadow-md transition hover:bg-[#123a6b] disabled:opacity-60"
                >
                  {busy ? "Signing in…" : "Sign In →"}
                </button>
              </div>
            </form>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <p>
                <span className="font-semibold text-slate-700">Selected Profile:</span> {selectedRole.demoUser} ({ROLE_LABELS[selectedRole.id]})
              </p>
              <p className="text-[11px] text-slate-400">
                Pre-filled authority credentials for local administrative evaluation.
              </p>
            </div>
          </div>
        </section>
      </main>

      {/* 5. Official Footer */}
      <footer className="mt-8 border-t border-slate-200 bg-white py-6" id="contact">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-4 text-center sm:flex-row sm:text-left">
            <div className="flex items-center gap-3">
              <Image
                src="/assets/aicte_official_logo.png"
                alt="All India Council for Technical Education Logo"
                width={36}
                height={36}
                className="h-9 w-9 object-contain"
              />
              <div>
                <p className="text-xs font-bold text-[#0c2340]">All India Council for Technical Education</p>
                <p className="text-[11px] text-slate-500">Ministry of Education, Government of India</p>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
