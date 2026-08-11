const FALLBACK_TIMEZONE = "America/Los_Angeles";

/** Browser IANA timezone (e.g. America/Los_Angeles). Falls back if unavailable. */
export function getLocalTimezone(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone?.trim();
    if (tz) return tz;
  } catch {
    // ignore
  }
  return FALLBACK_TIMEZONE;
}
