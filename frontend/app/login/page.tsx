"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Notice } from "@/components/Shell";
import { api, ApiError, LoginResult, setSession } from "@/lib/api";

const AUDIENCES = ["For Institutions", "For Scrutiny Officers", "For Approving Authorities", "For Administrators"];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
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
      if (err instanceof ApiError && err.status === 401) setError("Wrong username or password.");
      else setError(err instanceof Error ? err.message : "Could not sign in. Is the backend running?");
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen md:grid-cols-[1.05fr_1fr]">
      <section className="flex flex-col justify-between bg-gradient-to-br from-[#0f2d52] via-[#123a6b] to-[#0a2140] p-8 text-white md:p-12">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/15 text-base font-bold ring-1 ring-white/30">
            AI
          </span>
          <div>
            <p className="text-lg font-semibold leading-tight">AICTE</p>
            <p className="text-sm text-blue-200">FDR Management Portal</p>
          </div>
        </div>

        <div className="my-10 md:my-0">
          <p className="text-sm font-medium uppercase tracking-wider text-blue-200">Secure · Transparent · Compliant</p>
          <h2 className="mt-3 text-3xl font-bold leading-tight md:text-4xl">Security deposits and FDRs, in one place.</h2>
          <ul className="mt-8 space-y-3">
            {AUDIENCES.map((label) => (
              <li key={label} className="flex items-center gap-3 text-blue-100">
                <span className="h-2 w-2 rounded-full bg-blue-300" />
                {label}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-blue-200">All India Council for Technical Education</p>
      </section>

      <section className="flex items-center justify-center bg-slate-50 p-6 md:p-12">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-lg">
          <h1 className="text-2xl font-bold text-[#0f2d52]">Welcome back</h1>
          <p className="mt-1 text-sm text-slate-600">Sign in with the account your administrator gave you.</p>

          <div className="mt-6">{error && <Notice kind="error">{error}</Notice>}</div>

          <form onSubmit={submit} className="space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-slate-800">Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="e.g. institution1"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium text-slate-800">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Enter your password"
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
              />
            </label>

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-[#0f2d52] px-4 py-2.5 font-medium text-white shadow-sm hover:bg-[#123a6b] disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
