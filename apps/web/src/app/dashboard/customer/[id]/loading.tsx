export default function CustomerDetailLoading() {
  return (
    <div className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden md:h-full">
      <div className="animate-pulse space-y-4 p-5">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-full bg-[var(--background)]" />
          <div className="space-y-2">
            <div className="h-4 w-40 rounded bg-[var(--background)]" />
            <div className="h-3 w-28 rounded bg-[var(--background)]" />
          </div>
        </div>
        <div className="h-9 w-full max-w-sm rounded-lg bg-[var(--background)]" />
        <div className="h-32 rounded-xl bg-[var(--background)]" />
      </div>
    </div>
  );
}
