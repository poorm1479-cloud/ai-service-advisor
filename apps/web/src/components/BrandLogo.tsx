import Link from "next/link";

type BrandLogoProps = {
  href?: string;
  /** Hex mark edge length in px (icon-only or embedded “a”) */
  size?: number;
  /** Show full wordmark; false = orange hex mark only */
  wordmark?: boolean;
  /** Accessible name */
  label?: string;
  className?: string;
  wordmarkClassName?: string;
  /** Kept for call-site compatibility; unused (SVG mark) */
  priority?: boolean;
};

/** Brand hexagon + center dot — doubles as the letter “a”. */
export function BrandHexMark({
  size,
  className = "",
  title,
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      <polygon
        points="16,2.5 28.5,9.5 28.5,22.5 16,29.5 3.5,22.5 3.5,9.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="16" r="3.6" fill="currentColor" />
    </svg>
  );
}

export function BrandWordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center font-display font-extrabold lowercase tracking-tight ${className}`}
    >
      <span className="text-inherit">r</span>
      <BrandHexMark className="mx-[0.04em] h-[0.78em] w-[0.78em] shrink-0 text-[var(--accent)]" />
      <span className="text-inherit">tchet</span>
      <span className="text-[var(--accent)]">hub</span>
    </span>
  );
}

export function BrandLogo({
  href = "/",
  size = 40,
  wordmark = true,
  label = "RatchetHub",
  className = "",
  wordmarkClassName = "",
}: BrandLogoProps) {
  const content = wordmark ? (
    <span className={`inline-flex items-center ${className}`}>
      <BrandWordmark className={wordmarkClassName} />
    </span>
  ) : (
    <span className={`inline-flex items-center ${className}`}>
      <BrandHexMark size={size} className="shrink-0 text-[var(--accent)]" title={label} />
      <span className="sr-only">{label}</span>
    </span>
  );

  if (!href) return content;
  return (
    <Link href={href} className="inline-flex items-center" aria-label={label}>
      {content}
    </Link>
  );
}
