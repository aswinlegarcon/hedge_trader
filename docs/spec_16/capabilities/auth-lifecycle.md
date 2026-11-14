# Capability: Upstox authentication lifecycle

MUST = acceptance requirement. Each scenario names its automated test in `tests/test_spec16_auth_lifecycle.py`.

## R1 — Managed token store
- S01 Install MUST write atomically (temp + rename) with file mode 0600 and directory 0700, leaving no temp files; reprs MUST hide values.
- S02 A failed replacement MUST leave the existing credential intact.
- S03 Expiry MUST follow the documented rule: 03:30 IST the following day (an issue time before 03:30 expires that same day).

## R2 — Precedence, rejection, status
- S04 Managed token MUST take precedence over the environment token; a rejected environment token MUST never be used again, even when the managed token is removed.
- S05 An expired managed token MUST not be used and MUST show "rejected / reauthorization required".
- S06 Status labels MUST be value-free: not configured / not verified / connected / rejected-reauth; expiry MUST be shown only with issuance metadata (environment tokens: "unknown").
- S07 The production HTTP transport MUST mark 401/403 as rejection and 2xx as verification by fingerprint, so a rejected token cannot be resolved again (no retry storm).
- S08 A LIVE stream MUST fail once on a rejected credential, and a subsequent Start MUST make zero HTTP calls while guiding to Reconnect.

## R3 — OAuth reconnect
- S09 `begin_login` MUST build the exact dialog URL (`client_id`, `redirect_uri`, `response_type=code`, `state`), with ≥ 32-byte random, unique state, and MUST refuse when configuration is missing (naming the missing variable only).
- S10 Callbacks with missing/unknown/expired/replayed state or a missing code MUST be rejected before any exchange.
- S11 A valid callback MUST exchange server-side with the exact documented form fields, install the token atomically, stop any active stream with `CREDENTIALS_REPLACED`, require an explicit Start, and leak no code/token/secret into DEBUG logs; existing clients MUST use the replacement on their next call.
- S12 Exchange failures (HTTP error codes, malformed success) MUST keep the existing credential and MUST not echo broker bodies.
- S13 The auth transport MUST post only to `https://api.upstox.com/v2/login/authorization/token`.
- S14 Pending logins MUST be bounded and expire.

## R4 — Settings page
- S15 The Settings page MUST show the value-free status, process the callback from query parameters, clear `code`/`state` from the URL, show success, switch to the managed source, and reject a replayed callback.
- S16 Reconnect controls MUST be hidden when the page is not reached via loopback (direct or SSH tunnel).

## MODIFIED
Spec 04's "set `UPSTOX_ACCESS_TOKEN` in .env and restart" remains a supported initial path with lower precedence than the managed store.
