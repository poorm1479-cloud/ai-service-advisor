"use client";

import Image from "next/image";
import Link from "next/link";
import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { LoginForm } from "@/components/LoginForm";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/dashboard";
  if (raw === "/admin" || raw.startsWith("/admin/")) return "/dashboard";
  return raw;
}

function LoginPageInner() {
  const searchParams = useSearchParams();
  const nextPath = useMemo(() => safeNextPath(searchParams.get("next")), [searchParams]);

  return (
    <main className="relative min-h-dvh lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      <aside className="relative isolate hidden min-h-dvh overflow-hidden bg-[#141414] lg:block">
        <div className="absolute inset-0 auth-brand-motion">
          <Image
            src="/marketing/hero-service-bay.png"
            alt=""
            fill
            priority
            className="object-cover object-[center_40%]"
            sizes="55vw"
          />
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(160deg, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.45) 42%, rgba(0,0,0,0.62) 100%)",
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 70% 55% at 20% 85%, rgba(240,90,36,0.28), transparent 60%)",
            }}
          />
        </div>

        <div className="relative flex h-full min-h-dvh flex-col justify-between px-10 py-10 xl:px-14">
          <Link
            href="/"
            className="font-display text-sm font-semibold tracking-[0.18em] text-white/70 transition-colors hover:text-white"
          >
            AI SERVICE ADVISOR
          </Link>

          <div className="auth-form-motion max-w-lg pb-6">
            <p
              className="font-display text-[clamp(2.6rem,4.2vw,3.75rem)] font-extrabold leading-[0.95] tracking-[-0.04em] text-white"
              style={{ textShadow: "0 1px 2px rgba(0,0,0,0.35), 0 10px 36px rgba(0,0,0,0.4)" }}
            >
              AI Service Advisor
            </p>
            <p className="mt-5 max-w-md text-base font-medium leading-relaxed text-white/78 sm:text-lg">
              Sign in to the shop floor OS — voice, SMS, scheduling, and vehicle knowledge in one
              elevated workspace.
            </p>
            <div className="mt-10 flex flex-wrap gap-x-8 gap-y-3 text-sm text-white/55">
              <span>Always-on front desk</span>
              <span className="hidden h-1 w-1 self-center rounded-full bg-white/30 sm:inline-block" />
              <span>Shop-isolated by design</span>
            </div>
          </div>
        </div>
      </aside>

      <section className="auth-canvas relative flex min-h-dvh flex-col justify-center px-4 py-10 sm:px-8 sm:py-14">
        <div className="auth-form-motion mx-auto w-full max-w-[26rem]">
          <div className="mb-8 lg:hidden">
            <Link
              href="/"
              className="font-display text-xl font-extrabold tracking-tight text-[var(--ink)]"
            >
              AI Service Advisor
            </Link>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Elevated shop software for every bay and every call.
            </p>
          </div>

          <div className="surface-panel auth-panel p-6 sm:p-8">
            <LoginForm variant="page" nextPath={nextPath} />
          </div>
        </div>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-dvh items-center justify-center text-sm text-[var(--muted)]">
          Loading…
        </main>
      }
    >
      <LoginPageInner />
    </Suspense>
  );
}
