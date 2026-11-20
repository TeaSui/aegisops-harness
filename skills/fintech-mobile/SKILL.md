---
name: fintech-mobile
description: |
  Fintech mobile-app patterns for Flutter (primary), native iOS and Android apps.
  Biometric authentication flows, secure transaction handling, push notifications
  for financial alerts, KYC document capture, offline-first for financial data.
  Use when: implementing mobile banking features, biometric auth, transaction
  flows, push notifications for financial events, KYC document upload, or
  secure data display on mobile.
  Triggers on: Flutter, iOS/Android app, biometric login, in-app payment, app transaction screen,
  push notification, KYC capture in the app, mobile banking app, app secure storage, PIN entry.
  Not for phone/mobile-number fields in web or backend code.
---

# Fintech Mobile Patterns

Flutter/Dart primary; Swift/Kotlin only for native modules (platform channels). Read `pubspec.lock` before using any plugin API; do not upgrade a dependency just to match these notes.

## Biometric auth

- `local_auth` 3.x: `authenticate(localizedReason:, biometricOnly:, persistAcrossBackgrounding:)`, errors via `LocalAuthException`/`LocalAuthExceptionCode` (non-exhaustive — handle `default`). Pinned 2.x projects keep `AuthenticationOptions`/`stickyAuth`/`PlatformException` until a planned migration.
- Map cancel → cancelled; lockout, no hardware, not enrolled, no credentials, user fallback → password fallback.
- Serialize concurrent prompts. A passed OS prompt is not server authorization and does not bind a key read or signature to hardware auth — for biometric-gated keys use a facility that enforces authenticated key access (Keychain access control / Keystore `setUserAuthenticationRequired`).
- Biometric-only policy: check `getAvailableBiometrics()`, set `biometricOnly: true`; never silently weaken a payment authorization policy.

| Rule | |
|---|---|
| BIO-01 | Never store biometric data; delegate to OS (LocalAuthentication / BiometricPrompt). |
| BIO-02 | Biometric unlocks a stored credential (refresh token), then refresh the session server-side; never unlocks the account directly. |
| BIO-03 | Use the approved fallback policy; device credential/password needs proper re-auth. Never bypass a biometric-only transaction requirement with an unverified app PIN. |
| BIO-04 | Respect OS lockout and server re-auth policy; assume no portable attempt count or lockout duration. |
| BIO-05 | Re-enrol the biometric binding when device biometrics change. |
| BIO-06 | Fresh biometric for payments above the threshold amount (transaction signing). |

## Secure storage

- Tokens in `flutter_secure_storage` (verify installed API). iOS Keychain `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` (`KeychainAccessibility.passcode`); Android `encryptedSharedPreferences` is a legacy option and does not give StrongBox or biometric-bound keys. `clearAll` on logout.

## Secure display

- Sensitive screens: Android `FLAG_SECURE` via a project-owned MethodChannel (enable on mount, clear on dispose) or a maintained package — not `flutter_windowmanager` (unmaintained since 2021). iOS: overlay content on `AppLifecycleState.inactive`.
- Account numbers masked (`****5678`), reveal on explicit action.
- Every async screen has loading (skeleton), error and loaded states (sealed-state switch with Bloc).

## Money

- Amounts are `int` minor units; never `double`. Format with `NumberFormat.simpleCurrency` using the ISO 4217 exponent (VND/KRW/JPY 0; SGD/USD/MYR/PHP/EUR 2; KWD/BHD/OMR/JOD 3); an unknown currency throws, never defaults to 2.

## Push notifications

- Categories → Android channels: transaction (high importance), security (max, heads-up), kyc (default), marketing (low, opt-in).
- iOS: no `criticalAlert` (Critical Alerts entitlement is reserved for health/safety); send security and transaction alerts with APNs `interruption-level: time-sensitive`.
- Register the FCM token on start and on `onTokenRefresh`. Foreground transaction message → in-app banner + refresh transactions; security → system notification.

| Rule | |
|---|---|
| PUSH-01 | No full account numbers or amounts in the payload. |
| PUSH-02 | Data-only messages; build display text client-side. |
| PUSH-03 | Security alerts (new-device login): Android high-importance channel, iOS Time Sensitive (not Critical). |
| PUSH-04 | Marketing notifications can be disabled independently. |
| PUSH-05 | Invalidate cached financial data on a transaction notification. |
| PUSH-06 | Test delivery in foreground and background states. |

## KYC capture

- Capture limits: max 2048×2048, quality 85, reject > 10 MB, validate it decodes as an image. Types: national ID (camera, 2 sides), passport (camera, 1), proof of address (camera or gallery, 1), selfie (camera, 1).

| Rule | |
|---|---|
| KYC-MOB-01 | National ID and passport: camera only. |
| KYC-MOB-02 | Selfie: liveness detection recommended (blink/head-turn). |
| KYC-MOB-03 | Upload via pre-signed S3 URL, never through the app server. |
| KYC-MOB-04 | Delete local document files immediately after successful upload. |
| KYC-MOB-05 | Show upload progress; retry on failure (resume if possible). |
| KYC-MOB-06 | Preview before submit; allow retake. |

## Offline-first

Repository serves the local stream first and syncs in the background (`since: lastSync`); sync failure is non-fatal.

| Rule | |
|---|---|
| OFFLINE-01 | Show cached data immediately, sync in background. |
| OFFLINE-02 | Show "Last updated X minutes ago" when offline. |
| OFFLINE-03 | Read-only offline: disable transfer/payment actions. |
| OFFLINE-04 | Queue non-financial actions (profile updates) offline; sync on reconnect. |
| OFFLINE-05 | Never queue financial transactions offline. |
| OFFLINE-06 | Encrypted local DB with key in Keychain/Keystore: drift 2.32+ with SQLite3MultipleCiphers (`sqlite3` hook `source: sqlite3mc`) or `sqflite_sqlcipher`. Not `sqlcipher_flutter_libs` (EOL) or Isar 3 (no encryption). |

## App hardening

- Root/jailbreak or emulator detected: allow, warn and log a security event (blocking breaks dev testing) unless the project policy says block.
- Certificate pinning on the HTTP client (pins from config).
- Re-authenticate (biometric) after > 5 min in background.

## Tests

Biometric fallback chain (mock `LocalAuthentication`), offline display with stale indicator (mock connectivity), KYC capture validation, minor-unit formatting per exponent.
