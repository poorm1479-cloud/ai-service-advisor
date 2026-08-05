import Link from "next/link";

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
      <Link href="/" className="font-display text-lg font-semibold tracking-tight">
        AI Service Advisor
      </Link>
      <h1 className="font-display mt-10 text-3xl font-semibold tracking-tight sm:text-4xl">
        Terms of Service
      </h1>
      <p className="mt-2 text-sm text-[var(--muted)]">Last updated: July 29, 2026</p>
      <div className="surface-panel mt-8 space-y-4 p-6 text-sm leading-relaxed text-[var(--muted)]">
        <p>
          By creating a shop account you agree to use AI Service Advisor only for lawful automotive
          service operations and to keep credentials secure.
        </p>
        <p>
          Paid plans renew monthly unless canceled. Usage over plan quotas may be blocked until you
          upgrade. The Free plan includes a trial period.
        </p>
        <p>
          The service is provided as-is. Operators may suspend shops that abuse SMS, AI, or payment
          systems.
        </p>
      </div>
    </main>
  );
}
