"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Notice } from "@/components/Shell";
import { ROLE_LABELS, Role, setSession } from "@/lib/api";

const ROLES = Object.keys(ROLE_LABELS) as Role[];

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("INSTITUTION_USER");
  const [user, setUser] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!user.trim()) {
      setError("Enter your name or office ID.");
      return;
    }
    setSession({ role, user: user.trim() });
    router.push("/dashboard");
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">AICTE Regulation Bureau</p>
        <h1 className="mt-2 text-2xl font-bold">Sign in</h1>

        <Notice kind="info">
          Placeholder login: no password yet. Pick a role to try each view. Real login comes later.
        </Notice>

        {error && <Notice kind="error">{error}</Notice>}

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium">Name or office ID</span>
            <input
              value={user}
              onChange={(e) => setUser(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              placeholder="e.g. VIT Pune Principal"
            />
          </label>

          <fieldset>
            <legend className="text-sm font-medium">Role</legend>
            <div className="mt-2 grid gap-2">
              {ROLES.map((r) => (
                <label
                  key={r}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm ${
                    role === r ? "border-indigo-500 bg-indigo-50" : "border-slate-200"
                  }`}
                >
                  <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} />
                  {ROLE_LABELS[r]}
                </label>
              ))}
            </div>
          </fieldset>

          <button type="submit" className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-700">
            Continue
          </button>
        </form>
      </div>
    </main>
  );
}
