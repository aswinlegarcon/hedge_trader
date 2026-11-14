# Spec 06 implementation handoff

Status: **IMPLEMENTED** (read-only Upstox watchlist company news). No git commits. Funded-paper qualification remains **blocked**.

## Implementation

| Area | Path (final line anchor) |
|------|---------------------------|
| News client (`GET /v2/news`, category `instrument_keys` only) | `nifty_lab/news/upstox_news.py` (146) |
| Normalization, snapshot, dedupe, URL/timestamp rules | `nifty_lab/news/snapshot.py` (226) |
| Watchlist key resolution (bundle or public master) | `nifty_lab/news/watchlist_keys.py` (47) |
| Streamlit session + panels (pages 02/11) | `nifty_lab/ui/watchlist_news.py` (131) |
| Global News page integration | `pages/02_Global_News_and_Events.py` |
| Watchlist detail news card | `pages/11_Watchlist_Research.py` |
| Mocked tests | `tests/test_spec06_news.py` (13 cases) |
| Optional live smoke | `scripts/upstox_news_smoke.py` |

**Preserved:** Spec 03–05 modules, `production_context_blocked` / tri-state funded-paper gate, manual event calendar on page 02, no orders/holdings/positions news categories, no scraping or article-host fetches.

**Workflow:** User clicks **Refresh news** on page 02 or **Refresh news for watchlist** on page 11 → one bounded news HTTP call (≤4 keys, URL-encoded) → shared `st.session_state.watchlist_news_snapshot`. Optional **Load next page** = second call, max two pages merged with dedupe. Failed refresh clears active snapshot and may show prior content only as cached reference with old timestamp.

## Scenario evidence

| Requirement | Evidence |
|-------------|----------|
| Category fixed `instrument_keys`; no holdings/positions | `test_category_fixed_instrument_keys_only`, `FORBIDDEN_NEWS_CATEGORIES` constant |
| One news HTTP call per explicit refresh | `test_one_request_per_refresh`, `UpstoxNewsClient._calls` |
| ≤4 keys, bearer via existing transport | Client `_news_url` + `build_auth_header` / `read_access_token` (not exercised with real token in tests) |
| Empty provider list → `NO RECENT ARTICLES` | `test_empty_news_list_per_key_no_recent` |
| Empty `data` → `COVERAGE UNKNOWN` | `test_empty_data_coverage_unknown` |
| ms→UTC sort, 7d window, dedupe | `test_ms_timestamp_and_sort`, `test_old_article_excluded_count`, `test_dedupe_same_url_time` |
| Unsafe URL quarantined | `test_unsafe_url_quarantined` |
| Auth failure → failed snapshot, no fake success | `test_auth_failure_marks_no_success_snapshot` |
| Stale snapshot >15m | `test_stale_snapshot_flag` |
| Fake-secret sentinel in JSON payload | `test_fake_secret_in_payload` |
| 15m stale label / failure not re-labelled fresh | `render_news_panel` + `SESSION_CACHED_REFERENCE` in `watchlist_news.py` (UI; manual verify) |
| Selection invalidation on watchlist key change | `invalidate_news_if_keys_changed` called from page 11 watchlist refresh |
| Network blocked in automated suite | `block_net` autouse in `test_spec06_news.py` (same pattern as Spec 05) |

## Verification

- **Python:** 3.12.15 (project `.venv`)
- **Command:** `.venv/bin/pytest -q tests`
- **Result:** **94 passed**, 0 failed (81 prior + 13 Spec 06)
- **Secrets in tests:** `UPSTOX_ACCESS_TOKEN=fake-token-for-tests`; socket connect blocked; no `.env` read in pytest
- **Sentinel:** `FAKE_SECRET_SENTINEL` rejected in normalized payloads; failure messages checked (`test_refresh_failure_message_sanitized`)

## Live result

**Ran:** `scripts/upstox_news_smoke.py` (token read from local `.env` by script only; not inspected or logged by agent).

```
OK outcome=VALID_EMPTY symbol=ICICIBANK articles=0 newest_utc=none retrieved_utc=2026-11-13T04:38:42Z per_key=OK page=1 has_more=False
```

Interpretation: **Endpoint reachable** (HTTP 200, success payload); **no displayable articles** for the first resolved watchlist/master key after validation (valid-empty / filtered-empty — not invented headlines). One master resolution + one news call within smoke script bounds.

## Remaining limitations

- Macro/RBI/FOMC/earnings schedules remain **NOT CHECKED**; manual calendar only.
- News is provider-reported headings/excerpts only — not verified truth, sentiment, or trade eligibility.
- Seven-day recency is a client heuristic; provider may return fewer items; pagination capped at two pages (50 raw rows before dedupe).
- News success does **not** certify candle connectivity (`ACCESS_STATE` / candle paths unchanged except auth failure propagation on 401/403).
- Spec 03 financial-gate edge cases, session-calendar labels, and broad UI scenario matrices remain deferred.
- Spec 05 handoff “9 calls per instrument” was **not** re-measured in this slice (watchlist transport unchanged).

**Smallest next task (optional):** Capture one non-empty live headline sample in handoff after market hours with a symbol known to have recent `news_list` entries, still sanitized.
