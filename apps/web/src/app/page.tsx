"use client";

import Link from "next/link";
import Image from "next/image";
import { type MouseEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { BrandLogo, BrandWordmark } from "@/components/BrandLogo";
import { LoginForm } from "@/components/LoginForm";
import { RegisterForm } from "@/components/RegisterForm";

const PLANS = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    features: [
      "Walk-in + VIN decode",
      "Appointments",
      "Customer CRM",
      "Team roles & permissions",
      "CSV / data import",
      "10 AI calls / mo",
      "2 seats",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$150",
    features: [
      "Walk-in + VIN decode",
      "Appointments",
      "Customer CRM",
      "Team roles & permissions",
      "CSV / data import",
      "150 AI calls / mo",
      "4 seats",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "$400",
    features: [
      "Walk-in + VIN decode",
      "Appointments",
      "Customer CRM",
      "Team roles & permissions",
      "CSV / data import",
      "500 AI calls / mo",
      "10+ seats",
    ],
  },
] as const;

function FitWidthHeadline({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  const ref = useRef<HTMLHeadingElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const fit = () => {
      const parent = el.parentElement;
      if (!parent) return;
      const available = parent.clientWidth;
      if (available <= 0) return;

      // Measure at a known size, then scale exactly to the container width.
      el.style.fontSize = "100px";
      const measured = el.scrollWidth;
      if (measured <= 0) return;
      const next = (available / measured) * 100;
      el.style.fontSize = `${Math.max(12, Math.min(next, 52))}px`;
    };

    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el.parentElement ?? el);
    if (document.fonts?.ready) {
      void document.fonts.ready.then(fit);
    }
    return () => ro.disconnect();
  }, [children]);

  return (
    <h2 ref={ref} className={className}>
      {children}
    </h2>
  );
}

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/dashboard";
  if (raw === "/admin" || raw.startsWith("/admin/")) return "/dashboard";
  return raw;
}

export default function HomePage() {
  const router = useRouter();
  const [loginOpen, setLoginOpen] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [loginNext, setLoginNext] = useState("/dashboard");
  const [portalReady, setPortalReady] = useState(false);

  useEffect(() => {
    setPortalReady(true);
    const params = new URLSearchParams(window.location.search);
    if (params.has("login")) {
      setLoginNext(safeNextPath(params.get("next")));
      setRegisterOpen(false);
      setLoginOpen(true);
      router.replace("/", { scroll: false });
    } else if (params.has("register")) {
      setLoginOpen(false);
      setRegisterOpen(true);
      router.replace("/", { scroll: false });
    }
  }, [router]);

  useEffect(() => {
    if (!loginOpen && !registerOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setLoginOpen(false);
        setRegisterOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [loginOpen, registerOpen]);

  function openLogin(e?: MouseEvent) {
    e?.preventDefault();
    setLoginNext("/dashboard");
    setRegisterOpen(false);
    setLoginOpen(true);
  }

  function closeLogin() {
    setLoginOpen(false);
  }

  function openRegister(e?: MouseEvent) {
    e?.preventDefault();
    setLoginOpen(false);
    setRegisterOpen(true);
  }

  function closeRegister() {
    setRegisterOpen(false);
  }

  function switchToLogin() {
    setRegisterOpen(false);
    setLoginNext("/dashboard");
    setLoginOpen(true);
  }

  function switchToRegister() {
    setLoginOpen(false);
    setRegisterOpen(true);
  }

  return (
    <main
      className={`landing bg-[#121212] text-[#111111]${
        loginOpen || registerOpen ? " landing--modal-open" : ""
      }`}
    >
      <header className="landing-nav landing-nav--solid">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <BrandLogo
            size={44}
            priority
            wordmarkClassName="text-xl font-semibold tracking-tight text-black sm:text-2xl"
          />
          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            <button
              type="button"
              onClick={openLogin}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-[#5c5c5c] transition-colors hover:text-black"
            >
              <svg
                className="h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              Sign in
            </button>
            <button type="button" onClick={openRegister} className="btn-primary gap-1.5">
              <svg
                className="h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
                <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
                <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
                <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
              </svg>
              Start free
            </button>
          </div>
        </div>
      </header>

      {/* Hero — brand first, one composition, full-bleed visual */}
      <section className="relative isolate min-h-dvh overflow-hidden bg-[#121212]">
        <div className="absolute inset-0 hero-visual-motion">
          <Image
            src="/marketing/hero-service-bay.png"
            alt=""
            fill
            priority
            className="object-cover object-[center_22%] scale-[1.02] sm:object-[center_32%]"
            sizes="100vw"
          />
          <div className="landing-hero-veil" aria-hidden />
          <div className="landing-hero-grain" aria-hidden />
        </div>

        <div className="relative mx-auto flex min-h-dvh w-full max-w-6xl flex-col px-4 pb-[max(1.25rem,env(safe-area-inset-bottom,0px))] pt-[calc(4.75rem+env(safe-area-inset-top,0px))] [container-type:inline-size] sm:px-6 sm:pb-[max(2.5rem,env(safe-area-inset-bottom,0px))] sm:pt-[calc(7rem+env(safe-area-inset-top,0px))] lg:pb-12">
          <div className="flex min-h-0 flex-1 flex-col justify-end pb-[clamp(2.75rem,12dvh,5.5rem)] sm:pb-0">
            <div className="max-w-3xl pl-3 sm:mb-14 sm:pl-0 sm:pb-4 lg:mb-16">
              <p className="hero-motion text-[clamp(2.4rem,12vw,5.5rem)] leading-[0.92] tracking-[-0.045em] text-white">
                <BrandWordmark className="text-[1em] leading-none text-white" />
              </p>
              <h1 className="hero-motion-delay mt-4 max-w-xl font-display text-[clamp(1.2rem,4.6vw,1.85rem)] font-medium leading-snug tracking-[-0.02em] text-white sm:mt-6">
                Raise the standard for every bay and every call.
              </h1>
              <p className="hero-motion-delay mt-3.5 max-w-[22rem] text-[0.9rem] leading-relaxed text-white/90 sm:mt-5 sm:max-w-lg sm:text-base sm:text-white">
                Voice, workflows, and vehicle knowledge — composed into one elevated front desk for
                independent shops.
              </p>
            </div>
          </div>

          <ul className="hero-motion-late grid w-full shrink-0 grid-cols-3 border-t border-white/15 pt-4 sm:pt-6">
            {["Independent shops", "Human-led AI", "Every repair, elevated"].map((label, i) => (
              <li
                key={label}
                className={`px-1 text-center sm:px-3 ${
                  i > 0 ? "border-l border-white/15" : ""
                }`}
              >
                <span className="block font-display text-[0.68rem] font-medium leading-snug tracking-[-0.01em] text-white/70 sm:text-[0.8rem] sm:text-white/60 md:text-[0.9rem]">
                  {label}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="landing-hero-line" aria-hidden />
      </section>

      <section className="bg-[#f2f2f2]">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
          <div className="w-full">
            <p className="section-label">All-in-one</p>
            <FitWidthHeadline className="font-display mt-2 w-full whitespace-nowrap font-extrabold leading-[1.05] tracking-[-0.035em]">
              Shop software that saves time and grows profit.
            </FitWidthHeadline>
          </div>

          <div className="mt-6 grid gap-4 sm:mt-8 sm:gap-5 md:grid-cols-3">
            {[
              {
                num: "01",
                title: "Lightning-fast workflow",
                body: "Replace paper trails and missed calls with AI that books, reminds, and routes work while your team stays on the bay.",
                icon: <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />,
              },
              {
                num: "02",
                title: "Smarter opportunities",
                body: "Surface declined estimates, maintenance reminders, and upsell moments with workflows built for repair shops.",
                icon: (
                  <>
                    <path d="M3 3v18h18" />
                    <path d="m19 9-5 5-4-4-3 3" />
                  </>
                ),
              },
              {
                num: "03",
                title: "Happier customers",
                body: "Precise communication over the phone builds trust, approvals, and five-star reviews that keep cars coming back.",
                icon: (
                  <>
                    <path d="M12 2l2.4 7.4H22l-6 4.6 2.3 7-6.3-4.6L5.7 21l2.3-7-6-4.6h7.6L12 2z" />
                  </>
                ),
              },
            ].map((item) => (
              <div
                key={item.num}
                className="landing-feature-card rounded-2xl px-6 py-8 sm:px-7 sm:py-10"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-[11px] tracking-[0.16em] text-[var(--accent)]">{item.num}</p>
                  <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[rgba(240,90,36,0.18)] bg-[var(--accent-soft)] text-[var(--accent)]">
                    <svg
                      className="h-5 w-5"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.75"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      {item.icon}
                    </svg>
                  </span>
                </div>
                <h3 className="font-display mt-4 text-xl font-bold tracking-tight sm:text-2xl">{item.title}</h3>
                <p className="mt-4 text-sm leading-relaxed text-[#5c5c5c] sm:text-[0.95rem]">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden bg-[#111111] px-4 py-10 text-white sm:px-6 sm:py-14">
        <div className="landing-dark-glow" aria-hidden />
        <div className="relative mx-auto max-w-6xl">
          <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-end lg:gap-10">
            <div>
              <p className="section-label !text-[var(--signal)]">Built differently</p>
              <h2 className="font-display mt-2 max-w-xl text-[clamp(2rem,4.2vw,3.1rem)] font-extrabold leading-[1.05] tracking-[-0.035em]">
                Everything the front desk needs — without the noise.
              </h2>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-white/55 sm:text-base">
                From the first ring to the final review, RatchetHub keeps the shop calm,
                precise, and always ready.
              </p>
            </div>
            <ul className="space-y-0 border-t border-white/10">
              {[
                {
                  title: "Voice AI",
                  body: "Answer and assist without missing a beat.",
                  icon: (
                    <>
                      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92z" />
                    </>
                  ),
                },
                {
                  title: "Appointments",
                  body: "Fill the schedule with fewer callbacks.",
                  icon: (
                    <>
                      <rect x="3" y="4" width="18" height="18" rx="2" />
                      <path d="M16 2v4M8 2v4M3 10h18" />
                    </>
                  ),
                },
                {
                  title: "Marketing",
                  body: "Reminders, reviews, and campaigns on autopilot.",
                  icon: (
                    <>
                      <path d="M22 2 11 13" />
                      <path d="M22 2 15 22 11 13 2 9l20-7z" />
                    </>
                  ),
                },
                {
                  title: "Vehicle knowledge",
                  body: "Health, history, and context for every RO.",
                  icon: (
                    <>
                      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                    </>
                  ),
                },
              ].map(({ title, body, icon }) => (
                <li
                  key={title}
                  className="group flex flex-col gap-1.5 border-b border-white/10 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:py-4"
                >
                  <span className="flex items-center gap-3">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-[var(--signal)] transition-colors group-hover:border-[var(--signal)]/40 group-hover:bg-[var(--signal)]/10">
                      <svg
                        className="h-[18px] w-[18px]"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden
                      >
                        {icon}
                      </svg>
                    </span>
                    <span className="font-display text-lg font-semibold tracking-tight text-white transition-colors group-hover:text-[var(--signal)] sm:text-xl">
                      {title}
                    </span>
                  </span>
                  <span className="pl-12 text-sm leading-relaxed text-white/45 sm:pl-0 sm:whitespace-nowrap sm:text-right">
                    {body}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Pricing — last content section */}
      <section id="pricing" className="relative overflow-hidden bg-[#ececec] px-4 py-12 sm:px-6 sm:py-16">
        <div className="relative mx-auto max-w-6xl">
          <h2 className="section-label">Pricing</h2>
          <p className="mt-3 text-sm leading-relaxed text-[#5c5c5c] sm:text-base">
            Simple monthly plans. Upgrade anytime from Billing.
          </p>

          <div className="mt-8 grid gap-3 sm:mt-10 sm:gap-4 md:grid-cols-3 md:items-stretch">
            {PLANS.map((plan, index) => {
              const isPro = plan.id === "pro";
              const canStart = plan.id === "free";
              return (
                <div
                  key={plan.id}
                  className={`landing-plan-card ${isPro ? "landing-plan-card--featured" : ""}`}
                  style={{ animationDelay: `${index * 80}ms` }}
                >
                  <h3 className="font-display text-xl font-bold tracking-tight sm:text-2xl">
                    {plan.name}
                  </h3>

                  <p className="mt-4 flex items-end gap-1.5">
                    <span className="font-display text-[2.6rem] font-extrabold leading-none tracking-[-0.04em] sm:text-[2.75rem]">
                      {plan.price}
                    </span>
                    <span className="mb-1 text-sm text-[#8a8a8a]">/mo</span>
                  </p>

                  <div className="my-5 h-px bg-gradient-to-r from-black/10 via-black/5 to-transparent" aria-hidden />

                  <ul className="flex-1 space-y-2.5 text-sm text-[#5c5c5c]">
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-center gap-2.5">
                        <span className="h-1 w-1 shrink-0 rounded-full bg-[var(--accent)]" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>

                  <button
                    type="button"
                    disabled={!canStart}
                    aria-disabled={!canStart}
                    onClick={canStart ? openRegister : undefined}
                    className={`mt-7 inline-flex w-full items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition ${
                      canStart
                        ? "bg-[var(--accent)] text-white shadow-[0_14px_32px_-14px_rgba(240,90,36,0.85)] hover:bg-[var(--accent-hover)]"
                        : isPro
                          ? "border border-black/12 bg-black/[0.03] text-[#8a8a8a] cursor-not-allowed"
                          : "border border-black/10 text-[#9a9a9a] cursor-not-allowed"
                    }`}
                  >
                    {canStart ? "Get started" : "Upgrade in Billing"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <footer className="landing-footer relative overflow-hidden">
        <div className="landing-footer-glow" aria-hidden />
        <div className="landing-footer-line" aria-hidden />
        <div className="relative mx-auto flex max-w-6xl flex-col items-center px-4 py-7 text-center sm:px-6 sm:py-8">
          <p className="font-display text-[0.7rem] font-semibold uppercase tracking-[0.28em] text-[var(--accent)]">
            Independent shops
          </p>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-[#6b6b6b]">
            Crafted for shops that treat service as a craft.
          </p>
          <div className="mt-4 h-px w-12 bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent opacity-70" aria-hidden />
          <p className="mt-3 font-mono text-[10px] tracking-[0.18em] text-[#9a9a9a]">
            © {new Date().getFullYear()}
          </p>
        </div>
      </footer>

      {portalReady &&
        loginOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-end justify-center overflow-hidden overscroll-none bg-black/60 p-4 backdrop-blur-[6px] sm:items-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="home-login-title"
            onClick={closeLogin}
          >
            <div
              className="auth-form-motion surface-panel auth-panel flex max-h-[min(92dvh,42rem)] w-full max-w-[26rem] flex-col overflow-hidden p-6 pb-5 sm:p-8 sm:pb-6"
              onClick={(e) => e.stopPropagation()}
            >
              <LoginForm
                variant="modal"
                nextPath={loginNext}
                onClose={closeLogin}
                onSwitchToRegister={switchToRegister}
              />
            </div>
          </div>,
          document.body,
        )}

      {portalReady &&
        registerOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-end justify-center overflow-hidden overscroll-none bg-black/60 p-4 backdrop-blur-[6px] sm:items-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="home-register-title"
            onClick={closeRegister}
          >
            <div
              className="auth-form-motion surface-panel auth-panel flex max-h-[min(92dvh,48rem)] w-full max-w-[28rem] flex-col overflow-hidden p-6 pb-5 sm:p-8 sm:pb-6"
              onClick={(e) => e.stopPropagation()}
            >
              <RegisterForm
                variant="modal"
                onClose={closeRegister}
                onSwitchToLogin={switchToLogin}
              />
            </div>
          </div>,
          document.body,
        )}
    </main>
  );
}
