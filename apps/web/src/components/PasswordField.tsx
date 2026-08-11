"use client";

import { type ReactNode, useState } from "react";

type PasswordFieldProps = {
  label: string;
  icon?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  minLength?: number;
  placeholder?: string;
  hint?: string;
  name?: string;
  autoComplete?: string;
  guardAutofill?: boolean;
  disabled?: boolean;
};

export function PasswordField({
  label,
  icon,
  value,
  onChange,
  required,
  minLength,
  placeholder,
  hint,
  name,
  autoComplete = "current-password",
  guardAutofill = false,
  disabled = false,
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);

  return (
    <label className="block space-y-1.5">
      <span className="inline-flex items-center gap-1.5 text-sm font-medium">
        {icon ? <span className="text-[var(--muted)]">{icon}</span> : null}
        {label}
        {required ? <span className="text-red-600"> *</span> : null}
      </span>
      <div className="relative">
        <input
          type={visible ? "text" : "password"}
          name={name}
          value={value}
          placeholder={placeholder}
          required={required}
          aria-required={required || undefined}
          minLength={minLength}
          autoComplete={autoComplete}
          disabled={disabled}
          readOnly={guardAutofill}
          onFocus={(e) => {
            if (guardAutofill) e.currentTarget.readOnly = false;
          }}
          onChange={(e) => onChange(e.target.value)}
          className="auth-input pr-10 disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          disabled={disabled}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="absolute inset-y-0 right-0 flex items-center px-2.5 text-[var(--muted)] hover:text-[var(--foreground)] disabled:opacity-60"
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      {hint ? <span className="block text-xs text-[var(--muted)]">{hint}</span> : null}
    </label>
  );
}

function EyeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2.5 12s3.5-7 9.5-7 9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.75" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 3l18 18M10.6 10.6a2.5 2.5 0 0 0 3.5 3.5M9.9 5.2A10.4 10.4 0 0 1 12 5c6 0 9.5 7 9.5 7a16.6 16.6 0 0 1-2.5 3.4M6.1 6.1C3.8 7.7 2.5 10 2.5 12s3.5 7 9.5 7c1.5 0 2.9-.3 4.1-.8"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
