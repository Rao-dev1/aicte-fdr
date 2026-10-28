"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Notice } from "@/components/Shell";
import { api, ApiError, LoginResult, setSession } from "@/lib/api";

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
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-300 bg-white p-8 shadow-md">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">AICTE Regulation Bureau</p>
        <h1 className="mt-2 text-2xl font-bold text-slate-900">Sign in</h1>
        <p className="mt-1 text-sm text-slate-600">Use the account your administrator gave you.</p>

        <div className="mt-6">
          {error && <Notice kind="error">{error}</Notice>}
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-800">Username</span>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-800">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="mt-1 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900"
            />
          </label>

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
