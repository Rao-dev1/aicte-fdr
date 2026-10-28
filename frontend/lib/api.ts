export function getApiBaseUrl(): string {
  if (typeof window !== "undefined" && window.location) {
    const curHost = window.location.hostname;
    const defaultPort = "8001";
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl) {
      try {
        const u = new URL(envUrl);
        if ((curHost === "localhost" || curHost === "127.0.0.1") && (u.hostname === "localhost" || u.hostname === "127.0.0.1")) {
          return `${u.protocol}//${curHost}:${u.port || defaultPort}`;
        }
        return envUrl;
      } catch {
        return envUrl;
      }
    }
    return `http://${curHost}:${defaultPort}`;
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
}

export const API_URL = getApiBaseUrl();

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
};
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

// ---- Currency and File Size Helpers ----------------------------------------

export function parseCleanAmount(val: string | number | null | undefined): { numeric: number; cleaned: string } | null {
  if (val === null || val === undefined) return null;
  let str = String(val).trim();
  if (!str) return null;

  // Remove currency symbols (₹, Rs., Rs, INR) and spaces
  str = str.replace(/[₹\s]|(?:Rs\.?|INR)/gi, "");

  // Handle potential comma decimal separator (e.g. "10,000,00" or "10000,00")
  if (str.includes(",") && !str.includes(".")) {
    const lastCommaIdx = str.lastIndexOf(",");
    const decimalPart = str.slice(lastCommaIdx + 1);
    if (decimalPart.length === 2) {
      const integerPart = str.slice(0, lastCommaIdx).replace(/,/g, "");
      str = `${integerPart}.${decimalPart}`;
    } else {
      str = str.replace(/,/g, "");
    }
  } else {
    str = str.replace(/,/g, "");
  }

  const num = Number(str);
  if (Number.isNaN(num) || num <= 0) return null;
  const cleaned = str.includes(".") ? Number(str).toFixed(2) : String(Number(str));
  return { numeric: num, cleaned };
}

export function formatFileSize(bytes: number): string {
  if (bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    const kb = bytes / 1024;
    return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  }
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(2)} MB`;
}

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
  if (res.status === 404 && message === "Not Found") {
    message = `Endpoint not found (HTTP 404) at ${res.url}. Verify backend routes and server port.`;
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
  const baseUrl = getApiBaseUrl();
  const fullUrl = `${baseUrl}/api${path}`;
  let res: Response;
  try {
    res = await fetch(fullUrl, { ...init, headers: authHeaders(init.headers) });
  } catch (err) {
    // Host fallback for dual-stack macOS localhost <-> 127.0.0.1
    let altUrl: string | null = null;
    if (baseUrl.includes("localhost")) {
      altUrl = `${baseUrl.replace("localhost", "127.0.0.1")}/api${path}`;
    } else if (baseUrl.includes("127.0.0.1")) {
      altUrl = `${baseUrl.replace("127.0.0.1", "localhost")}/api${path}`;
    }

    if (altUrl) {
      try {
        res = await fetch(altUrl, { ...init, headers: authHeaders(init.headers) });
      } catch {
        const msg = err instanceof Error ? err.message : String(err);
        throw new ApiError(
          503,
          `Backend service unreachable at ${baseUrl} (${msg}). Please verify that FastAPI is running on port 8001.`
        );
      }
    } else {
      const msg = err instanceof Error ? err.message : String(err);
      throw new ApiError(
        503,
        `Backend service unreachable at ${baseUrl} (${msg}). Please verify that FastAPI is running on port 8001.`
      );
    }
  }
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

export async function downloadFile(path: string, filename: string): Promise<void> {
  const baseUrl = getApiBaseUrl();
  let res: Response;
  try {
    res = await fetch(`${baseUrl}/api${path}`, { headers: authHeaders() });
  } catch {
    const altUrl = baseUrl.includes("localhost")
      ? baseUrl.replace("localhost", "127.0.0.1")
      : baseUrl.replace("127.0.0.1", "localhost");
    res = await fetch(`${altUrl}/api${path}`, { headers: authHeaders() });
  }
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

// ---- Feature 1: FDR TRACE Types -------------------------------------------

export type TraceNode = {
  id: number;
  reference_no: string;
  bank_name: string;
  amount: number;
  status: string;
  issue_date: string;
  maturity_date: string;
  effective_maturity: string;
  is_current: boolean;
  institution_id: number;
};

export type TraceEdge = {
  id: number;
  source: number;
  target: number;
  relation_type: string;
  created_at: string;
  actor: string;
  metadata: Record<string, unknown>;
};

export type LineageGraph = {
  deposit_id: number;
  root_id: number;
  nodes: TraceNode[];
  edges: TraceEdge[];
  total_nodes: number;
  total_edges: number;
};

export type TimelineEvent = {
  id: string;
  source: string;
  event_type: string;
  actor: string;
  actor_role: string | null;
  summary: string;
  details: Record<string, unknown>;
  created_at: string;
  event_hash: string | null;
  prev_hash: string | null;
};

export type TraceResponse = {
  deposit_id: number;
  reference_no: string;
  lineage: LineageGraph;
  timeline: {
    deposit_id: number;
    integrity: { valid: boolean; event_count: number; message: string };
    events: TimelineEvent[];
    total_events: number;
  };
};

// ---- Feature 2: Release Readiness Types -----------------------------------

export type ReadinessNode = {
  id: string;
  category: string;
  title: string;
  is_mandatory: boolean;
  status: "SATISFIED" | "PENDING" | "MISSING" | "BLOCKED" | "REQUIRES_REVIEW" | "NOT_APPLICABLE";
  explanation: string;
  evidence: Record<string, unknown>;
  responsible_role: string;
  next_action: string;
};

export type ReadinessResponse = {
  deposit_id: number;
  release_request_id: number | null;
  overall_status: "READY_FOR_APPROVAL" | "BLOCKED" | "UNDER_REVIEW" | "INCOMPLETE";
  is_ready_for_decision: boolean;
  completion_percentage: number;
  total_prerequisites: number;
  satisfied_count: number;
  blocked_count: number;
  missing_count: number;
  pending_count: number;
  blocking_reasons: string[];
  next_actions: { node: string; role: string; action: string }[];
  nodes: ReadinessNode[];
  edges: { source: string; target: string }[];
  evaluated_at: string;
};

// ---- Feature 3: Regulation Replay Types -----------------------------------

export type RegulationRule = {
  id: number;
  rule_code: string;
  version: string;
  title: string;
  description: string;
  effective_from: string;
  effective_to: string | null;
  status: "DRAFT" | "ACTIVE" | "SUPERSEDED" | "ARCHIVED";
  source_reference: string;
  rule_spec_json: string;
  change_summary: string;
  author: string;
  created_at: string;
  published_at: string | null;
};

export type ReplayCondition = {
  condition_id: string;
  title: string;
  passed: boolean;
  required: unknown;
  actual: unknown;
  reason: string;
};

export type ReplayComparison = {
  deposit_id: number;
  earlier_assessment: {
    snapshot_id: number;
    rule_code: string;
    rule_version: string;
    evaluation_result: string;
    assessed_at: string;
    conditions: ReplayCondition[];
  };
  replay_assessment: {
    snapshot_id: number;
    rule_code: string;
    rule_version: string;
    evaluation_result: string;
    assessed_at: string;
    conditions: ReplayCondition[];
  };
  changed_conditions: {
    condition_id: string;
    title: string;
    previous_status: string;
    new_status: string;
    reason: string;
  }[];
  newly_identified_issues: ReplayCondition[];
  resolved_issues: ReplayCondition[];
  requires_manual_review: boolean;
};

export type ImpactCase = {
  deposit_id: number;
  reference_no: string;
  institution_id: number;
  bank_name: string;
  amount: number;
  current_status: string;
  evaluation_result: string;
  impact_reason: string;
  failed_conditions: ReplayCondition[];
};

export type ImpactAnalysisResponse = {
  rule_id: number;
  rule_code: string;
  rule_version: string;
  rule_title: string;
  total_open_cases_scanned: number;
  summary: {
    potentially_affected_count: number;
    requires_manual_review_count: number;
    no_detected_impact_count: number;
    insufficient_data_count: number;
  };
  potentially_affected: ImpactCase[];
  requires_manual_review: ImpactCase[];
  no_detected_impact: ImpactCase[];
  insufficient_data: { deposit_id: number; reference_no: string; institution_id: number; reason: string }[];
};

// ---- Feature 4: Cross-Record Integrity Types ------------------------------

export type FindingStatus =
  | "OPEN"
  | "UNDER_REVIEW"
  | "CONFIRMED_INCONSISTENCY"
  | "FALSE_POSITIVE"
  | "RESOLVED"
  | "ESCALATED";

export type IntegrityFinding = {
  id: number;
  finding_code: string;
  category: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  status: FindingStatus;
  primary_deposit_id: number | null;
  related_deposit_ids: number[];
  institution_ids: number[];
  explanation: string;
  trigger_values: Record<string, unknown>;
  evidence: Record<string, unknown>;
  assignee: string | null;
  first_detected_at: string;
  last_detected_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_remarks: string | null;
  actions?: {
    id: number;
    action: string;
    actor: string;
    actor_role: string;
    notes: string;
    created_at: string;
  }[];
};

export type IntegrityFindingsResponse = {
  items: IntegrityFinding[];
  total: number;
  page: number;
  page_size: number;
  summary: {
    by_status: Record<string, number>;
    by_severity: Record<string, number>;
    open_critical: number;
  };
};

export type IntegrityNetworkNode = {
  id: string;
  type: "deposit" | "institution" | "finding";
  label: string;
  [key: string]: unknown;
};

export type IntegrityNetworkEdge = {
  source: string;
  target: string;
  relation: string;
  severity?: string;
};

export type IntegrityNetworkResponse = {
  nodes: IntegrityNetworkNode[];
  edges: IntegrityNetworkEdge[];
  total_nodes: number;
  total_edges: number;
};

// ============================================================================
// FEATURE 1: Smart Deadline & Expiry Alerts Types
// ============================================================================

export type DeadlineItem = {
  alert_id: string;
  deposit_id: number;
  reference_no: string;
  institution_id: number;
  institution_name: string;
  institution_code: string;
  deadline_type: "MATURITY" | "RENEWAL" | "SCRUTINY_PENDING" | "RELEASE_APPROVAL";
  deadline_label: string;
  deadline_date: string;
  days_left: number;
  urgency: "overdue" | "due_soon" | "upcoming" | "completed";
  status: string;
  amount: number | string;
  target_role: string;
  is_my_action: boolean;
  url: string;
};

export type DeadlineSummary = {
  overdue: number;
  due_soon: number;
  upcoming: number;
  completed: number;
  total: number;
};

export type DeadlinesResponse = {
  items: DeadlineItem[];
  summary: DeadlineSummary;
};

// ============================================================================
// FEATURE 2: Explainable Document Verification Types
// ============================================================================

export type ExtractedFieldMeta = {
  value: string | null;
  status: "Extracted" | "Needs review" | "Not detected";
  confidence: number | null;
  evidence: string | null;
  normalized?: string | null;
};

export type StructuredExtracted = {
  engine: string;
  fields: Record<string, string | null>;
  structured: Record<string, ExtractedFieldMeta>;
  warnings: string[];
  text_preview?: string;
};

// ============================================================================
// FEATURE 3: Deficiency Report Types
// ============================================================================

export type DeficiencyItem = {
  id: string;
  category: "FIELD_MISMATCH" | "MISSING_DOCUMENT" | "SCRUTINY_FLAG" | "REGULATION_NON_COMPLIANCE";
  title: string;
  field_name?: string | null;
  submitted_value?: string | null;
  verified_value?: string | null;
  explanation: string;
  required_action: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  is_confirmed: boolean;
};

export type DeficiencyReportPreview = {
  deposit_id: number;
  reference_no: string;
  institution_name: string;
  institution_code: string;
  bank_name: string;
  amount: number | string;
  issue_date: string;
  maturity_date: string;
  current_status: string;
  has_deficiencies: boolean;
  summary_message: string;
  deficiencies: DeficiencyItem[];
  reviewer_comments: string[];
  report_date: string;
};

export type DeficiencyReportGenerateIn = {
  confirmed_deficiency_ids?: string[];
  additional_comments?: string;
  custom_corrective_action?: string;
};


