/** Example shown in phone inputs (US E.164 display). */
export const PHONE_PLACEHOLDER = "+1 309 844 9753";

/** Digits only — for storage-agnostic comparisons. */
export function phoneDigits(phone: string | null | undefined): string {
  return (phone ?? "").replace(/\D/g, "");
}

/**
 * True when two phone strings refer to the same number.
 * Tolerates formatting and optional US country code (+1).
 */
export function phonesMatch(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const da = phoneDigits(a);
  const db = phoneDigits(b);
  if (!da || !db) return false;
  if (da === db) return true;
  const national = (d: string) =>
    d.length === 11 && d.startsWith("1") ? d.slice(1) : d;
  const na = national(da);
  const nb = national(db);
  return na.length >= 10 && nb.length >= 10 && na.slice(-10) === nb.slice(-10);
}

/**
 * Format phone input as `+1 NXX NXX XXXX` while typing.
 * Empty stays empty; national digits are always prefixed with +1.
 */
export function formatPhoneInput(raw: string): string {
  const digitsAll = raw.replace(/\D/g, "");
  if (!digitsAll) return "";

  let national = digitsAll.startsWith("1") ? digitsAll.slice(1) : digitsAll;
  national = national.slice(0, 10);
  if (!national) return "+1";

  const parts = [national.slice(0, 3), national.slice(3, 6), national.slice(6, 10)].filter(
    Boolean,
  );
  return `+1 ${parts.join(" ")}`;
}
