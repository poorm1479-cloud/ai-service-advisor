"use client";

import { useLayoutEffect } from "react";
import Image from "next/image";
import { BrandLogo, BrandWordmark } from "@/components/BrandLogo";
import { RegisterForm } from "@/components/RegisterForm";

export default function RegisterPage() {
  useLayoutEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const scrollY = window.scrollY;
    html.classList.add("auth-lock");
    body.style.top = `-${scrollY}px`;
    body.style.position = "fixed";
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";
    return () => {
      html.classList.remove("auth-lock");
      body.style.position = "";
      body.style.top = "";
      body.style.left = "";
      body.style.right = "";
      body.style.width = "";
      window.scrollTo(0, scrollY);
    };
  }, []);

  return (
    <main className="auth-lock fixed inset-0 z-10 grid h-[100dvh] w-full grid-cols-1 grid-rows-[minmax(0,1fr)] overflow-hidden overscroll-none lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      <aside className="relative isolate hidden min-h-0 overflow-hidden bg-[#141414] lg:block">
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

        <div className="relative flex h-full flex-col justify-between px-10 py-10 xl:px-14">
          <BrandLogo
            size={42}
            priority
            wordmarkClassName="text-lg font-semibold tracking-tight text-white/70 transition-colors hover:text-white"
          />

          <div className="max-w-lg pb-6">
            <p
              className="text-[clamp(2.6rem,4.2vw,3.75rem)] leading-[0.95] tracking-[-0.04em] text-white"
              style={{ textShadow: "0 1px 2px rgba(0,0,0,0.35), 0 10px 36px rgba(0,0,0,0.4)" }}
            >
              <BrandWordmark className="text-[1em] leading-none text-white" />
            </p>
            <p className="mt-5 max-w-md text-base font-medium leading-relaxed text-white/78 sm:text-lg">
              Open your shop workspace — voice, SMS, scheduling, and vehicle knowledge ready from day
              one.
            </p>
            <div className="mt-10 flex flex-wrap gap-x-8 gap-y-3 text-sm text-white/55">
              <span>Setup in minutes</span>
              <span className="hidden h-1 w-1 self-center rounded-full bg-white/30 sm:inline-block" />
              <span>Shop-isolated by design</span>
            </div>
          </div>
        </div>
      </aside>

      <section className="auth-canvas relative min-h-0 min-w-0 overflow-hidden">
        <div className="absolute inset-0 flex flex-col px-4 py-6 sm:px-6 sm:py-8">
          <div className="mx-auto flex min-h-0 w-full max-w-[24rem] flex-1 flex-col gap-4">
            <div className="shrink-0 lg:hidden">
              <BrandLogo
                size={40}
                priority
                wordmarkClassName="text-2xl font-extrabold tracking-tight text-[var(--ink)]"
              />
              <p className="mt-1.5 text-sm text-[var(--muted)]">
                Elevated shop software for every bay and every call.
              </p>
            </div>

            <div className="surface-panel auth-panel flex min-h-0 flex-1 flex-col overflow-hidden p-5 sm:p-6">
              <RegisterForm variant="page" />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
