export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-16">
      <div className="max-w-2xl text-center">
        <p className="text-sm font-medium uppercase tracking-wide text-indigo-600">AICTE Regulation Bureau</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight">Security Deposit and FDR Portal</h1>
        <p className="mt-4 text-lg text-slate-600">
          Record, verify, track and release security deposits and Fixed Deposit Receipts across their full lifecycle.
        </p>

        <div className="mt-10 grid gap-4 text-left sm:grid-cols-2">
          {[
            { title: "Deposit records", text: "Institution-wise and instrument-wise FDR records." },
            { title: "Verification", text: "Flag amount mismatches for scrutiny." },
            { title: "Maturity tracking", text: "Reminders before expiry and renewal." },
            { title: "Release workflow", text: "Request, approve or reject release of deposits." },
          ].map((item) => (
            <div key={item.title} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">{item.title}</h2>
              <p className="mt-1 text-sm text-slate-600">{item.text}</p>
            </div>
          ))}
        </div>

        <p className="mt-10 text-sm text-slate-500">
          Login and dashboard are not connected yet. This is the first placeholder page.
        </p>
      </div>
    </main>
  );
}
