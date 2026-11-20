---
name: frontend-react
description: |
  Web React/Next.js frontend patterns for fintech browser applications (not React Native or other mobile apps). Component architecture,
  state management, form handling, KYC flows, PII masking, secure data display,
  and testing patterns with Vitest + Testing Library.
  Use when: building React/Next.js frontends, KYC forms, transaction UIs,
  financial dashboards, or any frontend consuming Spring Boot/Go APIs.
  Triggers on: React web app, Next.js, web frontend, browser component, web form, KYC web UI, dashboard,
  PII masking in the browser, transaction display.
---

# React / Next.js (Fintech)

## Stack (adapt if the project differs; fintech rules still apply)

Next.js 14+ App Router or React 18+ SPA · TanStack Query (server state) · Zustand (UI state only) · React Hook Form + Zod · Tailwind or CSS Modules · Vitest + Testing Library + MSW · fetch or Axios with interceptors.

Layout: `app/(auth)/…` and `app/(public)/…` route groups; `components/{ui,forms,data-display,layout}`; `lib/{api,auth,validation,utils}`; `stores/`; `hooks/`; `types/`.

## State

- Server data only in TanStack Query; never mirrored in Zustand. Transactions `staleTime` 30 s, `placeholderData: keepPreviousData` for pagination.
- Transfer mutation: on success invalidate `['transactions']` and `['balance']`.
- Every fetch has a loading skeleton and an error boundary. Paginate lists (cursor or offset); never fetch all transactions.

## Forms

- Zod schema in `lib/validation`, shared with the form via `zodResolver`. Numeric inputs register with `valueAsNumber` (or `z.coerce.number()`).
- Transfer: account `^\d{10,16}$`; amount positive, max 50,000 single-transfer limit, decimal step derived from the currency's ISO 4217 exponent (not a fixed 0.01); currency `SGD | USD | MYR` (default SGD); reference ≤ 140 chars.
- Map API error codes to field errors (`INSUFFICIENT_FUNDS` → `amount`). Client validation is UX only; the server validates too.

## Money display

API amounts are integer minor units. Scale by the ISO 4217 exponent (`Intl.NumberFormat(...).resolvedOptions().maximumFractionDigits`: VND/KRW 0, SGD/USD 2, KWD/BHD 3), never a fixed 100. Cache `Intl.NumberFormat` per locale+currency. Default locale `en-SG`.

## PII

- Masked by default; reveal only on explicit user action (button with `aria-pressed`); log reveal events for audit.
- Masks: account `****5678` (all but last 4), email `us***@domain`, phone `+65****1234`, NRIC/FIN `****567A`.

## KYC

- Multi-step wizard (personal → identity → document → review); short-circuit when status is `APPROVED`.
- Documents upload directly to S3 via pre-signed URL from the backend, then confirm to the backend; no document bytes through our servers.
- Client-side: ≤ 10 MB, JPEG/PNG/PDF only (MIME check), no client OCR, `URL.revokeObjectURL` after upload.

## API client

- Base URL from env; unwrap the `{ data, meta }` envelope; errors as `ApiError(code, message, status)` from `{ error: { code, message } }`.
- 401 → refresh once and retry; a second 401 ends the session (redirect to login).

## Security rules

| Rule | |
|---|---|
| FE-SEC-01 | No tokens in localStorage: httpOnly cookies, or in-memory with refresh. |
| FE-SEC-02 | Sanitize user-generated HTML (DOMPurify) before rendering. |
| FE-SEC-03 | CSP configured: report-only first, then enforce. |
| FE-SEC-04 | No PII in URL parameters. |
| FE-SEC-05 | Idle auto-logout: 15 min on financial pages, 30 min otherwise. |
| FE-SEC-06 | Clear clipboard 60 s after copying sensitive data. |
| FE-SEC-07 | `autocomplete="off"` on sensitive financial fields. |
| FE-SEC-08 | No `console.log` of PII; strip console calls in production builds. |

All interactive elements keyboard-accessible.

## Tests

Form validation messages (e.g. limit exceeded), masking utilities, masked values in confirmation views, API error → form error via MSW handlers, currency formatting per exponent.
