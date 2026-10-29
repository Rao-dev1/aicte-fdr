"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Shell, Notice } from "@/components/Shell";
import {
  api,
  apiJson,
  getSession,
  ImpactAnalysisResponse,
  RegulationRule,
  ReplayComparison,
} from "@/lib/api";

export default function RegulationsPage() {
  const [tab, setTab] = useState<"registry" | "replay" | "impact">("registry");
  const [rules, setRules] = useState<RegulationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // New rule draft state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [ruleCode, setRuleCode] = useState("REG-AICTE-FDR-2025");
  const [ruleVersion, setRuleVersion] = useState("2.1.0");
  const [ruleTitle, setRuleTitle] = useState("");
  const [ruleDesc, setRuleDesc] = useState("");
  const [minTenureMonths, setMinTenureMonths] = useState(60);
  const [minAmount, setMinAmount] = useState(500000);
  const [requireZeroDiscrepancy, setRequireZeroDiscrepancy] = useState(true);
  const [sourceRef, setSourceRef] = useState("AICTE APH 2025-26");
  const [changeSummary, setChangeSummary] = useState("");
  const [creating, setCreating] = useState(false);

  // Replay Simulator state
  const [replayDepositId, setReplayDepositId] = useState<string>("");
  const [selectedTargetRuleId, setSelectedTargetRuleId] = useState<number | null>(null);
  const [replayResult, setReplayResult] = useState<ReplayComparison | null>(null);
  const [replaying, setReplaying] = useState(false);

  // Impact Analysis state
  const [impactRuleId, setImpactRuleId] = useState<number | null>(null);
  const [impactData, setImpactData] = useState<ImpactAnalysisResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const session = getSession();
  const isAdmin = session?.role === "ADMIN";
  const isOfficerOrAdmin = session?.role === "REGULATOR_OFFICER" || isAdmin || session?.role === "APPROVING_AUTHORITY";

  async function loadRules() {
    setLoading(true);
    try {
      const res = await api<RegulationRule[]>("/regulations/rules");
      setRules(res);
      if (res.length > 0) {
        setSelectedTargetRuleId(res[0].id);
        setImpactRuleId(res[0].id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load regulation rules");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRules();
  }, []);

  async function handleCreateRule(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await apiJson("/regulations/rules", "POST", {
        rule_code: ruleCode.trim(),
        version: ruleVersion.trim(),
        title: ruleTitle.trim(),
        description: ruleDesc.trim(),
        effective_from: new Date().toISOString().slice(0, 10),
        source_reference: sourceRef.trim(),
        rule_spec: {
          min_tenure_months: Number(minTenureMonths),
          min_amount_inr: Number(minAmount),
          require_zero_discrepancy: requireZeroDiscrepancy,
          mandatory_documents: ["FDR Certificate"],
        },
        change_summary: changeSummary.trim(),
      });
      setSuccess(`Draft rule ${ruleCode} v${ruleVersion} created successfully`);
      setShowCreateModal(false);
      loadRules();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setCreating(false);
    }
  }

  async function handlePublishRule(ruleId: number) {
    if (!confirm("Publish this rule version? It will become ACTIVE and supersede prior versions.")) return;
    try {
      await api(`/regulations/rules/${ruleId}/publish`, { method: "POST" });
      setSuccess("Rule version published and activated successfully");
      loadRules();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to publish rule");
    }
  }

  async function handleRunReplay(e: React.FormEvent) {
    e.preventDefault();
    if (!replayDepositId.trim() || !selectedTargetRuleId) return;
    setReplaying(true);
    setError(null);
    setReplayResult(null);
    try {
      const res = await apiJson<ReplayComparison>(
        `/regulations/replay?deposit_id=${encodeURIComponent(replayDepositId.trim())}`,
        "POST",
        { target_rule_id: selectedTargetRuleId }
      );
      setReplayResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Replay simulation failed");
    } finally {
      setReplaying(false);
    }
  }

  async function handleRunImpact(ruleId: number) {
    setAnalyzing(true);
    setError(null);
    try {
      const res = await api<ImpactAnalysisResponse>(`/regulations/rules/${ruleId}/impact-analysis`);
      setImpactData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impact analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  const statusBadge = (st: string) => {
    const map: Record<string, string> = {
      ACTIVE: "bg-emerald-100 text-emerald-800 border-emerald-200",
      DRAFT: "bg-amber-100 text-amber-800 border-amber-200",
      SUPERSEDED: "bg-slate-100 text-slate-700 border-slate-200",
      ARCHIVED: "bg-slate-100 text-slate-500 border-slate-200",
    };
    return (
      <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${map[st] || "bg-slate-100"}`}>
        {st}
      </span>
    );
  };

  return (
    <Shell>
      <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-[#0f2d52]">Regulation-Version Replay</h1>
          <p className="mt-1 text-sm text-slate-600">
            Versioned rules registry, deterministic condition evaluations, immutable assessment snapshots, and replay impact analysis
          </p>
        </div>

        {isOfficerOrAdmin && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#0f2d52] px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#1a3d6b]"
          >
            + New Regulation Version
          </button>
        )}
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {success && <Notice kind="ok">{success}</Notice>}

      {/* Tabs */}
      <div className="my-6 flex gap-2 border-b border-slate-200">
        <button
          onClick={() => setTab("registry")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            tab === "registry" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Versioned Rule Registry ({rules.length})
        </button>
        <button
          onClick={() => setTab("replay")}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            tab === "replay" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Replay & Comparison Simulator
        </button>
        <button
          onClick={() => {
            setTab("impact");
            if (impactRuleId && !impactData) handleRunImpact(impactRuleId);
          }}
          className={`border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${
            tab === "impact" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Open Cases Impact Analysis
        </button>
      </div>

      {/* TAB 1: REGISTRY */}
      {tab === "registry" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">Official AICTE Deposit Regulations & Versions</h2>
            <p className="mt-1 text-xs text-slate-500">
              Each FDR assessment is immutably anchored to a specific regulation version. Creating a new version never
              modifies historical assessments or retroactively changes past decisions.
            </p>

            {loading ? (
              <div className="p-10 text-center text-sm text-slate-500">Loading regulations…</div>
            ) : (
              <div className="mt-5 space-y-4">
                {rules.map((rule) => {
                  let specObj: Record<string, unknown> = {};
                  try {
                    specObj = JSON.parse(rule.rule_spec_json);
                  } catch {}

                  return (
                    <div
                      key={rule.id}
                      className={`rounded-xl border p-5 transition-all ${
                        rule.status === "ACTIVE"
                          ? "border-emerald-300 bg-emerald-50/20 shadow-xs"
                          : "border-slate-200 bg-white"
                      }`}
                    >
                      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                        <div className="flex items-center gap-3">
                          {statusBadge(rule.status)}
                          <span className="font-mono text-sm font-bold text-[#0f2d52]">
                            {rule.rule_code} <span className="text-blue-600">v{rule.version}</span>
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                          <span>Effective: {rule.effective_from}</span>
                          {rule.effective_to && <span>to {rule.effective_to}</span>}
                          <span>• Author: {rule.author}</span>
                        </div>
                      </div>

                      <h3 className="mt-2 text-base font-semibold text-slate-900">{rule.title}</h3>
                      <p className="mt-1 text-xs text-slate-600">{rule.description}</p>
                      <p className="mt-1 text-[11px] text-slate-500 italic">Source: {rule.source_reference}</p>

                      {/* Rule conditions summary */}
                      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
                        <div>
                          <span className="text-slate-500">Min Tenure:</span>{" "}
                          <span className="font-semibold text-slate-800">{String(specObj.min_tenure_months || "—")} Months</span>
                        </div>
                        <div>
                          <span className="text-slate-500">Min Amount:</span>{" "}
                          <span className="font-semibold text-slate-800">₹{Number(specObj.min_amount_inr || 0).toLocaleString("en-IN")}</span>
                        </div>
                        <div>
                          <span className="text-slate-500">Strict Match:</span>{" "}
                          <span className="font-semibold text-slate-800">{specObj.require_zero_discrepancy ? "Zero Tolerance" : "Standard"}</span>
                        </div>
                        <div>
                          <span className="text-slate-500">Mandatory Docs:</span>{" "}
                          <span className="font-semibold text-slate-800">{Array.isArray(specObj.mandatory_documents) ? specObj.mandatory_documents.length : 1} required</span>
                        </div>
                      </div>

                      {rule.change_summary && (
                        <p className="mt-2 text-xs text-blue-900">
                          <span className="font-semibold">Version Change Summary:</span> {rule.change_summary}
                        </p>
                      )}

                      {isAdmin && rule.status === "DRAFT" && (
                        <div className="mt-3 flex justify-end">
                          <button
                            onClick={() => handlePublishRule(rule.id)}
                            className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-800"
                          >
                            ✓ Publish & Activate This Version
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: REPLAY & COMPARISON SIMULATOR */}
      {tab === "replay" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">FDR Assessment Replay Simulator</h2>
            <p className="mt-1 text-xs text-slate-500">
              Evaluate an existing deposit under a new or alternative regulation version. The simulator produces a new
              analytical replay snapshot without retroactively mutating the historical assessment record.
            </p>

            <form onSubmit={handleRunReplay} className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="block text-xs font-medium text-slate-700">FDR Deposit ID <span className="text-red-500">*</span></label>
                <input
                  type="number"
                  required
                  placeholder="e.g. 1"
                  value={replayDepositId}
                  onChange={(e) => setReplayDepositId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700">Target Regulation Version <span className="text-red-500">*</span></label>
                <select
                  value={selectedTargetRuleId ?? ""}
                  onChange={(e) => setSelectedTargetRuleId(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
                >
                  {rules.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.rule_code} v{r.version} ({r.status})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={replaying}
                  className="w-full rounded-lg bg-[#0f2d52] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#1a3d6b] disabled:opacity-50"
                >
                  {replaying ? "Simulating Replay…" : "Run Replay Simulation"}
                </button>
              </div>
            </form>
          </div>

          {/* Replay Results Side-by-Side Comparison */}
          {replayResult && (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <h3 className="text-base font-bold text-slate-900">
                  Side-by-Side Assessment Comparison (FDR #{replayResult.deposit_id})
                </h3>
                {replayResult.requires_manual_review && (
                  <span className="rounded-md bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
                    ⚠ Manual Review Required Under Target Rule
                  </span>
                )}
              </div>

              <div className="mt-5 grid grid-cols-1 gap-6 md:grid-cols-2">
                {/* Historical Assessment */}
                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                  <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Historical Snapshot</span>
                    <span className="font-mono text-xs font-semibold text-slate-700">
                      {replayResult.earlier_assessment.rule_code} v{replayResult.earlier_assessment.rule_version}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">Original Result:</span>
                    <span
                      className={`rounded px-2.5 py-0.5 text-xs font-bold ${
                        replayResult.earlier_assessment.evaluation_result === "COMPLIANT"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {replayResult.earlier_assessment.evaluation_result}
                    </span>
                  </div>
                  <div className="mt-4 space-y-2 text-xs">
                    {replayResult.earlier_assessment.conditions.map((c: any) => (
                      <div key={c.condition_id} className="rounded-lg border border-slate-200 bg-white p-2.5">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-800">{c.title}</span>
                          <span className={c.passed ? "text-emerald-600 font-bold" : "text-red-600 font-bold"}>
                            {c.passed ? "✓ Passed" : "✗ Failed"}
                          </span>
                        </div>
                        <p className="mt-1 text-slate-600">{c.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Replay Simulation */}
                <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
                  <div className="flex items-center justify-between border-b border-blue-200 pb-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-blue-700">Target Replay Result</span>
                    <span className="font-mono text-xs font-semibold text-blue-900">
                      {replayResult.replay_assessment.rule_code} v{replayResult.replay_assessment.rule_version}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-sm font-medium text-blue-950">Simulated Result:</span>
                    <span
                      className={`rounded px-2.5 py-0.5 text-xs font-bold ${
                        replayResult.replay_assessment.evaluation_result === "COMPLIANT"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {replayResult.replay_assessment.evaluation_result}
                    </span>
                  </div>
                  <div className="mt-4 space-y-2 text-xs">
                    {replayResult.replay_assessment.conditions.map((c: any) => (
                      <div key={c.condition_id} className="rounded-lg border border-blue-200 bg-white p-2.5">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-800">{c.title}</span>
                          <span className={c.passed ? "text-emerald-600 font-bold" : "text-red-600 font-bold"}>
                            {c.passed ? "✓ Passed" : "✗ Failed"}
                          </span>
                        </div>
                        <p className="mt-1 text-slate-600">{c.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Newly Identified Issues */}
              {replayResult.newly_identified_issues.length > 0 && (
                <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-900">
                  <div className="flex items-center gap-1.5 font-bold text-red-950">
                    <svg className="h-4 w-4 shrink-0 text-red-600" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span>Newly Identified Compliance Issues Under Target Version:</span>
                  </div>
                  <ul className="mt-2 list-inside list-disc space-y-1">
                    {replayResult.newly_identified_issues.map((i: any, idx: number) => (
                      <li key={idx}>
                        <span className="font-semibold">{i.title}:</span> {i.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: IMPACT ANALYSIS */}
      {tab === "impact" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Impact Analysis on Open Cases</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Examines all OPEN and IN-PROGRESS FDR records against a target regulation version to identify cases
                  requiring scrutiny before policy transition.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={impactRuleId ?? ""}
                  onChange={(e) => {
                    const id = Number(e.target.value);
                    setImpactRuleId(id);
                    handleRunImpact(id);
                  }}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
                >
                  {rules.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.rule_code} v{r.version} ({r.status})
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => impactRuleId && handleRunImpact(impactRuleId)}
                  disabled={analyzing}
                  className="rounded-lg bg-[#0f2d52] px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-[#1a3d6b] disabled:opacity-50"
                >
                  {analyzing ? "Scanning…" : "Recalculate Impact"}
                </button>
              </div>
            </div>
          </div>

          {analyzing && <div className="p-10 text-center text-sm text-slate-500">Scanning open deposits…</div>}

          {impactData && !analyzing && (
            <div className="space-y-6">
              {/* Metric Cards */}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs font-medium text-slate-500">Total In-Progress Cases</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{impactData.total_open_cases_scanned}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs font-medium text-slate-500">Potentially Affected</p>
                  <p className="mt-1 text-2xl font-bold text-red-600">{impactData.summary.potentially_affected_count}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs font-medium text-slate-500">Manual Review Required</p>
                  <p className="mt-1 text-2xl font-bold text-amber-600">{impactData.summary.requires_manual_review_count}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs font-medium text-slate-500">No Detected Impact</p>
                  <p className="mt-1 text-2xl font-bold text-emerald-600">{impactData.summary.no_detected_impact_count}</p>
                </div>
              </div>

              {/* Potentially Affected Cases Table */}
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 bg-red-50/50 px-5 py-3">
                  <h3 className="text-sm font-bold text-red-950">
                    Potentially Affected In-Progress FDR Cases ({impactData.potentially_affected.length})
                  </h3>
                </div>

                {impactData.potentially_affected.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-500">
                    No open cases would be adversely affected under {impactData.rule_code} v{impactData.rule_version}.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase text-slate-600">
                        <tr>
                          <th className="px-4 py-2.5">FDR Reference</th>
                          <th className="px-4 py-2.5">Bank</th>
                          <th className="px-4 py-2.5">Current Status</th>
                          <th className="px-4 py-2.5">Impact Analysis Explanation</th>
                          <th className="px-4 py-2.5 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {impactData.potentially_affected.map((c: any) => (
                          <tr key={c.deposit_id} className="hover:bg-red-50/20">
                            <td className="px-4 py-3 font-mono font-medium text-blue-700">
                              <Link href={`/deposits/${c.deposit_id}`}>{c.reference_no}</Link>
                            </td>
                            <td className="px-4 py-3 text-slate-700">{c.bank_name}</td>
                            <td className="px-4 py-3 font-semibold text-slate-800">{c.current_status}</td>
                            <td className="px-4 py-3 text-red-700">{c.impact_reason}</td>
                            <td className="px-4 py-3 text-right">
                              <Link
                                href={`/deposits/${c.deposit_id}`}
                                className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-700 hover:bg-slate-200"
                              >
                                View FDR →
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create Rule Version Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-slate-900">Create Regulation Version Draft</h2>
            <form onSubmit={handleCreateRule} className="mt-4 space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700">Rule Code</label>
                  <input
                    type="text"
                    required
                    value={ruleCode}
                    onChange={(e) => setRuleCode(e.target.value)}
                    className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700">Version</label>
                  <input
                    type="text"
                    required
                    value={ruleVersion}
                    onChange={(e) => setRuleVersion(e.target.value)}
                    className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700">Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. AICTE Security Deposit Framework 2025"
                  value={ruleTitle}
                  onChange={(e) => setRuleTitle(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700">Description</label>
                <textarea
                  rows={2}
                  required
                  placeholder="Official policy purpose and scope..."
                  value={ruleDesc}
                  onChange={(e) => setRuleDesc(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700">Min Tenure (Months)</label>
                  <input
                    type="number"
                    min="1"
                    value={minTenureMonths}
                    onChange={(e) => setMinTenureMonths(Number(e.target.value))}
                    className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700">Min Amount (INR)</label>
                  <input
                    type="number"
                    min="0"
                    value={minAmount}
                    onChange={(e) => setMinAmount(Number(e.target.value))}
                    className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="zeroDisc"
                  checked={requireZeroDiscrepancy}
                  onChange={(e) => setRequireZeroDiscrepancy(e.target.checked)}
                />
                <label htmlFor="zeroDisc" className="font-semibold text-slate-700">
                  Require Zero Discrepancy (Strict Match)
                </label>
              </div>

              <div>
                <label className="font-semibold text-slate-700">Source Reference</label>
                <input
                  type="text"
                  value={sourceRef}
                  onChange={(e) => setSourceRef(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700">Version Change Summary</label>
                <input
                  type="text"
                  placeholder="e.g. Updated minimum tenure requirement"
                  value={changeSummary}
                  onChange={(e) => setChangeSummary(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-xs"
                />
              </div>

              <div className="mt-4 flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded bg-[#0f2d52] px-4 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-[#1a3d6b] disabled:opacity-50"
                >
                  {creating ? "Saving…" : "Save Draft Version"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Shell>
  );
}
