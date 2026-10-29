export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "INSTITUTION_USER" | "REGULATOR_OFFICER" | "APPROVING_AUTHORITY" | "ADMIN";
export type Session = { token: string; role: Role; user: string };

export const ROLE_LABELS: Record<Role, string> = {
  INSTITUTION_USER: "Institution",
  REGULATOR_OFFICER: "AICTE officer",
  APPROVING_AUTHORITY: "Approving authority",
  ADMIN: "Admin",
};

// ---- Session: login token kept in this browser's local storage ---------------

const SESSION_KEY = "fdr-session";

export function getSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function setSession(session: Session): void {
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    /* storage blocked: the user will simply be asked to log in again */
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

// ---- Types matching the backend schemas -------------------------------------

export type Institution = { id: number; name: string; code: string };

export type Deposit = {
  id: number;
  institution_id: number;
  reference_no: string;
  bank_name: string;
  amount: string;
  issue_date: string;
  maturity_date: string;
  status: string;
  previous_deposit_id: number | null;
  confirmed_reference_no: string | null;
  confirmed_bank_name: string | null;
  confirmed_amount: string | null;
  confirmed_issue_date: string | null;
  confirmed_maturity_date: string | null;
  mismatch_fields: string[];
};

export type DepositPage = { items: Deposit[]; total: number; page: number; page_size: number };
export type HistoryEntry = { id: number; action: string; actor: string; detail: string; at: string };
export type Doc = {
  id: number;
  deposit_id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by: string;
  uploaded_at: string;
  version?: number;
  series_id?: number | null;
};

export type VersionChange = { field: string; old: string | null; new: string | null };
export type Comparison = { a: number; b: number; changes: VersionChange[]; identical_values: boolean };
export type Notif = {
  id: number;
  deposit_id: number;
  kind: string;
  role: string;
  message: string;
  is_read: boolean;
  created_at: string;
};
export type Release = {
  id: number;
  deposit_id: number;
  status: string;
  status_before: string;
  requested_by: string;
  decided_by: string | null;
  remarks: string;
};
export type CalEvent = {
  on_date: string;
  type: string;
  deposit_id: number;
  reference_no: string;
  status: string;
  renewal_due: boolean;
};
export type Dashboard = {
  counts: Record<string, number>;
  total: number;
  upcoming: { deposit_id: number; reference_no: string; maturity_date: string; days_left: number; amount: number }[];
  pending_approvals: number;
};

export const GROUPS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "expiring", label: "Expiring" },
  { key: "matured", label: "Matured" },
  { key: "released", label: "Released" },
  { key: "pending", label: "Pending" },
] as const;

export const MATCH_FIELDS = [
  { key: "reference_no", label: "FDR number", submitted: "reference_no", confirmed: "confirmed_reference_no" },
  { key: "bank_name", label: "Bank", submitted: "bank_name", confirmed: "confirmed_bank_name" },
  { key: "amount", label: "Amount", submitted: "amount", confirmed: "confirmed_amount" },
  { key: "issue_date", label: "Issue date", submitted: "issue_date", confirmed: "confirmed_issue_date" },
  { key: "maturity_date", label: "Maturity date", submitted: "maturity_date", confirmed: "confirmed_maturity_date" },
] as const;

// ---- Formatting -------------------------------------------------------------

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString("en-IN", { style: "currency", currency: "INR" });
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value.length === 10 ? `${value}T00:00:00` : value).toLocaleDateString("en-IN");
}

export function dateTime(value: string): string {
  return new Date(value).toLocaleString("en-IN");
}

export const STATUS_STYLES: Record<string, string> = {
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
};

// ---- HTTP -------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const session = getSession();
  if (session) headers.set("Authorization", `Bearer ${session.token}`);
  return headers;
}

async function check(res: Response): Promise<Response> {
  if (res.ok) return res;
  let message = res.statusText || "Request failed";
  try {
    const body = await res.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* body was not JSON */
  }
  // Expired or invalid token: send the user back to the login page.
  if (res.status === 401 && !window.location.pathname.startsWith("/login")) {
    clearSession();
    window.location.href = "/login";
  }
  throw new ApiError(res.status, message);
}

export type Extracted = {
  engine: string;
  fields: Record<string, string | null>;
  warnings: string[];
};

export type LoginResult = {
  access_token: string;
  username: string;
  name: string;
  role: Role;
  institution_id: number | null;
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}/api${path}`, { ...init, headers: authHeaders(init.headers) });
  await check(res);
  return (await res.json()) as T;
}

export async function apiJson<T>(path: string, method: string, body: unknown): Promise<T> {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return api<T>(path, { method: "POST", body: form });
}

export async function fetchBlob(path: string): Promise<Blob> {
  const res = await fetch(`${API_URL}/api${path}`, { headers: authHeaders() });
  await check(res);
  return res.blob();
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_URL}/api${path}`, { headers: authHeaders() });
  await check(res);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
