"use client";

import { useRouter } from "next/navigation";
import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Notice, PageTitle, Shell } from "@/components/Shell";
import { api, apiUpload, Extracted, Institution } from "@/lib/api";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED = ["application/pdf", "image/png", "image/jpeg"];

type Form = {
  institution_id: string;
  reference_no: string;
  bank_name: string;
  amount: string;
  issue_date: string;
  maturity_date: string;
};

const EMPTY: Form = {
  institution_id: "",
  reference_no: "",
  bank_name: "",
  amount: "",
  issue_date: "",
  maturity_date: "",
};

function validate(form: Form, file: File | null): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.institution_id) errors.institution_id = "Choose an institution.";
  if (!form.reference_no.trim()) errors.reference_no = "FDR number is required.";
  if (!form.bank_name.trim()) errors.bank_name = "Bank name is required.";
  const amount = Number(form.amount);
  if (!form.amount || Number.isNaN(amount) || amount <= 0) errors.amount = "Enter an amount greater than zero.";
  if (!form.issue_date) errors.issue_date = "Issue date is required.";
  if (!form.maturity_date) errors.maturity_date = "Maturity date is required.";
  if (form.issue_date && form.maturity_date && form.maturity_date <= form.issue_date) {
    errors.maturity_date = "Maturity must be after the issue date.";
  }
  if (file) {
    if (!ACCEPTED.includes(file.type)) errors.file = "Only PDF, PNG or JPEG files are allowed.";
    else if (file.size > MAX_BYTES) errors.file = "File is larger than 10 MB.";
  }
  return errors;
}

function Field({
  label,
  name,
  error,
  children,
}: {
  label: string;
  name: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block" htmlFor={name}>
      <span className="text-sm font-medium">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";

export default function NewDepositPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dragging, setDragging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [readNotes, setReadNotes] = useState<string[]>([]);

  useEffect(() => {
    api<Institution[]>("/institutions")
      .then(setInstitutions)
      .catch((err) => setServerError(err instanceof Error ? err.message : "Could not load institutions"));
  }, []);

  function update(name: keyof Form, value: string) {
    setForm((f) => ({ ...f, [name]: value }));
  }

  async function pickFile(candidate: File | undefined) {
    if (!candidate) return;
    setFile(candidate);
    setErrors((e) => {
      const { file: _, ...rest } = e;
      return rest;
    });
    if (!ACCEPTED.includes(candidate.type)) return;

    // Suggest values from the document. Only empty fields are filled, and the user checks every value.
    setReading(true);
    setReadNotes([]);
    try {
      const result = await apiUpload<Extracted>("/extract/fdr", candidate);
      setForm((f) => ({
        ...f,
        reference_no: f.reference_no || result.fields.reference_no || "",
        bank_name: f.bank_name || result.fields.bank_name || "",
        amount: f.amount || result.fields.amount || "",
        issue_date: f.issue_date || result.fields.issue_date || "",
        maturity_date: f.maturity_date || result.fields.maturity_date || "",
      }));
      const notes = [...result.warnings];
      if (result.engine !== "none" && Object.values(result.fields).some(Boolean)) {
        notes.unshift("Suggested values were read from the document. Check every field before saving.");
      }
      setReadNotes(notes);
    } catch (err) {
      setReadNotes([`Could not read the document: ${err instanceof Error ? err.message : "unknown error"}. Enter the fields by hand.`]);
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

    setSaving(true);
    try {
      const created = await api<{ id: number }>("/deposits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          institution_id: Number(form.institution_id),
          reference_no: form.reference_no.trim(),
          bank_name: form.bank_name.trim(),
          amount: form.amount,
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

  return (
    <Shell>
      <PageTitle title="New FDR" subtitle="Enter the details exactly as they appear on the receipt, then attach the scan." />

      {serverError && <Notice kind="error">{serverError}</Notice>}

      <form onSubmit={submit} noValidate className="grid max-w-3xl gap-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Institution" name="institution_id" error={errors.institution_id}>
            <select id="institution_id" className={inputClass} value={form.institution_id} onChange={(e) => update("institution_id", e.target.value)}>
              <option value="">Select…</option>
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name} ({i.code})
                </option>
              ))}
            </select>
          </Field>
          <Field label="FDR number" name="reference_no" error={errors.reference_no}>
            <input id="reference_no" className={inputClass} value={form.reference_no} onChange={(e) => update("reference_no", e.target.value)} />
          </Field>
          <Field label="Bank" name="bank_name" error={errors.bank_name}>
            <input id="bank_name" className={inputClass} value={form.bank_name} onChange={(e) => update("bank_name", e.target.value)} />
          </Field>
          <Field label="Amount (₹)" name="amount" error={errors.amount}>
            <input id="amount" inputMode="decimal" className={inputClass} value={form.amount} onChange={(e) => update("amount", e.target.value)} />
          </Field>
          <Field label="Issue date" name="issue_date" error={errors.issue_date}>
            <input id="issue_date" type="date" className={inputClass} value={form.issue_date} onChange={(e) => update("issue_date", e.target.value)} />
          </Field>
          <Field label="Maturity date" name="maturity_date" error={errors.maturity_date}>
            <input id="maturity_date" type="date" className={inputClass} value={form.maturity_date} onChange={(e) => update("maturity_date", e.target.value)} />
          </Field>
        </div>

        <div>
          <span className="text-sm font-medium">FDR document</span>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`mt-1 cursor-pointer rounded-xl border-2 border-dashed p-8 text-center text-sm ${
              dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 hover:bg-slate-50"
            }`}
          >
            {file ? (
              <p>
                <span className="font-medium">{file.name}</span> · {(file.size / 1024).toFixed(0)} KB
              </p>
            ) : (
              <p className="text-slate-600">Drag a PDF, PNG or JPEG here, or click to choose a file (max 10 MB)</p>
            )}
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,image/png,image/jpeg"
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
          </div>
          {errors.file && <span className="mt-1 block text-xs text-red-600">{errors.file}</span>}
          {reading && <p className="mt-2 text-sm text-indigo-700">Reading the document…</p>}
          {readNotes.length > 0 && (
            <ul className="mt-2 space-y-1 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
              {readNotes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {saving ? "Saving…" : "Submit FDR"}
          </button>
          <button type="button" onClick={() => router.push("/deposits")} className="text-sm text-slate-600 hover:underline">
            Cancel
          </button>
        </div>
      </form>
    </Shell>
  );
}
