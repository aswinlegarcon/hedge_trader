# Spec 16 — Implementation handoff

Status: IMPLEMENTED — offline acceptance complete (2026-11-14). Real renewal not exercised (needs an attended owner approval).
Baseline `main` @ `0adda3c34242523324d487eef44a73bdb3f2bd94`; delivered in the commit that adds this file (child of the
Part A commit that adds `docs/spec_15/operator-smoke-handoff.md`). Tested tree = that commit's tree.

## Flow implemented and why

**Official interactive authorization-code flow** (`/v2/login/authorization/dialog` → `/v2/login/authorization/token`).
The docs define no refresh grant, and key + secret cannot renew a token. The approval-based *Access Token Request* API was
evaluated and **deferred**: it delivers the token to a notifier webhook whose payload has no documented signature or
authenticity mechanism, and this project has no secured public HTTPS endpoint; exposing an unauthenticated token-install
endpoint was ruled out. TOTP login is out of scope (would require storing PIN/TOTP secrets).

## Changes

| Area | Change |
|------|--------|
| `nifty_lab/brokers/upstox_auth.py` (new) | `TokenStore` (0600 atomic file + fingerprint marks), `resolve_access_token`, `auth_status`, `note_response`, `expiry_after` (03:30 IST rule), `begin_login`/`complete_login`, `UpstoxAuthTransport` (token endpoint only), bounded pending-login registry |
| `nifty_lab/brokers/upstox_market_data.py` | `read_access_token`, `_token_present`, `connection_generation` delegate to the store (managed > environment; rejected never returned) |
| `nifty_lab/brokers/upstox_transport.py` | value-free rejection/verification marks on every response; 401/403 text guides to Reconnect |
| `nifty_lab/stream_chart/stream_session.py`, `stream_errors.py` | `stop_for_credential_change()`; `CREDENTIALS_REPLACED`; sanitizer passes through static auth guidance |
| `nifty_lab/ui/upstox_auth_ui.py` (new), `pages/10_Settings_and_API_Connections.py` | status, Reconnect controls (loopback-only), callback processing, query-param clearing |
| `tests/conftest.py` | every test gets an isolated empty token store (`NSL_TOKEN_STORE`) |
| `.env.example`, `docs/spec_16/*` | configuration and operator guide |

## Scenario → test → result (`tests/test_spec16_auth_lifecycle.py`, 21 passed)

| Scenario | Test | Result |
|----------|------|--------|
| S01 | `test_s01_store_writes_atomically_with_restrictive_permissions` | pass |
| S02 | `test_s02_failed_replacement_keeps_working_credential` | pass |
| S03 | `test_s03_expiry_follows_documented_0330_ist_rule` | pass |
| S04 | `test_s04_precedence_managed_over_env_and_rejected_env_never_overrides` | pass |
| S05 | `test_s05_expired_managed_token_requires_reauth_and_is_not_used` | pass |
| S06 | `test_s06_status_labels_are_value_free_and_truthful` | pass |
| S07 | `test_s07_transport_marks_rejection_and_success_by_fingerprint` | pass |
| S08 | `test_s08_rejected_credential_stops_stream_retries_and_next_start_makes_no_http` | pass |
| S09 | `test_s09_begin_login_builds_exact_dialog_url_with_random_single_use_state`, `test_s09_begin_login_requires_configuration` | pass |
| S10 | `test_s10_callback_validation_rejects_bad_states_without_exchange` ×5 (missing state, unknown, missing code, expired, replayed) | pass |
| S11 | `test_s11_valid_callback_exchanges_server_side_installs_token_and_stops_active_stream` (DEBUG logs captured: no code/token/secret) | pass |
| S12 | `test_s12_exchange_failure_keeps_existing_credential_and_is_sanitized` | pass |
| S13 | `test_s13_auth_transport_only_talks_to_the_token_endpoint` | pass |
| S14 | `test_s14_pending_logins_are_bounded_and_expire` | pass |
| S15 | `test_s15_settings_page_shows_status_and_processes_callback_without_exposing_values` (AppTest) | pass |
| S16 | `test_s16_reconnect_controls_hidden_off_loopback` (AppTest) | pass |

Regression intact: Spec 15 reliability 36 passed (incl. 2 new bootstrap tests), loopback 6, Spec 14 readiness 14, Spec 14 unit 14, Spec 04 Upstox module passed, browser acceptance 3 passed in the final suite.

Final full suite: `395 passed, 1 skipped in 39.36s` (`TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest --tb=short -ra tests`, `NSL_FORBID_LIVE_MUTATIONS=1`). The skip is pre-existing and unrelated (`tests/test_spec10_paper_account.py:161: no local paper db`). Previous baseline 372 passed; +2 bootstrap regressions, +21 Spec 16.

## Token storage and precedence (as implemented)

`data/secrets/upstox_token.json` (gitignored via `secrets/`), 0600 file / 0700 dir, temp-file + `os.replace`; a failed write
leaves the old file untouched (S02). Marks file holds sha256 fingerprints only. Precedence managed → environment → none;
rejected fingerprints are never resolved again, so a revoked environment token cannot override a newly installed token and
cannot cause a retry storm (S04, S07, S08). No token is written to SQLite, research artifacts, browser storage or stream
snapshots. Nothing replicates the store between machines.

## Owner configuration still needed (non-secret)

- The Upstox app's registered **redirect URI** and `UPSTOX_REDIRECT_URI` in `.env` must both be exactly
  `http://localhost:8501/Settings_and_API_Connections` (the Settings page receives the callback). The currently configured
  `UPSTOX_REDIRECT_URI` points at loopback port 8501 but **not** at a dashboard page, so the first Reconnect will fail with the
  redirect-URI error until both are aligned. This was not changed automatically.
- For approval from another computer: `ssh -N -L 8501:127.0.0.1:8501 <linux-host>`, then use `http://localhost:8501`.

## Limitations

- Session binding is process-local: the callback arrives in a new Streamlit session (new tab), so the initiating session id is recorded (`cross_session`) but the browser identity cannot be bound (no server-settable cookie in Streamlit). Mitigations: random single-use state, 10-minute TTL, exact redirect URI, loopback-only controls.
- Pending logins live in process memory; a Streamlit restart between "Reconnect" and the callback requires starting again.
- Real exchange with Upstox was not performed (mocked `requests.Session`); the first real reconnect is an attended owner action.
- `extended_token` from the token response is not stored or used.
- Streamlit shows its own relative-path 404 probes in the browser console on multipage URLs; harmless, not ours.

## Verdicts

- LIVE smoke (Part A): **CONNECTIVITY_ONLY** — see `docs/spec_15/operator-smoke-handoff.md`. Not a fresh-price, rollover or live-trading claim.
- Spec 16: implemented and offline-accepted; **not** live-trading readiness.
