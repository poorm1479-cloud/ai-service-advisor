import Link from "next/link";

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
      <Link href="/" className="font-display text-lg font-semibold tracking-tight">
        AI Service Advisor
      </Link>
      <h1 className="font-display mt-10 text-3xl font-semibold tracking-tight sm:text-4xl">
        Privacy Policy
      </h1>
      <p className="mt-2 text-sm text-[var(--muted)]">Last updated: July 29, 2026</p>
      <div className="surface-panel mt-8 space-y-4 p-6 text-sm leading-relaxed text-[var(--muted)]">
        <p>
          AI Service Advisor processes shop, customer, vehicle, and communication data to provide
          multi-tenant repair-shop operations software.
        </p>
        <p>
          Shop owners can export their shop data and delete their shop account from Billing. Contact
          support for additional privacy requests.
        </p>
        <p>
          We use authentication identifiers (phone/email), usage metering for plan limits, and
          optional third-party providers (Twilio, OpenAI, Stripe) when configured by the operator.
        </p>
      </div>
    </main>
  );
}
