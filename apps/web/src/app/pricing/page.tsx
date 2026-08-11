import Link from "next/link";

const PLANS = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    blurb: "14-day trial for independent shops",
    features: ["50 AI calls / mo", "50 SMS / mo", "2 seats"],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$99",
    blurb: "For growing repair shops",
    features: ["200 AI calls / mo", "200 SMS / mo", "4 seats"],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "$299",
    blurb: "Multi-location and custom limits",
    features: ["500 AI calls / mo", "500 SMS / mo", "10 seats"],
  },
];

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-white">
      <header className="site-nav">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <Link href="/" className="font-display text-lg font-extrabold tracking-tight">
            AI Service Advisor
          </Link>
          <div className="flex items-center gap-2 text-sm">
            <Link href="/?login=1" className="rounded-full px-3 py-2 text-[#5c5c5c] hover:text-black">
              Sign in
            </Link>
            <Link href="/register" className="btn-primary py-2">
              Start free
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <p className="section-label">Pricing</p>
        <h1 className="font-display mt-4 max-w-3xl text-4xl font-extrabold tracking-tight sm:text-6xl">
          Feature-rich packages for every shop.
        </h1>
        <p className="mt-5 max-w-2xl text-base text-[#5c5c5c]">
          Simple monthly plans. Upgrade anytime from Billing after you register your shop.
        </p>

        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`flex flex-col rounded-2xl border bg-white p-7 shadow-[0_20px_50px_-36px_rgba(0,0,0,0.35)] ${
                plan.id === "pro"
                  ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/25"
                  : "border-black/8"
              }`}
            >
              <p className="text-sm font-semibold text-[var(--accent)]">{plan.name}</p>
              <p className="font-display mt-3 text-5xl font-extrabold tracking-tight">
                {plan.price}
                <span className="text-base font-medium text-[#5c5c5c]">/mo</span>
              </p>
              <p className="mt-3 text-sm text-[#5c5c5c]">{plan.blurb}</p>
              <ul className="mt-7 flex-1 space-y-3 text-sm text-[#5c5c5c]">
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href="/register"
                className={`mt-8 inline-flex w-full items-center justify-center rounded-full px-4 py-3 text-sm font-semibold ${
                  plan.id === "pro"
                    ? "bg-[var(--accent)] text-white"
                    : "bg-black text-white hover:bg-[#1a1a1a]"
                }`}
              >
                Get started
              </Link>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
