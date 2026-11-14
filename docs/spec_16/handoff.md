# Spec 16 — Implementation handoff

Status: IMPLEMENTED — offline acceptance complete (2026-11-14), review corrections applied the same day. Real renewal not
exercised (needs an attended owner approval). Delivered in `dbe41ad` (initial) and the correction commit that last touched
this file (`git log -1 --format=%H -- docs/spec_16/handoff.md`); tested tree = that commit's tree.

## Flow implemented and why

**Official interactive authorization-code flow** (`/v2/login/authorization/dialog` → `/v2/login/authorization/token`).
The docs define no refresh grant, and key + secret cannot renew a token. The approval-based *Access Token Request* API was
evaluated and **deferred**: it delivers the token to a notifier webhook whose payload has no documented signature or
authenticity mechanism, and this project has no secured public HTTPS endpoint; exposing an unauthenticated token-install
endpoint was ruled out. TOTP login is out of scope (would require storing PIN/TOTP secrets).

## Review corrections (second pass) — finding → fix → test

| # | Finding (baseline `dbe41ad`) | Fix | Tests |
|---|------------------------------|-----|-------|
| 1 | `_handle_callback()` ran before any access check, and the check trusted the client `Host` header. | OAuth initiation **and** callback processing are gated by `oauth_access_allowed()`, which reads the listener address from server configuration (`server.address`), fail-closed when unset or non-loopback. Refused callbacks still clear `code`/`state` from the URL and perform zero exchanges, writes or stream changes. `.streamlit/config.toml` now binds `address = "127.0.0.1"`. Documented as a network boundary + OS/SSH identity, not UI authentication. | S16 `test_s16_oauth_processing_refused_unless_listener_is_loopback` (addresses `None`, `""`, `0.0.0.0`, LAN IP; asserts no exchange, no store write, stream untouched, no controls; header-independent) |
| 2 | `complete_login()` accepted any session and merely reported `cross_session=True`. | Two-step flow: `receive_callback()` (any session) only holds the code on the pending record; `complete_login(state, session_key)` exchanges solely in the initiating session (key = session id + per-session random nonce). Wrong session refused without consuming the pending login; replayed callback refused; code removed from memory before the exchange. UI: initiating tab shows **Complete reconnection**; callback tab shows "return to the original tab". | S19 `test_s19_completion_requires_the_initiating_session_and_a_received_callback`, S10 (+`replayed_callback`, `replayed_completion`), S11, S15 `test_s15_settings_flow_completes_only_in_the_initiating_session` |
| 3 | A known-expired managed token could reappear through an identical environment token. | `resolve_access_token` records a durable `expired` mark when the managed token passes its documented expiry and consults `is_unusable(fp)` (rejected **or** expired) for every source. A genuinely different environment credential remains a documented fallback: expiry unknown, "not verified" until a 2xx. | S05 (extended) `test_s05_expired_managed_token_requires_reauth_and_is_not_used` |
| 4 | `mark_verified()` cleared rejection; `default_store()` created a fresh lock per instance for the same files. | Marks are one-directional (`setdefault`; success never clears rejected/expired). One shared in-process `RLock` per store path plus an advisory `fcntl.flock` on a sibling `.lock` file around every read-modify-write (threads and processes on one host). | S17 `test_s17_late_success_cannot_resurrect_a_rejected_credential`, S18 `test_s18_shared_state_updates_are_not_lost_under_concurrent_writers` (40 concurrent writers with separate instances, zero lost marks) |

Also verified in the same run: failed replacement preserves the previous credential (S02, S12); secrets absent from UI text, exception messages, DEBUG logs and store reprs (S11, S12, S15, S16 assertions with marker strings).

## Changes

| Area | Change |
|------|--------|
| `nifty_lab/brokers/upstox_auth.py` (new) | `TokenStore` (0600 atomic file + fingerprint marks), `resolve_access_token`, `auth_status`, `note_response`, `expiry_after` (03:30 IST rule), `begin_login`/`complete_login`, `UpstoxAuthTransport` (token endpoint only), bounded pending-login registry |
| `nifty_lab/brokers/upstox_market_data.py` | `read_access_token`, `_token_present`, `connection_generation` delegate to the store (managed > environment; rejected never returned) |
| `nifty_lab/brokers/upstox_transport.py` | value-free rejection/verification marks on every response; 401/403 text guides to Reconnect |
| `nifty_lab/stream_chart/stream_session.py`, `stream_errors.py` | `stop_for_credential_change()`; `CREDENTIALS_REPLACED`; sanitizer passes through static auth guidance |
| `nifty_lab/ui/upstox_auth_ui.py` (new), `pages/10_Settings_and_API_Connections.py`, `.streamlit/config.toml` | status; listener-gated OAuth; receive-then-complete flow; query-param clearing; loopback listener binding |
| `tests/conftest.py` | every test gets an isolated empty token store (`NSL_TOKEN_STORE`) |
| `.env.example`, `docs/spec_16/*` | configuration and operator guide |

## Scenario → test → result (`tests/test_spec16_auth_lifecycle.py`, 25 passed)

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
| S10 | `test_s10_callback_validation_rejects_bad_states_without_exchange` ×6 (missing state, unknown, missing code, expired, replayed callback, replayed completion) | pass |
| S11 | `test_s11_valid_completion_exchanges_server_side_installs_token_and_stops_active_stream` (DEBUG logs captured: no code/token/secret) | pass |
| S12 | `test_s12_exchange_failure_keeps_existing_credential_and_is_sanitized` | pass |
| S13 | `test_s13_auth_transport_only_talks_to_the_token_endpoint` | pass |
| S14 | `test_s14_pending_logins_are_bounded_and_expire` | pass |
| S15 | `test_s15_settings_flow_completes_only_in_the_initiating_session` (AppTest: initiate in tab 1, callback in tab 2 records only, replay rejected, tab 1 completes) | pass |
| S16 | `test_s16_oauth_processing_refused_unless_listener_is_loopback` (AppTest) | pass |
| S17 | `test_s17_late_success_cannot_resurrect_a_rejected_credential` | pass |
| S18 | `test_s18_shared_state_updates_are_not_lost_under_concurrent_writers` | pass |
| S19 | `test_s19_completion_requires_the_initiating_session_and_a_received_callback` | pass |

Regression intact: Spec 15 reliability 36 passed (incl. 2 new bootstrap tests), loopback 6, Spec 14 readiness 14, Spec 14 unit 14, Spec 04 Upstox module passed, browser acceptance 3 passed in the final suite.

Final full suite: `399 passed, 1 skipped in 40.02s` (`TMPDIR=/tmp/pytest_hedge .venv/bin/python3.12 -m pytest --tb=short -ra tests`, `NSL_FORBID_LIVE_MUTATIONS=1`). The skip is pre-existing and unrelated (`tests/test_spec10_paper_account.py:161: no local paper db`). Previous 395; +4 from the review corrections (S17, S18, S19, extra S10 case).

## Token storage and precedence (as implemented)

`data/secrets/upstox_token.json` (gitignored via `secrets/`), 0600 file / 0700 dir, temp-file + `os.replace`; a failed write
leaves the old file untouched (S02). Marks file holds sha256 fingerprints only. Precedence managed → environment → none;
rejected fingerprints are never resolved again, so a revoked environment token cannot override a newly installed token and
cannot cause a retry storm (S04, S07, S08). No token is written to SQLite, research artifacts, browser storage or stream
snapshots. Nothing replicates the store between machines.

## Owner configuration still needed (non-secret)

- **Changed in this pass:** the dashboard now listens on `127.0.0.1` only (`.streamlit/config.toml`). Remote access requires `ssh -N -L 8501:127.0.0.1:8501 <linux-host>`; any LAN-address bookmark stops working by design.

- The Upstox app's registered **redirect URI** and `UPSTOX_REDIRECT_URI` in `.env` must both be exactly
  `http://localhost:8501/Settings_and_API_Connections` (the Settings page receives the callback). The currently configured
  `UPSTOX_REDIRECT_URI` points at loopback port 8501 but **not** at a dashboard page, so the first Reconnect will fail with the
  redirect-URI error until both are aligned. This was not changed automatically.
- For approval from another computer: `ssh -N -L 8501:127.0.0.1:8501 <linux-host>`, then use `http://localhost:8501`.

## Limitations

- Binding is enforced by explicit completion in the initiating session (two-step flow); the callback tab can only record the approval. The authorization code is held in process memory for at most 10 minutes between receipt and completion (single-use; removed before the exchange). The access boundary is the loopback-bound listener plus the host's SSH/OS account; the UI itself does not authenticate users, and a reverse proxy in front of the dashboard would defeat the listener assumption (unsupported).
- Pending logins live in process memory; a Streamlit restart between "Reconnect" and the callback requires starting again.
- Real exchange with Upstox was not performed (mocked `requests.Session`); the first real reconnect is an attended owner action.
- `extended_token` from the token response is not stored or used.
- Streamlit shows its own relative-path 404 probes in the browser console on multipage URLs; harmless, not ours.

## Verdicts

- LIVE smoke (Part A): **CONNECTIVITY_ONLY** — see `docs/spec_15/operator-smoke-handoff.md`. Not a fresh-price, rollover or live-trading claim.
- Spec 16: implemented and offline-accepted; **not** live-trading readiness.
