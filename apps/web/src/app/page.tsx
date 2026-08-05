import Link from "next/link";
import Image from "next/image";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-white text-black">
      <header className="site-nav">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <Link href="/" className="font-display text-lg font-extrabold tracking-tight sm:text-xl">
            AI Service Advisor
          </Link>
          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            <Link
              href="/pricing"
              className="hidden rounded-full px-3 py-2 text-sm font-medium text-[#5c5c5c] hover:text-black sm:inline-flex"
            >
              Pricing
            </Link>
            <Link
              href="/login"
              className="rounded-full px-3 py-2 text-sm font-medium text-[#5c5c5c] hover:text-black"
            >
              Sign in
            </Link>
            <Link href="/register" className="btn-primary">
              Start free
            </Link>
          </div>
        </div>
      </header>

      {/* Hero — brand first, one headline, one sentence, CTAs, full-bleed visual */}
      <section className="relative isolate min-h-[calc(100dvh-4.5rem)] overflow-hidden bg-[#1a1a1a]">
        <div className="absolute inset-0 hero-visual-motion">
          <Image
            src="/marketing/hero-service-bay.png"
            alt=""
            fill
            priority
            className="object-cover object-[center_35%]"
            sizes="100vw"
          />
          {/* Soft natural falloff — no box, image stays open on the right */}
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(105deg, rgba(0,0,0,0.62) 0%, rgba(0,0,0,0.38) 34%, rgba(0,0,0,0.12) 58%, rgba(0,0,0,0.04) 100%)",
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to top, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0.12) 34%, transparent 62%)",
            }}
          />
        </div>

        <div className="relative mx-auto flex min-h-[calc(100dvh-4.5rem)] max-w-6xl flex-col justify-end px-4 pb-16 pt-24 sm:px-6 sm:pb-24">
          <div className="max-w-2xl">
            <p
              className="hero-motion font-display text-[clamp(2.4rem,7vw,4.75rem)] font-extrabold leading-[0.95] tracking-[-0.04em] text-white"
              style={{ textShadow: "0 1px 2px rgba(0,0,0,0.35), 0 8px 32px rgba(0,0,0,0.35)" }}
            >
              AI Service Advisor
            </p>
            <h1
              className="hero-motion-delay mt-4 max-w-2xl font-display text-[clamp(1.35rem,3vw,2.1rem)] font-semibold leading-tight tracking-tight text-white"
              style={{ textShadow: "0 1px 2px rgba(0,0,0,0.3), 0 6px 24px rgba(0,0,0,0.28)" }}
            >
              Raise the standard for every bay and every call.
            </h1>
            <p className="hero-motion-delay relative mt-5 max-w-xl">
              <span
                aria-hidden
                className="pointer-events-none absolute -inset-x-3 -inset-y-2 rounded-2xl bg-black/35 blur-xl"
              />
              <span
                className="relative block text-base font-medium leading-relaxed text-white sm:text-lg"
                style={{
                  textShadow: "0 1px 3px rgba(0,0,0,0.75), 0 8px 24px rgba(0,0,0,0.45)",
                }}
              >
                Turn everyday shop management into an elevated experience — voice, SMS, workflows, and
                vehicle knowledge in one place.
              </span>
            </p>
            <div className="hero-motion-late mt-8 flex flex-wrap gap-3">
              <Link href="/register" className="btn-primary px-6 py-3 text-base shadow-[0_10px_28px_-10px_rgba(240,90,36,0.8)]">
                Book a walkthrough
              </Link>
              <Link
                href="/pricing"
                className="inline-flex items-center justify-center rounded-full border border-white/50 bg-white/12 px-6 py-3 text-base font-semibold text-white shadow-[0_8px_24px_-12px_rgba(0,0,0,0.45)] backdrop-blur-[2px] hover:bg-white/20"
              >
                Take a product tour
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-black/5 bg-white px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-center gap-3 text-center text-sm text-[#6b6b6b] sm:flex-row sm:gap-0">
          <p>Crafted for independent shops</p>
          <span aria-hidden className="mx-5 hidden h-1 w-1 rounded-full bg-black/20 sm:inline-block" />
          <p className="hidden sm:block">AI with a distinctly human touch</p>
          <span aria-hidden className="mx-5 hidden h-1 w-1 rounded-full bg-black/20 sm:inline-block" />
          <p>Every repair, raised higher</p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <p className="section-label">All-in-one</p>
        <h2 className="font-display mt-4 max-w-3xl text-4xl font-extrabold tracking-tight sm:text-5xl">
          Shop software that saves time and grows profit.
        </h2>
        <div className="mt-14 grid gap-10 md:grid-cols-3">
          {[
            {
              kicker: "Efficiency",
              title: "Lightning-fast workflow",
              body: "Replace paper trails and missed calls with AI that books, reminds, and routes work while your team stays on the bay.",
            },
            {
              kicker: "Profitability",
              title: "Smarter opportunities",
              body: "Surface declined estimates, maintenance reminders, and upsell moments with workflows built for repair shops.",
            },
            {
              kicker: "Customer experience",
              title: "Happier customers",
              body: "Precise communication over phone and SMS builds trust, approvals, and five-star reviews that keep cars coming back.",
            },
          ].map((item) => (
            <div key={item.title} className="border-t-2 border-[var(--accent)] pt-6">
              <p className="section-label">{item.kicker}</p>
              <h3 className="font-display mt-3 text-2xl font-bold tracking-tight">{item.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-[#5c5c5c] sm:text-base">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-black px-4 py-20 text-white sm:px-6 sm:py-24">
        <div className="mx-auto max-w-6xl">
          <p className="section-label !text-[var(--signal)]">Results you can see</p>
          <h2 className="font-display mt-4 max-w-2xl text-4xl font-extrabold tracking-tight sm:text-5xl">
            Built for shops that expect more.
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { value: "AI + SMS", label: "Always-on front desk" },
              { value: "Workflows", label: "From walk-in to review" },
              { value: "Memory", label: "Vehicle & shop knowledge" },
              { value: "Multi-tenant", label: "Shop-isolated by design" },
            ].map((stat) => (
              <div key={stat.label} className="border-t border-white/15 pt-5">
                <p className="font-display text-3xl font-extrabold tracking-tight text-[var(--accent)]">
                  {stat.value}
                </p>
                <p className="mt-2 text-sm text-white/65">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <p className="section-label">Solutions</p>
        <h2 className="font-display mt-4 max-w-3xl text-4xl font-extrabold tracking-tight sm:text-5xl">
          Capabilities that handle the whole shop.
        </h2>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ["Voice AI", "Answer and assist customers on the phone without missing a beat."],
            ["SMS Inbox", "Two-way text conversations with AI drafting and shop control."],
            ["Appointments", "Book, reschedule, and fill the schedule with fewer callbacks."],
            ["Marketing", "Reminders, reviews, and campaigns on autopilot."],
            ["Vehicle knowledge", "Health, history, and inspection context for every RO."],
            ["Enterprise", "SSO, multi-location visibility, and franchise controls."],
          ].map(([title, body]) => (
            <div key={title} className="surface-panel p-6 transition hover:-translate-y-0.5 hover:shadow-[0_24px_50px_-32px_rgba(0,0,0,0.35)]">
              <h3 className="font-display text-xl font-bold tracking-tight">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#5c5c5c]">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-black/5 bg-[#f2f2f2] px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="font-display text-4xl font-extrabold tracking-tight sm:text-5xl">
            Fifteen minutes can transform your shop.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-[#5c5c5c]">
            Create your shop, connect the front desk, and see AI Service Advisor in action.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/register" className="btn-primary px-6 py-3 text-base">
              Get started
            </Link>
            <Link href="/login" className="btn-dark px-6 py-3 text-base">
              Sign in
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-black/8 bg-white py-8 text-center text-sm text-[#5c5c5c]">
        <Link href="/privacy" className="hover:text-black">
          Privacy
        </Link>
        <span className="mx-2">·</span>
        <Link href="/terms" className="hover:text-black">
          Terms
        </Link>
        <span className="mx-2">·</span>
        <Link href="/status" className="hover:text-black">
          Status
        </Link>
      </footer>
    </main>
  );
}
