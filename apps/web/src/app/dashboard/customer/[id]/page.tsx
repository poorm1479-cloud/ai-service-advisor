"use client";

import { Suspense, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

function RedirectToCustomerList() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const qs = new URLSearchParams(searchParams.toString());
    qs.set("id", params.id);
    router.replace(`/dashboard/customer?${qs.toString()}`);
  }, [params.id, router, searchParams]);

  return <p className="text-sm text-[var(--muted)]">Loading customer…</p>;
}

/** Deep links `/dashboard/customer/[id]` open the list + selected detail panel. */
export default function CustomerDetailPage() {
  return (
    <Suspense
      fallback={
        <p className="text-sm text-[var(--muted)]">Loading customer…</p>
      }
    >
      <RedirectToCustomerList />
    </Suspense>
  );
}
