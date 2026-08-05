/** Example shown in phone inputs (US E.164 display). */
export const PHONE_PLACEHOLDER = "+1 309 844 9753";

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
