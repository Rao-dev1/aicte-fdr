"use client";

import { useRouter } from "next/navigation";
import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import {
  api,
  apiUpload,
  formatFileSize,
  Institution,
  money,
  parseCleanAmount,
  StructuredExtracted,
} from "@/lib/api";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED = ["application/pdf", "image/png", "image/jpeg"];

type Form = {
  institution_id: string;
  reference_no: string;
  bank_name: string;
  branch_name: string;
  amount: string;
  issue_date: string;
  maturity_date: string;
  interest_rate: string;
};

const EMPTY: Form = {
  institution_id: "",
  reference_no: "",
  bank_name: "",
  branch_name: "",
  amount: "",
  issue_date: "",
  maturity_date: "",
  interest_rate: "",
};

function validate(form: Form, file: File | null): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.institution_id) errors.institution_id = "Choose an institution.";
  if (!form.reference_no.trim()) errors.reference_no = "FDR number is required.";
  if (!form.bank_name.trim()) errors.bank_name = "Bank name is required.";

  const parsedAmount = parseCleanAmount(form.amount);
  if (!parsedAmount) {
    errors.amount = "Enter an amount greater than zero (e.g. 10000 or 1,00,000.00).";
  }

  if (!form.issue_date) errors.issue_date = "Issue date is required.";
  if (!form.maturity_date) errors.maturity_date = "Maturity date is required.";
  if (form.issue_date && form.maturity_date && form.maturity_date <= form.issue_date) {
    errors.maturity_date = "Maturity must be strictly after the issue date.";
  }

  if (file) {
    if (!ACCEPTED.includes(file.type)) {
      errors.file = "Only PDF, PNG or JPEG files are allowed.";
    } else if (file.size === 0) {
      errors.file = "The selected file is empty (0 bytes). Please upload a valid document.";
    } else if (file.size > MAX_BYTES) {
      errors.file = `File is larger than 10 MB (${formatFileSize(file.size)}).`;
    }
  }
  return errors;
}

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-600 focus:ring-2 focus:ring-blue-100";

export default function NewDepositPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [docPreviewUrl, setDocPreviewUrl] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dragging, setDragging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  // FEATURE 2: Explainable Extraction State
  const [reading, setReading] = useState(false);
  const [extractedData, setExtractedData] = useState<StructuredExtracted | null>(null);
  const [extractionNotes, setExtractionNotes] = useState<string[]>([]);
  const [institutionMismatchWarning, setInstitutionMismatchWarning] = useState<string | null>(null);

  useEffect(() => {
    api<Institution[]>("/institutions")
      .then(setInstitutions)
      .catch((err) => setServerError(err instanceof Error ? err.message : "Could not load institutions"));
  }, []);

  // Update object URL whenever selected file changes
  useEffect(() => {
    if (!file) {
      setDocPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setDocPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function update(name: keyof Form, value: string) {
    setForm((f) => ({ ...f, [name]: value }));
  }

  // Cross-check selected institution against extracted institution
  useEffect(() => {
    if (!form.institution_id || !extractedData?.fields?.institution_name) {
      setInstitutionMismatchWarning(null);
      return;
    }
    const selectedInst = institutions.find((i) => String(i.id) === String(form.institution_id));
    if (!selectedInst) return;

    const extractedName = extractedData.fields.institution_name.toLowerCase();
    const instName = selectedInst.name.toLowerCase();
    const instCode = selectedInst.code.toLowerCase();

    // Check if any major word from institution name appears in extracted text
    const words = instName.split(/\s+/).filter((w) => w.length > 3);
    const hasOverlap = words.some((w) => extractedName.includes(w)) || extractedName.includes(instCode);

    if (!hasOverlap && extractedName.length > 5) {
      setInstitutionMismatchWarning(
        `Selected institution "${selectedInst.name}" does not match the account title detected in document ("${extractedData.fields.institution_name}"). Please verify.`
      );
    } else {
      setInstitutionMismatchWarning(null);
    }
  }, [form.institution_id, extractedData, institutions]);

  async function pickFile(candidate: File | undefined) {
    if (!candidate) return;
    setFile(candidate);
    setExtractionNotes([]);
    setInstitutionMismatchWarning(null);
    setErrors((e) => {
      const { file: _, ...rest } = e;
      return rest;
    });

    if (candidate.size === 0) {
      setErrors((e) => ({ ...e, file: "The selected file is empty (0 bytes). Please choose a valid document." }));
      return;
    }

    if (!ACCEPTED.includes(candidate.type)) {
      setErrors((e) => ({ ...e, file: "Unsupported format. Only PDF, PNG or JPEG files are allowed." }));
      return;
    }

    if (candidate.size > MAX_BYTES) {
      setErrors((e) => ({ ...e, file: `File is too large (${formatFileSize(candidate.size)}). Maximum allowed size is 10 MB.` }));
      return;
    }

    // Process document through explainable backend extraction
    setReading(true);
    try {
      const result = await apiUpload<StructuredExtracted>("/extract/fdr", candidate);
      setExtractedData(result);

      // Auto-populate form fields that are currently empty or freshly extracted
      setForm((f) => {
        const next = { ...f };
        if (result.fields.reference_no) next.reference_no = result.fields.reference_no;
        if (result.fields.bank_name) next.bank_name = result.fields.bank_name;
        if (result.fields.branch_name) next.branch_name = result.fields.branch_name;
        if (result.fields.amount) {
          const p = parseCleanAmount(result.fields.amount);
          next.amount = p ? p.cleaned : result.fields.amount;
        }
        if (result.fields.issue_date) next.issue_date = result.fields.issue_date;
        if (result.fields.maturity_date) next.maturity_date = result.fields.maturity_date;
        if (result.fields.interest_rate) next.interest_rate = result.fields.interest_rate;
        return next;
      });

      const notes: string[] = [];
      const extractedCount = Object.values(result.structured || {}).filter(
        (meta) => meta.status === "Extracted"
      ).length;

      if (extractedCount > 0) {
        notes.push(
          `Document processed via ${result.engine.toUpperCase()}. Successfully identified ${extractedCount} field(s). Review each value below before final submission.`
        );
      } else {
        notes.push("Document processed, but no FDR fields could be detected automatically. Please enter all details manually.");
      }

      if (result.warnings && result.warnings.length > 0) {
        notes.push(...result.warnings);
      }
      setExtractionNotes(notes);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Service unreachable";
      setExtractionNotes([
        `Could not extract values automatically (${msg}). Your document is preserved; please enter values manually.`,
      ]);
    } finally {
      setReading(false);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files[0]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setServerError(null);
    const found = validate(form, file);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const parsedAmount = parseCleanAmount(form.amount);
    if (!parsedAmount) {
      setErrors((prev) => ({ ...prev, amount: "Enter an amount greater than zero." }));
      return;
    }

    setSaving(true);
    try {
      const created = await api<{ id: number }>("/deposits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          institution_id: Number(form.institution_id),
          reference_no: form.reference_no.trim(),
          bank_name: form.bank_name.trim(),
          amount: parsedAmount.cleaned,
          issue_date: form.issue_date,
          maturity_date: form.maturity_date,
        }),
      });
      if (file) await apiUpload(`/deposits/${created.id}/documents`, file);
      router.push(`/deposits/${created.id}`);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Could not save the FDR");
      setSaving(false);
    }
  }

  const cleanAmt = parseCleanAmount(form.amount);

  return (
    <Shell>
      <PageTitle
        title="Submit New Fixed Deposit Receipt"
        subtitle="Upload the bank deposit certificate. Verify extracted fields using the explainability panel before recording."
      />

      {serverError && <Notice kind="error">{serverError}</Notice>}

      {/* Official Safety & Integrity Banner */}
      <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 p-4 shadow-xs">
        <div className="flex items-start gap-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white">
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
          </span>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-blue-900">
              Statutory Verification Directive · AICTE APH
            </h4>
            <p className="mt-0.5 text-xs text-blue-800 leading-relaxed">
              Optical Character Recognition (OCR) and text parsing are assistive only. Extracted values are suggestions and 
              do <b>not</b> constitute certified bank data. Authorized officials must inspect the attached receipt and verify 
              lien clauses before submitting.
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={submit} noValidate>
        {/* Responsive Two-Column Grid: Document Inspector on Left, Verification Form on Right */}
        <div className="grid gap-6 lg:grid-cols-12">
          {/* Column 1: Document Upload & Live Inspector (5 cols) */}
          <div className="space-y-6 lg:col-span-5">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div>
                  <h3 className="text-base font-bold text-[#0c2340]">1. FDR Document Upload</h3>
                  <p className="text-xs text-slate-500">Attach bank-issued FDR certificate or lien advice scan</p>
                </div>
                {file && (
                  <span className="rounded-md bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700">
                    File Attached
                  </span>
                )}
              </div>

              {/* Upload Dropzone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
                className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center text-sm transition-colors ${
                  dragging
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-300 bg-slate-50/70 hover:border-blue-400 hover:bg-blue-50/50"
                }`}
              >
                <span className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </span>
                {file ? (
                  <div className="space-y-1">
                    <p className="font-bold text-slate-900 truncate max-w-[280px]">{file.name}</p>
                    <p className="text-xs text-slate-500">
                      Size: <span className="font-semibold text-slate-700">{formatFileSize(file.size)}</span> · {file.type || "Document"}
                    </p>
                    <p className="text-xs font-semibold text-blue-600 underline hover:text-blue-800">
                      Click or drag to replace document
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="font-semibold text-slate-800">Click to upload or drag & drop</p>
                    <p className="mt-0.5 text-xs text-slate-500">Supported formats: PDF, PNG, JPEG (max 10 MB)</p>
                  </>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/pdf,image/png,image/jpeg"
                  className="hidden"
                  onChange={(e) => {
                    pickFile(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </div>
              {errors.file && <span className="mt-1.5 block text-xs font-semibold text-red-600">{errors.file}</span>}

              {/* Reading Progress State */}
              {reading && (
                <div className="mt-4 flex items-center gap-2.5 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs font-semibold text-blue-800">
                  <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                  Extracting receipt fields & analyzing document text layer…
                </div>
              )}

              {/* Extraction Notes & Engine Details */}
              {extractionNotes.length > 0 && (
                <div className="mt-4 space-y-1 rounded-xl border border-sky-200 bg-sky-50/80 p-3.5 text-xs text-sky-950">
                  <p className="font-bold uppercase tracking-wider text-sky-900 text-[10px]">
                    Extraction Analysis Notes:
                  </p>
                  {extractionNotes.map((note, idx) => (
                    <p key={idx} className="leading-snug">
                      • {note}
                    </p>
                  ))}
                </div>
              )}
            </div>

            {/* Live Document Preview Panel */}
            {docPreviewUrl && (
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
                <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Live Document Inspection
                  </h4>
                  <a
                    href={docPreviewUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-semibold text-blue-600 hover:underline"
                  >
                    Open in new tab ↗
                  </a>
                </div>

                <div className="h-96 w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
                  {file?.type === "application/pdf" ? (
                    <iframe
                      src={docPreviewUrl}
                      className="h-full w-full"
                      title="Uploaded Document Preview"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center p-2">
                      <img
                        src={docPreviewUrl}
                        alt="Document Preview"
                        className="max-h-full max-w-full object-contain rounded-lg"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Column 2: Structured Explainable Verification Form (7 cols) */}
          <div className="space-y-6 lg:col-span-7">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs sm:p-8">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div>
                  <h3 className="text-base font-bold text-[#0c2340]">2. Structured Verification Panel</h3>
                  <p className="text-xs text-slate-500">
                    Review and confirm each field against the uploaded receipt. Correct any discrepancies.
                  </p>
                </div>
                {extractedData && (
                  <span className="rounded-full bg-slate-100 border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700">
                    Engine: {extractedData.engine.toUpperCase()}
                  </span>
                )}
              </div>

              {/* Institution Mismatch Warning */}
              {institutionMismatchWarning && (
                <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3.5 text-xs text-amber-900">
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-amber-700">⚠️</span>
                    <p className="font-medium">{institutionMismatchWarning}</p>
                  </div>
                </div>
              )}

              <div className="mt-6 space-y-5">
                {/* Field: Institution */}
                <div>
                  <div className="flex items-center justify-between">
                    <label htmlFor="institution_id" className="text-xs font-bold uppercase tracking-wider text-slate-700">
                      Approved Institution <span className="text-red-500">*</span>
                    </label>
                  </div>
                  <select
                    id="institution_id"
                    value={form.institution_id}
                    onChange={(e) => update("institution_id", e.target.value)}
                    className={inputClass}
                  >
                    <option value="">Select institution…</option>
                    {institutions.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.name} ({i.code})
                      </option>
                    ))}
                  </select>
                  {errors.institution_id && <p className="mt-1 text-xs text-red-600">{errors.institution_id}</p>}
                </div>

                {/* Field: FDR Reference Number */}
                <FieldRow
                  label="FDR / Receipt Number"
                  fieldKey="reference_no"
                  meta={extractedData?.structured?.reference_no}
                  error={errors.reference_no}
                  required
                >
                  <input
                    id="reference_no"
                    value={form.reference_no}
                    onChange={(e) => update("reference_no", e.target.value)}
                    placeholder="e.g. FDR/SBI/2026/884920"
                    className={inputClass}
                  />
                </FieldRow>

                {/* Field: Bank Name */}
                <FieldRow
                  label="Issuing Bank Name"
                  fieldKey="bank_name"
                  meta={extractedData?.structured?.bank_name}
                  error={errors.bank_name}
                  required
                >
                  <input
                    id="bank_name"
                    value={form.bank_name}
                    onChange={(e) => update("bank_name", e.target.value)}
                    placeholder="e.g. State Bank of India"
                    className={inputClass}
                  />
                </FieldRow>

                {/* Field: Branch Name (Optional / Contextual) */}
                <FieldRow
                  label="Bank Branch"
                  fieldKey="branch_name"
                  meta={extractedData?.structured?.branch_name}
                >
                  <input
                    id="branch_name"
                    value={form.branch_name}
                    onChange={(e) => update("branch_name", e.target.value)}
                    placeholder="e.g. Nariman Point Branch, Mumbai"
                    className={inputClass}
                  />
                </FieldRow>

                {/* Field: Amount */}
                <FieldRow
                  label="Deposit Amount (₹)"
                  fieldKey="amount"
                  meta={extractedData?.structured?.amount}
                  error={errors.amount}
                  required
                >
                  <input
                    id="amount"
                    inputMode="decimal"
                    value={form.amount}
                    onChange={(e) => update("amount", e.target.value)}
                    onBlur={(e) => {
                      const p = parseCleanAmount(e.target.value);
                      if (p) update("amount", p.cleaned);
                    }}
                    placeholder="e.g. 3500000.00"
                    className={inputClass}
                  />
                  {cleanAmt && (
                    <p className="mt-1 text-xs font-semibold text-emerald-700">
                      Standard Indian Currency: {money(cleanAmt.numeric)}
                    </p>
                  )}
                </FieldRow>

                {/* Field: Issue Date & Maturity Date */}
                <div className="grid gap-4 sm:grid-cols-2">
                  <FieldRow
                    label="Issue Date"
                    fieldKey="issue_date"
                    meta={extractedData?.structured?.issue_date}
                    error={errors.issue_date}
                    required
                  >
                    <input
                      id="issue_date"
                      type="date"
                      value={form.issue_date}
                      onChange={(e) => update("issue_date", e.target.value)}
                      className={inputClass}
                    />
                  </FieldRow>

                  <FieldRow
                    label="Maturity Date"
                    fieldKey="maturity_date"
                    meta={extractedData?.structured?.maturity_date}
                    error={errors.maturity_date}
                    required
                  >
                    <input
                      id="maturity_date"
                      type="date"
                      value={form.maturity_date}
                      onChange={(e) => update("maturity_date", e.target.value)}
                      className={inputClass}
                    />
                  </FieldRow>
                </div>

                {/* Field: Interest Rate */}
                <FieldRow
                  label="Interest Rate (% p.a.)"
                  fieldKey="interest_rate"
                  meta={extractedData?.structured?.interest_rate}
                >
                  <input
                    id="interest_rate"
                    value={form.interest_rate}
                    onChange={(e) => update("interest_rate", e.target.value)}
                    placeholder="e.g. 7.10%"
                    className={inputClass}
                  />
                </FieldRow>
              </div>

              {/* Action Buttons */}
              <div className="mt-8 flex items-center gap-3 border-t border-slate-100 pt-5">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-[#0c2340] px-6 py-2.5 text-sm font-bold text-white shadow-xs transition hover:bg-[#123a6b] disabled:opacity-60"
                >
                  {saving ? "Saving Verified FDR…" : "Confirm & Submit FDR Record"}
                </button>
                <button
                  type="button"
                  onClick={() => router.push("/deposits")}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      </form>
    </Shell>
  );
}

// Reusable Field Row with Explainability Status Badges & Evidence Snippets
function FieldRow({
  label,
  fieldKey,
  meta,
  error,
  required,
  children,
}: {
  label: string;
  fieldKey: string;
  meta?: {
    value: string | null;
    status: string;
    confidence: number | null;
    evidence: string | null;
  };
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={fieldKey} className="text-xs font-bold uppercase tracking-wider text-slate-700">
          {label} {required && <span className="text-red-500">*</span>}
        </label>

        {/* Explainability Status Pill */}
        {meta && (
          <div className="flex items-center gap-2">
            {meta.status === "Extracted" ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                <span>✓</span> Extracted
              </span>
            ) : meta.status === "Needs review" ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                <span>⚠️</span> Needs review
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                <span>—</span> Not detected
              </span>
            )}
            {/* Show genuine confidence score ONLY if provided by engine, never fake */}
            {meta.confidence !== null && (
              <span className="text-[10px] font-semibold text-slate-500">
                Confidence: {Math.round(meta.confidence * 100)}%
              </span>
            )}
          </div>
        )}
      </div>

      {children}
      {error && <p className="mt-1 text-xs font-semibold text-red-600">{error}</p>}

      {/* Evidence snippet from document */}
      {meta?.evidence && (
        <p className="mt-1 text-[11px] text-slate-500 leading-snug italic truncate">
          Found in document: <span className="text-slate-700 font-medium">"{meta.evidence}"</span>
        </p>
      )}
    </div>
  );
}
