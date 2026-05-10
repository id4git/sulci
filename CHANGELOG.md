# Changelog

All notable changes to Sulci are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.5.7] — 2026-05-10 — Fix cloud backend URL paths (sulci-oss P0)

Three-string fix to `sulci/backends/cloud.py` aligning the SDK's request
URLs with the gateway's canonical paths. Pre-0.5.7, the cloud backend
POSTed to `/v1/get` and `/v1/set`; the gateway has always exposed
`/v1/cache/get` and `/v1/cache/set`. Every request returned 404, the
SDK's outer `except Exception:` clause swallowed it, and `cache.get()`
returned `(None, 0.0)` — a silent dataplane failure across the entire
managed-cloud tier. Users saw "sulci doesn't seem to be caching anything"
with nothing in their logs to investigate.

### Fixed

- **`SulciCloudBackend.search()`** (`cloud.py:101`) now POSTs to
  `/v1/cache/get` rather than `/v1/get`.

- **`SulciCloudBackend.store()`** (`cloud.py:150`) now POSTs to
  `/v1/cache/set` rather than `/v1/set`.

- **`SulciCloudBackend.upsert()`** (`cloud.py:179`) now POSTs to
  `/v1/cache/set` rather than `/v1/set`. The delete path at `cloud.py:201`
  already used `/v1/cache` and was unaffected.

### Added

- **`TestCanonicalGatewayPaths`** in `tests/test_cloud_backend.py`. Four
  assertions pinning each URL-bearing method (`search`, `store`, `upsert`)
  to the gateway's canonical path, plus a static-source check that catches
  the regression case where a new method is added but the URL prefix is
  forgotten. The class header documents the gateway-side source of truth
  (`gateway/app/main.py` for the prefix, `gateway/app/routes/cache.py` for
  the route decorators) so the contract is auditable from the test file.

### Changed

- **`TestSearch.test_sends_correct_payload`** previously asserted
  `call_args[0][0] == "/v1/get"`, tautologically locking in the bug. Now
  asserts `"/v1/cache/get"`. The stale docstring on
  `TestUpsert.test_sends_correct_payload` was also corrected.

### Why this slipped past CI

The pre-0.5.7 unit test asserted the SDK was POSTing to `/v1/get` and was
passing because the SDK was, in fact, POSTing to `/v1/get`. The test
verified the wrong contract — what the SDK *did*, rather than what the
gateway *expected*. The new `TestCanonicalGatewayPaths` class encodes the
gateway-side contract as a comment block and asserts against it directly,
so a future drift on either side is caught at the test boundary rather
than via production telemetry.

### Compatibility

Strictly a bugfix. No public API changes, no payload shape changes, no
new dependencies. Any caller that was getting silent `(None, 0.0)` cache
misses against the live gateway will now actually hit the cache.

---

## [0.5.6] — 2026-05-08 — `plan` field on `CacheEvent` (sulci-oss #36)

Additive field on the v0.5.0 `CacheEvent` dataclass plus a matching
keyword argument on `Cache.get` / `Cache.set` / `Cache.cached_call`,
so callers who know a tenant's plan tier at emit time can attribute
it onto the event without monkey-patching the dataclass or doing a
join at consume time. Backward-compatible per ADR 0005's
"additive kwarg with default" rule — pre-0.5.6 callers see no
behavior change; emitted events default to `plan=None`.

### Added

- **`CacheEvent.plan: Optional[str] = None`** (#36). New field on the
  privacy-firewalled event surface, sitting alongside `tenant_id`.
  Carries the customer plan tier (`'free' | 'pro' | 'business' |
  'enterprise' | 'oss_connect'`) when the caller knows it. Defaults
  to `None` so users of the OSS library who don't have plan context
  don't have to thread anything through.

- **`plan: Optional[str] = None`** added as a keyword-only argument
  to `Cache.get`, `Cache.set`, and `Cache.cached_call`. When supplied,
  it is forwarded onto the emitted `CacheEvent.plan`. `cached_call`
  threads it through both its internal `.get()` and `.set()` calls so
  the miss-then-set path emits two events that both carry plan.

- **`"plan"` added to `_ALLOWED_FIELDS`** in `sulci/sinks/telemetry.py`
  so it survives the privacy firewall and reaches `TelemetrySink` /
  `RedisStreamSink` consumers. The allowlist's docstring now
  articulates the three-criteria rule for future additions: a candidate
  field must be (a) low-cardinality, (b) already known to the
  recipient via auth context, and (c) explicitly billing- or
  routing-relevant. `plan` satisfies all three.

### Why

The sulci-platform billing pipeline reads cache events from a Redis
stream and routes them by tenant + plan. Pre-0.5.6, `CacheEvent` had
no plan field, so the gateway emitted events with `plan` recoverable
only by joining each event back to Postgres at consume time. That
join was painful enough that two real-world E2E tests in the platform
(`test_09_billing_events_have_correct_tenant_and_plan` and
`test_j09_billing_events_carry_pro_plan`) had been failing for weeks
with `[None, None, None, None, None]`, eating a per-PR bypass-note
tax on every backend-touching change. Carrying plan on the event
closes that gap and lets the gate run clean.

### Tests

- `tests/test_core.py::TestCacheEventPlan` (6 tests). Recording-sink
  fixture verifies `plan` flows from `Cache.get` / `.set` / `.cached_call`
  onto the emitted `CacheEvent`, that the default-`None` path is
  unchanged for pre-0.5.6 callers, and that `plan` is keyword-only
  with default `None` on all three methods (pinning the API shape
  the same way `tenant_id` / `user_id` / `session_id` are pinned).

- `tests/test_sinks.py` — `TestAllowlist::test_allowlist_contents_are_stable`
  extended to include `"plan"`. Two new scrubbing tests verify
  `plan="pro"` and `plan=None` both round-trip through `_scrub`. The
  canonical `sample_event` fixture now sets `plan="pro"` so all
  existing scrub-loop tests cover the new field implicitly.

### Privacy review note

Adding any field to `_ALLOWED_FIELDS` is a privacy-relevant change.
`plan` was reviewed against the rule the docstring now documents:

| Criterion                                     | `plan` satisfies? |
| --------------------------------------------- | ----------------- |
| Low-cardinality (closed enum, ~5 values)      | yes               |
| Already known to recipient via auth context   | yes               |
| Explicitly billing- or routing-relevant       | yes               |

Adding `plan` doesn't expose anything the receiving service didn't
already know; it removes a join. The cardinality is bounded; there
is no PII or free-form content carried.

### Compatibility

- Existing callers (no `plan` kwarg): emit `plan=None`, identical to
  pre-0.5.6 behavior on the wire.
- Older sinks that don't know about the new field: `_scrub` is built
  on `dataclasses.asdict`, so missing the field on an old struct is
  impossible — the field exists on every `CacheEvent` instance from
  this version forward.
- Custom `EventSink` implementations: receive `event.plan` like any
  other field; no breaking change to the sink API.

---

## [0.5.5] — 2026-05-07 — telemetry honors `SULCI_GATEWAY` (PR-D)

One-line behavior fix that unblocks staging-gateway smoke tests for the
sulci-platform Connected-OSS dashboard tier (LAUNCH-PLAN row C2e). No
new public API surface; no changes for users running against the
default `https://api.sulci.io` gateway.

### Fixed

- **`SULCI_GATEWAY` now actually redirects telemetry POSTs** (#51).
  `_TELEMETRY_URL` is now derived from `_GATEWAY_BASE` instead of being
  a separate hardcoded literal. Prior to v0.5.5, setting
  `SULCI_GATEWAY=https://staging.example.com` redirected the v0.6.0
  device-code flow but silently did NOT redirect the v0.5.x telemetry
  pipeline — the `_post()` helper still went to `api.sulci.io`. The
  module comment claimed staging override was supported; the code
  contradicted it. Now they agree:

  ```python
  # before (v0.5.4)
  _TELEMETRY_URL = "https://api.sulci.io/v1/telemetry"   # hardcoded
  _GATEWAY_BASE  = os.environ.get("SULCI_GATEWAY", "https://api.sulci.io").rstrip("/")

  # after (v0.5.5)
  _GATEWAY_BASE  = os.environ.get("SULCI_GATEWAY", "https://api.sulci.io").rstrip("/")
  _TELEMETRY_URL = f"{_GATEWAY_BASE}/v1/telemetry"
  ```

  Backward-compatible: callers who don't set `SULCI_GATEWAY` see no
  change (still resolves to `https://api.sulci.io/v1/telemetry`).

### Tests

- New `tests/test_telemetry_gateway_override.py` (6 tests) covering
  default URL, env override, trailing-slash normalization, localhost
  for local-dev, and end-to-end verification that `_post()` actually
  POSTs to the resolved URL — closing the gap that let v0.5.4 ship
  with a comment that disagreed with the code.

### Out of scope (filed as follow-up)

- `sulci/backends/cloud.py` (the `Cache(backend="sulci")` HTTP backend)
  still hardcodes `CLOUD_URL = "https://api.sulci.io"` and only honors
  a programmatic `gateway_url=` kwarg, not `SULCI_GATEWAY`. This is a
  separate issue and a separate ergonomic gap; tracked as #TBD-2 for a
  future minor.

---

## [0.5.4] — 2026-05-04 — D7 enabler bundle (PR-C)

Five paper-cut fixes that land alongside the platform's D7 dashboard
`/oss-connect` page work. Each one removes friction a freshly OSS-Connect-
funneled user would otherwise hit in the first five minutes — startup
visibility, raw-API stats, examples idempotency, key-rejection clarity,
and PyPI-page metadata. No new public API surface; one observable
behavior change called out under **Changed**.

### Added

- **POST `event='startup'` from `_flush()`** (#41). When `sulci.connect()`
  is called the resulting startup event now reaches `/v1/telemetry`
  instead of being drained on the floor. One POST per flush cycle that
  contains any startup event (multiple buffered startups collapse to a
  single dashboard row — startup is a state, not a counter). Backend
  is sniffed from any non-startup event in the same batch; if the
  startup ships before any cache traffic it goes out with `backend=""`,
  which the gateway accepts and the fingerprint dedupes against later
  rows. Result: a fresh deployment appears on the dashboard before its
  first cache.get / cache.set, which is what D7's ConnectedOssOverview
  needs to render.

- **`pyproject.toml` — `authors` block + `Changelog` URL** (#25).
  `pip show sulci` and the PyPI sidebar now surface
  `Author: Kathiravan Sengodan` and a direct link to `CHANGELOG.md`.
  The other `[project.urls]` entries that were already in place
  (Homepage / Repository / Documentation / Bug Tracker) are unchanged.

### Changed

- **`Cache._stats["hits"]/["misses"]` increment inside `Cache.get()`,
  not inside `Cache.cached_call()`** (#42). Users who use the raw
  `.get()` / `.set()` API previously saw `stats() == {"hits": 0,
  "misses": 0, "total_queries": 0}` regardless of activity, because
  the counters only fired through `cached_call()`. They now reflect
  every `.get()` call. `cached_call()` no longer increments them
  itself — it goes through `.get()` like everyone else, so existing
  hit/miss counts from `cached_call()`-only callers are identical to
  before. `saved_cost` stays a `cached_call()`-only metric, since
  raw `.get()` doesn't know what an LLM call would have cost.

  **Behavior change to flag:** if you have assertions against
  `stats()` that assumed raw `.get()` was a no-op for stats, those
  assertions will need to be updated.

### Fixed

- **`examples/` are now idempotent across re-runs** (#19).
  `basic_usage.py`, `anthropic_example.py`, `context_aware.py`, and
  `context_aware_example.py` each now use a per-run
  `tempfile.mkdtemp(prefix="sulci_<demo>_")` for `db_path` instead of
  inheriting the SQLite backend's default `./sulci_db` (which polluted
  the repo working tree) or hardcoding `/tmp/sulci_ctx_demo*` (which
  carried state across runs). `async_example.py` and
  `llamaindex_example.py` already used this pattern; no change there.

- **`examples/` fail fast with a useful message when an API key is
  rejected** (#20). `anthropic_example.py` and `async_example.py` now
  catch `anthropic.AuthenticationError` and `openai.AuthenticationError`
  on the first real call, print a one-line "key rejected — verify at
  <provider URL>" message, and fall back to the mock LLM for the rest
  of the demo. Previously a stale or wrong key surfaced as a raw
  `HTTPStatusError` traceback mid-output. The integration examples
  (`langchain_example.py`, `llamaindex_example.py`) already cascade
  across providers and survive missing-SDK gracefully; extending the
  same rejection-path coverage to them is a sibling follow-up since
  their provider-detection structure differs.

### Tests

- **+5 unit tests in `tests/test_telemetry.py::TestFlushIntegration`**
  for the new startup-event branch:
  - `test_startup_only_buffer_emits_one_post` — replaces the legacy
    `test_startup_only_buffer_does_not_post`, which encoded the bug.
  - `test_startup_with_cache_get_emits_two_posts_sharing_fingerprint`
    — codifies the dashboard-join invariant (startup + cache.get from
    the same flush share a fingerprint).
  - `test_startup_sniffs_backend_from_non_startup_event` — backend
    propagates from cache.set in the same batch into the startup row.
  - `test_startup_payload_only_contains_wire_fields` — defense against
    leaking SDK-internal keys past the gateway's `extra='forbid'`.
  - `test_multiple_startup_events_collapse_to_one_post` — defensive
    against any future "connect-after-disconnect" flow that buffers
    multiple startups.
- **+4 unit tests in `tests/test_core.py::TestStats`** for the raw
  `.get()` / `.set()` stats path:
  - `test_raw_get_miss_increments_misses`
  - `test_raw_set_then_raw_get_increments_hits`
  - `test_no_double_counting_via_cached_call` — regression guard for
    the increment-moved-into-get refactor.
  - `test_saved_cost_only_from_cached_call` — invariant that raw API
    use must not contribute to the cost-savings metric.

### Closed issues

- sulci-oss #41 — POST startup events from `_flush()`
- sulci-oss #42 — `Cache.stats()` reports 0/0 for raw `.get()`/`.set()` users
- sulci-oss #20 — examples: fail fast on rejected API key with informative message
- sulci-oss #19 — examples: db_path pollution makes demos non-idempotent
- sulci-oss #25 — packaging: add `authors` block + `Changelog` URL to pyproject.toml

### Follow-ups not in scope here

- sulci-oss #48 (pre-commit smoke ~8 min on macOS) — not folded in;
  the fix has design surface of its own (force CPU on macOS vs prewarm
  cache vs mock embedder for smoke tests) that deserves a dedicated
  discussion.
- sulci-platform #55 (un-awaited AsyncMock in `test_oss_connect_authorize`)
  — platform-side fix; lands separately.
- Extending the #20 fail-fast pattern through `langchain_example.py` and
  `llamaindex_example.py`'s multi-provider cascade — kept out of this
  bundle to avoid touching the provider-detection structure.

---

## [0.5.3] — 2026-05-04

OSS-Connect device-code SDK client (D12). Ships **latent**: the code is in
place, but the surrounding pieces of the OSS-Connect funnel — the gateway
endpoints (sulci-platform `/v1/oss-connect/*`) and the dashboard
`/oss-connect` page — may not yet be deployed in your environment.

The default for the new `prompt` parameter is `False` for that reason.
**Setting `prompt=True` against an environment that hasn't announced
OSS-Connect availability is user error** — wait for the Sulci team's
release announcement that the full chain is live (gateway + dashboard)
before flipping it on. v0.6.0 will flip the default to `True` once the
full chain ships end-to-end.

### Added

- **`sulci.oss_connect`** — RFC 8628 device-code flow client.
  - `run_device_code_flow(gateway_base, sdk_version, client_name)` — blocks
    until the user authorizes via browser, denies, or the 15-minute
    device_code expires. Polls `/v1/oss-connect/token` at the gateway-
    advertised interval. Honors RFC 8628 `slow_down` (interval += 5s).
  - Lazy-imported from `sulci/__init__.py` only on the no-key-found path,
    so `import sulci` cost is unchanged for users who never trigger it.
  - Module is named `oss_connect` (not `connect`) to avoid shadowing the
    public `sulci.connect()` function. See sulci-platform ADR 0014
    §"Naming" for the full chronology of why the platform's URL prefix
    moved from `cli` → `connect` → `oss-connect`.
- **`sulci.connect(prompt=False)`** — new keyword parameter. When `True`,
  if no api_key is found through args/env/config, runs the browser-based
  device-code flow. Default is `False` in v0.5.3; will flip to `True`
  in v0.6.0 once the full OSS-Connect chain ships end-to-end.
- **Four-step api_key resolution** in `sulci.connect()`:
  1. `api_key=` argument
  2. `SULCI_API_KEY` environment variable
  3. `~/.sulci/config` (persisted from a prior successful connect)
  4. Browser device-code flow (only if `prompt=True`)
  Step 3 is new in v0.5.3 — connect()'s previously documented
  resolution stopped at step 2.
- **`SULCI_GATEWAY` env var** — overrides the gateway base URL for the
  device-code flow (default `https://api.sulci.io`). Used for staging /
  local-dev environments. Resolved at module-import time so the same
  value is used by both telemetry and the new device-code flow.

### Changed

- **`sulci.connect()` signature** gains the `prompt: bool = False`
  parameter. Existing callers that pass `api_key=...` are unaffected.
- **`tests/test_connect.py`** — three tests in the new `TestDeviceCodeFlow`
  class that exercise the device-code-fires path now pass `prompt=True`
  explicitly. `test_connect_without_key_does_not_enable_telemetry` and
  `test_connect_does_not_start_thread_without_key` continue to call with
  `prompt=False` to assert the no-op behavior.

### Tests

- **+27 new tests** across two files:
  - `tests/test_oss_connect.py` (new) — 19 tests for the RFC 8628 client
    (httpx mocked; deterministic; covers `slow_down`, denied, expired,
    network-error retry, the `_safe_error_field` helper).
  - `tests/test_connect.py::TestDeviceCodeFlow` — 8 new tests for the
    integration in `connect()` (resolution order, persistence on success,
    `prompt=False` escape hatch, RuntimeError propagation, persist-failure
    non-blocking).
- **Test-gate fix** — `scripts/run_tests_per_file.py::DEFAULT_FILES`
  gains `tests/test_oss_connect.py` so `make checkin` covers the new
  module. Without this addition, the 19 tests would exist but never run
  in the gate (same shape of test-gate omission caught and fixed
  upstream in sulci-platform PR #50). Per-file runner total goes from
  312 to 331.

### Compatibility

- **Backward-compatible against v0.5.2.** Existing `sulci.connect(api_key=...)`,
  `sulci.connect()` with `SULCI_API_KEY` set, and `sulci.connect(telemetry=False)`
  all preserve their v0.5.2 semantics.
- **The new step 3 (`~/.sulci/config` resolution) is observable only when
  the user has previously called `sulci.connect()` and `~/.sulci/config`
  contains an `api_key` field.** v0.5.2 didn't write this field.
  Pre-existing v0.5.2 configs (which only have `machine_id`) read as
  step 3 returning `None`, identical to no config existing.

### Privacy

- **No new wire fields.** The device-code flow is a `POST` to
  `/v1/oss-connect/{device-code,token}` with `{sdk_version, client_name,
  device_code, grant_type}` — no telemetry, no metrics, no user content.
- **The raw `api_key` returned by the flow is persisted to
  `~/.sulci/config` (mode 0600)** — same path / mode the v0.5.2
  `machine_id` already uses. The file is never logged or transmitted.

### Latent feature explainer

In v0.5.3, calling `sulci.connect(prompt=True)` against an environment
where the gateway hasn't deployed `/v1/oss-connect/*` endpoints will:

  1. Hit a 404 on `POST /v1/oss-connect/device-code`
  2. Raise `RuntimeError: sulci.connect() failed: could not request device code (HTTPStatusError: ...)`
  3. Leave `sulci._api_key = None` and telemetry disabled

If the gateway endpoints are deployed BUT the dashboard `/oss-connect`
page isn't:

  1. The SDK gets a `device_code` and prints `Visit {URL} and enter code: WXYZ-2345`
  2. The user follows the URL → 404 from the dashboard
  3. SDK polls for 15 minutes, then raises `RuntimeError: sulci.connect() timed out`

Both failure modes are clearly diagnosable. The default `prompt=False` is
designed to prevent users from discovering them by accident.

### Closed issues

- sulci-oss #35 (improvement 3) — device-code flow client, originally
  bundled with v0.5.2's improvements 1+2 but split out per launch-plan
  Phase Wave 2 sequencing.

### Wave 2 status (updated from v0.5.2 preview)

- ✅ **D12 — sulci-oss device-code client** (this release; latent)
- ✅ **D4 / D4.5 / D5 — gateway endpoints** (sulci-platform PR #51, pending merge + deploy)
- 🔲 **D7 — dashboard `/oss-connect` page** (sulci-platform; not yet started)
- ⏳ **v0.6.0 — promotion to production-ready** (after D7 merges + e2e validated)

### Naming chronology

The flow's URL/file naming went through two rename rounds at design time
in sulci-platform: `cli` → `connect` → `oss-connect`. The end-state
naming (`oss-connect` for URLs, `oss_connect` for Python identifiers)
is what's in this v0.5.3 release. The intermediate names do not appear
anywhere in the shipped code. Full chronology is in
`sulci-platform/docs/architecture/adrs/0014-restore-oss-connect-device-code.md`.

---

Connected-OSS telemetry wave 1: per-deployment fingerprinting, `cache.set` aggregation,
opt-in nudge. Pairs with sulci-platform's already-shipped `/v1/telemetry`,
`/v1/analytics/deployments`, and `oss_connect` plan (gateway-side D1/D2/D3/D6/D9).
Wave 2 (`sulci.connect()` device-code flow) follows in v0.6.0 once the gateway's
`/v1/cli/device-code` and `/v1/cli/token` endpoints land.

### Added

- **`sulci.config`** — persistent SDK config at `~/.sulci/config`.
  - `load()` / `save()` / `update()` / `get_machine_id()` helpers.
  - File written with mode `0600`; directory `0700`. Atomic write via tempfile + rename.
  - Silent fallback on corruption — a malformed file never blocks `import sulci` or `Cache(...)`.
  - `get_machine_id()` generates a fresh `uuid4` on first call and persists it; same machine returns the same id forever after. Used as one input to the deployment fingerprint.
- **`sulci.telemetry`** — helpers for the legacy `connect()` emit pipe (distinct from the v0.5.0 `sulci.sinks.telemetry.TelemetrySink`, which is the per-event `EventSink` implementation — see module docstring for the disambiguation).
  - `build_fingerprint(machine_id, backend, embedding_model, threshold, context_window)` — stable, anonymous, config-aware deployment hash. 24 hex chars (12-byte blake2b).
  - `WIRE_FIELDS` — the exact 9-field allowlist accepted by the gateway `TelemetryEvent` schema. Imported into `_post()` as a final safety strip against any future flush() drift.
  - `coerce_to_wire(payload)` — strips non-allowlisted keys.
  - `python_version_str()` — version helper for the wire payload.
- **`fingerprint` field in `/v1/telemetry` payloads.** Resolves the `analytics.py` comment at line 103: *"v0.5.1 sends None"*. Now sends a stable per-deployment hash so the dashboard's "Active deployments" tile dedupes correctly across restarts.
- **`cache.set` events** are now buffered and POSTed as a separate aggregated batch per flush. Convention (documented in `_flush()`): `hits = number of set() calls aggregated`, `misses = 0`, `avg_latency_ms = average set() latency`. The gateway's TelemetryEvent schema already accepts `event='cache.set'`.
- **Passive nudge in `Cache.stats()`** — after 100 raw `.get()` calls on a Cache instance, prints a single stderr line suggesting `sulci.connect()`. One-shot per process; suppressed by `SULCI_QUIET=1` or by `sulci.connect()` already being active.

### Changed

- **`Cache.set()`** now records the per-call latency and emits a `cache.set` telemetry event when the instance has telemetry enabled and `sulci.connect()` has been called. The structured `EventSink` path (added in v0.5.0) is unchanged.
- **`Cache.get()`** emit payload now also carries `embedding_model`, `threshold`, and `context_window` keys so `_flush()` can compute the deployment fingerprint without coupling to a specific event type. These keys never reach the wire — `_post()` strips them via the `WIRE_FIELDS` allowlist.
- **`_flush()` rewritten** to handle multiple event types in one drain: emits up to two HTTP POSTs per flush (one for `cache.get`, one for `cache.set`), each carrying the deployment fingerprint. Empty-bucket short-circuiting preserved.

### Fixed

- None. v0.5.2 is purely additive.

### Privacy

- **No new wire fields beyond `fingerprint`**, which is a one-way hash containing no recoverable PII. Deriving the originating `machine_id` from a fingerprint requires brute-forcing a 96-bit blake2b — computationally infeasible.
- **Five new tests in `test_telemetry.py::TestPrivacyInvariants`** assert that `query`, `response`, and `embedding` fields are never sent on the wire even when poisoned events are placed directly in the buffer. Defense-in-depth against future regressions.
- **`coerce_to_wire()` is invoked in `_post()`** as a final safety strip — even if a future `_flush()` change accidentally constructs a payload with an extra key, the gateway's `extra='forbid'` rejection (HTTP 422) won't drop entire batches.

### Tests

- **+56 new tests** across three new files:
  - `tests/test_config.py` — 20 tests (1 skipped on root)
  - `tests/test_telemetry.py` — 24 tests
  - `tests/test_nudge.py` — 13 tests (covers threshold, one-shot, suppression, return-value invariants)
- **0 regressions** in pre-existing `tests/test_connect.py` (28/28 unit tests; 4 Cache-integration tests require a real embedder and run in CI).

### Compatibility

- **Fully backward-compatible.** Existing `sulci.connect(api_key=...)` flow unchanged. All v0.5.x callers continue to work.
- The `fingerprint` field is `Optional[str]` on the gateway side; older SDK versions sending `None` (or omitting it entirely) continue to be accepted.
- Nudge defaults to ON. Set `SULCI_QUIET=1` to silence; set it in CI before running tests against this version if any test asserts on clean stderr.

### Known limitations (deferred to follow-up issues)

- `_emit("startup", {})` events emitted by `connect()` are drained by `_flush()` but never POSTed — the legacy emit pipe lacks a `startup` HTTP path. The gateway schema already accepts `event='startup'`. Documented in `_flush()`'s docstring.
- `Cache._stats["hits"]/["misses"]` only increment in `cached_call()`, not in raw `.get()`. The new `_query_count` field works around this for the nudge logic, but the underlying `stats()` inconsistency remains.

### Closed issues

- sulci-oss #35 — SDK fingerprint emission.

### Wave 2 preview (v0.6.0)

`sulci.connect()` device-code flow, `sulci/cli.py`, `~/.sulci/config` API-key persistence
end-to-end. Blocked on sulci-platform `/v1/cli/device-code` and `/v1/cli/token` endpoints
(D4/D5) and the dashboard `/cli` authorization page (D7).

---

## [0.5.1] — 2026-04-28

### Added

- `RedisBackend(key_prefix=...)` constructor kwarg.
  - Defaults to `"sulci:"` (matches v0.4.x behavior — no breaking change for existing callers).
  - Replaces three previously-hardcoded `"sulci:*"` literals in `_key()`, the SCAN match pattern in `search()`, and the keys-glob in `clear()`.
  - Production callers can now pick a custom prefix to coexist with other Redis-using processes on a shared daemon (e.g., `RedisBackend(key_prefix="acme:cache:")`).

### Changed

- **CI matrix** — Python 3.10 now tested in `tests.yml` and `publish.yml`. Previously: `[3.9, 3.11, 3.12]`. Now: `[3.9, 3.10, 3.11, 3.12]`. Aligns CI coverage with `pyproject.toml` classifiers (which already claimed 3.10 support).
- `LOCAL_SETUP.md` Python-version hint reflects the new matrix.

### Fixed

- **Test fixtures (`backend_instance` in `tests/compat/conftest.py`)**: now clear state on setup, not just teardown. Defends against state leaked by any test that crashed before reaching teardown. SQLite/Qdrant fixtures get fresh `tmp_path`/collection per call so the setup clear is a no-op for them; matters for Redis where the daemon is shared across tests.
- **Test fixtures (`event_sink` in `sulci/tests/compat/conftest.py`)**: `RedisStreamSink` writes to a persistent Redis stream key that the fixture had no teardown for. Two changes: factory now `DEL`s the test stream key on construction; fixture now has a teardown that `DEL`s the stream when the implementation has a Redis client.
- **Redis test namespacing**: All Redis-backed tests now use a session-scoped key prefix (`sulci:test:<8-char-uuid>:`) instead of the production-default `sulci:`. Tests SCAN/MATCH only their own session's keys; sulci-platform's runtime data on the same Redis daemon is now safe during `make checkin` execution. Two concurrent `make checkin` runs against the same Redis no longer interfere.

### Verified

`make checkin` runs cleanly with sulci-platform Docker Compose stack active. No platform state corruption; no test-result corruption from platform writes.

### Compatibility

- **Fully backward-compatible.** All v0.5.0 code continues to work unchanged.
- The new `RedisBackend(key_prefix=...)` kwarg is purely additive; the default value matches v0.5.0 behavior. Honors the ADR 0005 protocol-stability commitment via additive-extension.
- 390 existing tests pass; no test count change in v0.5.1 (no new test files, only fixture and CI infrastructure changes).

### Closed issues

- #28 — Fixture: clear-on-setup pattern for backend_instance
- #29 — Namespace conformance test runs to prevent cross-project Redis interference
- #30 — Decide on Python 3.10 in CI matrix (Option A — added to both matrices)

### Phase 3 readiness

All four v0.5.1 blockers needed for Phase 3 entry are now closed: three in this release plus sulci-platform#12 (Dependabot triage). See `sulci-platform/docs/roadmap/PHASE-3-WORKSTREAM-C.md` for the gating list.

---

## [0.5.0] — 2026-04-27

### Added

- `sulci.sessions` package — SessionStore protocol and implementations
  - `SessionStore` — public stable protocol
  - `InMemorySessionStore` — default, process-local (extracted from sulci/context.py)
  - `RedisSessionStore` — Redis Lists-backed for horizontal scaling
- `sulci.sinks` package — EventSink protocol and implementations
  - `EventSink` — public stable protocol
  - `CacheEvent` — dataclass representing a cache event
  - `NullSink` — default no-op sink
  - `TelemetrySink` — HTTPS POST with strict field allowlist (never emits query/response/vectors)
  - `RedisStreamSink` — writes scrubbed events to a Redis Stream
- `Cache(session_store=..., event_sink=...)` — two new constructor kwargs
  - Both default to `None`, which uses `InMemorySessionStore()` and `NullSink()` respectively
  - Enables horizontal-scale deployments (via `RedisSessionStore`) and observability/billing (via any EventSink)
- `SyncCache` — alias for `Cache` exported from the top-level `sulci` namespace
  - Naming symmetry with existing `AsyncCache`
  - `sulci.SyncCache is sulci.Cache` returns True
- Conformance suites: `sulci.tests.compat.test_session_store_conformance` + `test_event_sink_conformance`

### Changed

- `sulci/__init__.py` exports `SyncCache` and the new session/sink primitives
- `Cache.__init__` gains `session_store` and `event_sink` kwargs (both `None` by default).
  When `session_store` is injected, Cache uses an internal bridge
  (`_ProtocolAdaptedSessionStore`) to translate between the new
  `sulci.sessions.SessionStore` protocol and the legacy `ContextWindow` surface
  Cache uses internally.
- `sulci/context.py` is **unchanged** — the legacy `SessionStore` class
  (higher-level ContextWindow manager) remains the default when no
  `session_store` kwarg is passed. See ADR 0007.

### Compatibility

- Fully backward-compatible. All v0.4.x code continues to work unchanged.
- 335+ existing tests pass + ~50 new tests added (sessions, sinks, conformance, injection).
- `AsyncCache` behavior unchanged. No async-native refactor.
- Defaults preserve exact v0.4.x behavior if new kwargs are not supplied.
- `from sulci.context import SessionStore` returns the **legacy** higher-level
  manager class (unchanged), not `sulci.sessions.InMemorySessionStore`. The
  bundle originally proposed aliasing them; we kept them separate to preserve
  v0.4.x behavior for direct importers. See ADR 0007 for the full rationale.
  When `Cache(session_store=<sulci.sessions.SessionStore impl>)` is injected,
  Cache adapts via an internal bridge (`_ProtocolAdaptedSessionStore`) that
  rebuilds a transient `ContextWindow` per lookup.

### Privacy

- `TelemetrySink` and `RedisStreamSink` enforce a strict field allowlist (`_ALLOWED_FIELDS` frozenset).
- The `CacheEvent.metadata` dict is NEVER shipped externally.
- Query text, response text, and embedding vectors NEVER leave the process via shipped sinks.

### Related ADRs

- ADR 0004 — SessionStore and EventSink protocols
- ADR 0007 — Preserve the legacy `sulci.context.SessionStore` class (B1 adapter)

### Roadmap

- See `docs/roadmap/FUTURE-DESIGN-OPTIONS.md` — v0.5.0 is additive by design.
  True async-native Cache refactor is deferred as roadmap item R2.

---

## [0.4.0] — 2026-04-26

### Added

- **Public Backend protocol** (`sulci/backends/protocol.py`) — formalizes the
  shape every vector-cache backend must satisfy. `runtime_checkable` Protocol
  with `store()`, `search()`, `clear()` methods. New `tenant_id` keyword-only
  parameter for multi-tenant partition isolation. STABLE API per ADR 0005.
- **Public Embedder protocol** (`sulci/embeddings/protocol.py`) — formalizes
  the shape MiniLMEmbedder and OpenAIEmbedder already had: `dimension`
  property, `embed(text)`, `embed_batch(texts)`. L2-normalization required.
- **`tenant_id` partition isolation** — first-class kwarg on `Cache.get()`,
  `Cache.set()`, and `Cache.cached_call()`. Forwarded to backend's `store`/
  `search` calls. Tenant isolation is a hard boundary — entries from other
  tenants must not be returned even when similarity exceeds threshold.
- **Keyword-only enforcement** (`*,` separator) on `Cache.get()`, `set()`,
  `cached_call()` — locks down `tenant_id`, `user_id`, `session_id`, and
  `metadata` as keyword-only to prevent positional misuse.
- **`ENFORCES_TENANT_ISOLATION` class attribute** on every backend, declaring
  whether `search()` filters by tenant_id. QdrantBackend = True (uses payload
  Filter); other shipped backends accept tenant_id as a label only.
- **Conformance test suite** (`tests/compat/`) — parametrized tests verifying
  that any class claiming to implement Backend or Embedder protocol satisfies
  the contract. Three groups: TestStructural (signature checks, runs always),
  TestRoundTrip (behavioral, runs when backend is constructable),
  TestTenantIsolation (runs only on backends with ENFORCES_TENANT_ISOLATION).
- **Qdrant tenant isolation tests** (`tests/test_qdrant_tenant_isolation.py`)
  — 11 tests across 8 customer-support scenarios (HelpDesk AI / Acme /
  Globex / Initech) verifying isolation guarantees end-to-end against an
  embedded Qdrant. Test names framed as product scenarios so failures
  describe user-impacting breakage.
- **`docs/protocols.md`** — Backend and Embedder protocol reference for
  developers extending sulci with custom backends or embedders.
- **`docs/multi_tenancy_and_isolation.md`** — OSS-layer trust and partition
  model. Generic customer scenarios, what's enforced where, FAQ on hashing,
  rotation, GDPR, encryption-at-rest.
- **`examples/extending_sulci/custom_backend.py`** — InMemoryBackend
  reference implementation. ~150 lines, in-memory dict-based, satisfies the
  full Backend protocol with self-test.
- **Developer tooling** (`scripts/`):
  - `run_tests_per_file.py` — runs pytest test files in fresh subprocesses
    (avoids MPS deadlock on Apple Silicon)
  - `run_examples.py` — runs every example + smoke test with timeout
  - `verify_integration_examples.py` — 8-scenario LLM provider matrix for
    langchain/llamaindex examples
  - `verify_benchmark.py` — runs canonical benchmark and verifies headline
    numbers haven't drifted from `benchmark/baseline.json`
- **`benchmark/baseline.json`** — canonical TF-IDF benchmark numbers from
  pre-v040-baseline. Used by verify_benchmark.py for regression detection.

### Changed

- **`__version__`** is now derived dynamically from `pyproject.toml` via
  `importlib.metadata.version("sulci")`. Previously hardcoded in three
  places (pyproject.toml, \_SDK_VERSION, USER_AGENT) which had drifted.
- **`_SDK_VERSION`** still exists (telemetry payload field name unchanged
  on the wire) but now equals `__version__`. Marked as deprecated alias.
- **`SulciCloudBackend.USER_AGENT`** now `f"sulci/{__version__}"` (was
  hardcoded "sulci/0.3.0", drifted by two minor releases).
- **`SulciCloudBackend.store()`** added (was missing — `cloud.py` only had
  `upsert()` while `core.py` always called `self._backend.store()`. Latent
  AttributeError on `Cache(backend='sulci').set()` is now fixed).

### Fixed

- **qdrant-client 1.x compatibility**: `QdrantBackend.search()` migrated
  from `client.search()` (removed) to `client.query_points()` with
  `.points` iteration. `QdrantBackend.clear()` now deletes points (preserves
  collection schema) instead of `delete_collection()` which broke subsequent
  operations on qdrant-client 1.x.
- **Cross-tenant data leak in `tenant_id=None` read path**: stores wrote
  `tenant_id="global"` for None, but searches with `tenant_id=None` added
  no filter, so unscoped reads silently returned named-tenant entries.
  Fixed by always filtering to "global" when None is passed. Caught by
  `test_named_tenant_entry_does_not_match_global_search`.
- **`examples/anthropic_example.py`** previously hardcoded `backend="chroma"`
  and documented `pip install "sulci[chroma]" anthropic` install line, but
  the README's quickstart recommends `sulci[sqlite]`. Mismatch caused
  ImportError on first run for users following the README. Switched to
  `backend="sqlite"` (functionally equivalent for this demo) and added
  graceful mock-LLM fallback when `ANTHROPIC_API_KEY` is unset.
- **`benchmark/.gitignore`** had a typo (`iresults/*.json`) that left
  benchmark output untracked-but-visible in `git status`. Fixed.

### CI

- `qdrant-client` added to `.github/workflows/tests.yml` install step.
- New CI steps: "Test Qdrant tenant isolation" and "Conformance suite" run
  early in the matrix to fail-fast on isolation regressions.

### Makefile

- New targets: `test-per-file`, `test-per-file-fast`, `examples`,
  `verify-integration-examples`, `benchmark-verify`, `checkin`. The
  `checkin` target chains smoke + tests + examples + benchmark-verify
  as a comprehensive pre-PR check (~7 min wall-clock).

### Notes

- `tenant_id` is honored ungated when passed (no `personalized` flag
  required). `user_id` continues to be gated by `personalized=True` for
  backwards compatibility with v0.3.x users; this asymmetry will be
  reconciled in v0.5.0+.
- After a version bump, run `pip install -e . --no-deps` in editable
  installs to refresh `importlib.metadata`'s cached dist-info.
- Built-in TF-IDF benchmark numbers verified byte-stable across the
  v0.3.x line and pre-v040-baseline (CI runs #26 through #36).
- Verified end-to-end via `make checkin`: 290 pytest tests pass, 12/12
  examples pass (including real OpenAI + Anthropic API calls), all 17
  benchmark metrics within tolerance vs baseline.

---

## [0.3.7] — 2026-04-11

### Added

- `sulci.AsyncCache` — non-blocking async wrapper around `sulci.Cache`.
  Delegates all cache operations to a thread pool via `asyncio.to_thread()`
  so the event loop is never blocked during embedding or vector search.
  Required for FastAPI, LangChain async chains, LlamaIndex async agents,
  and any asyncio-based application.
- `sulci/async_cache.py` — `AsyncCache` implementation
  - Async methods: `aget()`, `aset()`, `acached_call()`, `aget_context()`,
    `aclear_context()`, `acontext_summary()`, `astats()`, `aclear()`
  - Sync passthrough: `get()`, `set()`, `cached_call()`, `stats()`, `clear()`,
    `get_context()`, `clear_context()`, `context_summary()`
  - All constructor parameters identical to `sulci.Cache`
- `sulci/__init__.py` — `AsyncCache` exported, `_SDK_VERSION` bumped to `0.3.7`
- `smoke_test_async.py` — end-to-end async smoke test (24 checks)
- `examples/async_example.py` — AsyncCache demo with FastAPI pattern shown
  Supports OpenAI, Anthropic, or built-in mock LLM fallback

### Tests

- `tests/test_async_cache.py` — 25 tests (212 total, 205 passed, 7 skipped)
  - `TestConstruction` (4) — constructor passthrough, repr, invalid backend
  - `TestAget` (5) — hit, miss, session_id, user_id, 3-tuple return
  - `TestAset` (3) — stores entry, advances context window, session_id
  - `TestAcachedCall` (4) — hit, miss, dict shape, cost_per_call
  - `TestContextMethods` (4) — aget_context, aclear_context, acontext_summary,
    session isolation
  - `TestStats` (3) — astats dict shape, aclear resets stats, repr
  - `TestSyncPassthrough` (2) — sync get/set/stats still work on AsyncCache

### Makefile

- `make smoke-async` — AsyncCache smoke test only
- `make test-async` — `tests/test_async_cache.py` only
- `make smoke` updated — includes `smoke_test_async.py`
- `make test-all` updated — includes `tests/test_async_cache.py`

### Notes

- Zero breaking changes — `sulci.Cache` is unchanged
- Pattern: `asyncio.to_thread()` — idiomatic Python 3.9+, same approach
  used by LangChain `BaseCache.alookup()` and `SulciCacheLLM.acomplete()`
- Future v2: native async backends for Qdrant (`AsyncQdrantClient`) and
  Redis (`redis.asyncio`) when throughput demands justify the rewrite

---

## [0.3.6] — 2026-04-10

### Changed

- Version bump to re-release v0.3.5 content to PyPI — the v0.3.5 wheel was
  published from an earlier tag before examples and doc updates were committed.
  No code changes — library behaviour is identical to v0.3.5.

### Includes (carried from v0.3.5)

- `examples/langchain_example.py` — LangChain stateless + context-aware demo
- `examples/llamaindex_example.py` — LlamaIndex Settings.llm demo
- `LOCAL_SETUP.md` — Step 12, smoke-llamaindex, v0.3.5 references
- `README.md` — examples section, Project Structure updated

---

## [0.3.5] — 2026-04-09

### Added

- Native LlamaIndex LLM wrapper `SulciCacheLLM` — first correct LLM-level
  semantic cache for LlamaIndex. Wraps any `LLM` subclass (OpenAI, Anthropic,
  Ollama, HuggingFaceLLM, etc.). `complete()` and `chat()` are cached;
  streaming passes through uncached; async methods use `run_in_executor`.
- `sulci/integrations/llamaindex.py` — `SulciCacheLLM(LLM)` implementation
- `sulci/integrations/__init__.py` — updated with LlamaIndex entry
- `pyproject.toml` — `llamaindex = ["llama-index-core>=0.10.0"]` extra
- `smoke_test_llamaindex.py` at repo root

### Tests

- `tests/test_integrations_llamaindex.py` — 29 tests (TestConstruction,
  TestComplete, TestChat, TestStreaming, TestAsync, TestStats)

### Examples

- `examples/langchain_example.py` — two demos in one file:
  - Demo 1: stateless `set_llm_cache(SulciCache(...))` — semantic hit/miss
    across 4 rounds showing real API latency vs <10ms cache hits
  - Demo 2: context-aware `ContextAwareSulciCache` subclass using `llm_string`
    as `session_id` — two isolated user sessions (alice/bob), 58% hit rate
  - Supports OpenAI, Anthropic, or built-in mock LLM fallback
  - API key detection logged at startup (`✓ found` / `✗ not set`)

- `examples/llamaindex_example.py` — four rounds:
  - Round 1: fresh questions per session (all misses)
  - Round 2: paraphrases in same sessions (93-96% similarity hits, <7ms)
  - Round 3: context-aware follow-ups in a single topic session
  - Round 4: clearly unrelated question (clean miss)
  - `Settings.llm = SulciCacheLLM(...)` — idiomatic LlamaIndex pattern
  - Supports OpenAI, Anthropic, or built-in mock LLM fallback
  - API key detection logged at startup

### Notes

- GPTCache's claimed LlamaIndex integration was a broken global OpenAI API
  patch. SulciCacheLLM uses the idiomatic `LLM` subclass pattern and works
  with any LlamaIndex-compatible model.

---

## [0.3.4] — 2026-04-08

### Fixed

- `SulciCache`: `namespace_by_llm=True` now logs a warning and is silently
  disabled when `backend="sulci"`. Sulci Cloud handles tenant isolation
  server-side; `db_path`-based partitioning was creating phantom
  `SulciCloudBackend` instances with no effect.

### Added

- `SulciCloudBackend`: new `gateway_url` parameter (default: `https://api.sulci.io`).
  Enterprise VPC customers can point to a self-hosted gateway:
  `Cache(backend="sulci", api_key="...", gateway_url="https://cache.acme.internal")`
- `Cache`: `gateway_url` threaded through `_load_backend()` when `backend="sulci"`.
- `SulciCache` (LangChain): `gateway_url` documented in `**kwargs` table.

### Tests

- `test_cloud_backend.py`: 3 new tests — default gateway URL, custom gateway URL,
  trailing slash stripping
- `test_integrations_langchain.py`: 3 new tests — `TestNamespaceByLLMCloudWarning`

---

## [0.3.3] — 2026-04-08

### Added

**LangChain integration — context-aware semantic cache adapter**

- `sulci/integrations/__init__.py` — new `integrations` sub-package
- `sulci/integrations/langchain.py` — `SulciCache(BaseCache)` for LangChain
  - Positioned as the **context-aware semantic cache** — distinct from stateless
    semantic caches (GPTCache, RedisSemanticCache) already in langchain-community
  - `lookup(prompt, llm_string)` — semantic match via `sulci.Cache.get()`,
    returns `list[Generation]` on hit, `None` on miss
  - `update(prompt, llm_string, return_val)` — stores first `Generation.text`
  - `clear()` — evicts data and resets namespace dict via `finally` block
    (guarantees `_ns_caches` is always cleared even if a data-clear raises)
  - `namespace_by_llm=True` (default) — separate cache partition per LLM config;
    uses MD5-hashed `db_path` suffix for local backends
  - `alookup`, `aupdate`, `aclear` — async overrides via `run_in_executor`
  - Silent failure throughout — cache errors never raise to the caller's app
  - `stats()` — passthrough to `sulci.Cache.stats()`
  - Lazy import of `langchain-core` — raises `ImportError` with install hint
    if not installed; core `sulci` package never depends on LangChain
  - `langchain_core.globals` used (not `langchain.globals`) — only `langchain-core`
    required, not the full `langchain` package

**LangChain integration — tests**

- `tests/test_integrations_langchain.py` — 24 tests, zero LLM API keys required
  - `TestContract` (9) — lookup/update/clear/exact-hit/semantic-miss/list-return
  - `TestNamespacing` (4) — model isolation, shared mode, clear resets dict
  - `TestSilentFailure` (3) — db errors in lookup/update/clear never raise
  - `TestAsync` (4) — alookup/aupdate/aclear/concurrent reads
  - `TestStats` (3) — dict shape, required keys, repr format
  - `TestGlobalRegistration` (1) — `set_llm_cache` / `get_llm_cache` round-trip

**LangChain integration — smoke test**

- `smoke_test_langchain.py` — standalone smoke test at repo root
  - Runs automatically via `setup.sh` after core smoke test
  - Skips gracefully (exit 0) if `langchain-core` is not installed
  - Covers: create → store → exact hit → unrelated miss → stats

**Developer tooling**

- `setup.sh` — updated to install `.[langchain]` extra and run both smoke tests
  sequentially; `Next steps` section updated to list actual `make` targets
- `Makefile` — new targets:
  - `make smoke` — runs `smoke_test.py` + `smoke_test_langchain.py`
  - `make smoke-core` — core smoke test only
  - `make smoke-langchain` — LangChain smoke test only
  - `make test` — core pytest suite
  - `make test-integrations` — LangChain + LlamaIndex integration tests
  - `make test-all` — full suite
  - `make test-cov` — full suite with coverage report
  - `make verify` — `smoke` + `test-all` (pre-commit full check)

**LangChain community PR artifact**

- `langchain_community_pr/sulci_cache_addition.py` — ready-to-paste addition
  for `langchain_community/cache.py` PR to `langchain-ai/langchain`

### Changed

- `pyproject.toml` — version bumped to `0.3.3`
- `pyproject.toml` — added `langchain = ["langchain-core>=0.1.0"]` optional extra
- `pyproject.toml` — added `pytest-asyncio==0.21.1` to `dev` deps
  (pinned — 0.23.x has a package collection bug)
- `pyproject.toml` — added `asyncio_mode = "auto"` to `[tool.pytest.ini_options]`
- `pyproject.toml` — added `"context-aware-semantic-cache"` keyword for PyPI search
- `sulci/__init__.py` — `_SDK_VERSION` bumped from `"0.3.0"` to `"0.3.3"`
  (was already out of sync with pyproject.toml since 0.3.1)

### Fixed (discovered during integration test development)

- `sulci/integrations/langchain.py` `clear()` — moved `_ns_caches.clear()` into
  a `finally` block so namespace dict is always reset even if a backend `clear()`
  raises an exception
- `tests/test_integrations_langchain.py` — assertion order in
  `test_clear_removes_all_partitions` corrected: `len(_ns_caches) == 0` must be
  checked _before_ any `lookup()` call, since `lookup()` calls `_cache_for()`
  which recreates namespace entries for any `llm_string` it encounters
- `tests/test_integrations_langchain.py` — `test_concurrent_lookups_no_crash`
  revised to check no exceptions are raised (not that all 20 concurrent SQLite
  reads return non-None — a single connection under high concurrency may return
  miss on some reads, which is acceptable behaviour)
- `tests/test_integrations_langchain.py` — `TestGlobalRegistration` import changed
  from `langchain.globals` to `langchain_core.globals` — only `langchain-core` is
  required, not the full `langchain` package

### Backward compatibility

- All existing code using local backends (`sqlite`, `chroma`, `faiss`, etc.)
  is completely unaffected — zero breaking changes
- `context_window=0` (default) remains stateless and identical to prior versions
- New `integrations` sub-package is purely additive — not imported unless
  explicitly requested by the caller

### Test count after this release

```
test_core.py                       27 tests
test_context.py                    35 tests
test_backends.py                    9 tests  (skipped if backend dep not installed)
test_connect.py                    32 tests
test_cloud_backend.py              25 tests
test_integrations_langchain.py     24 tests  ← new
────────────────────────────────────────────
Total                             152 tests
```

---

## [0.3.2] — 2026-03-27

### Patent & Legal

- Updated NOTICE file with US Patent Application No. 64/018,452
- Added Patent Pending badge and notice to README
- Updated PyPI description to include Patent Pending

### No code changes — library behaviour is unchanged

---

## [0.3.1] — 2026-03-27

### License

- Changed from MIT License to Apache License 2.0
- Added NOTICE file as required by Apache 2.0
- Updated pyproject.toml classifier to Apache Software License
- Added SPDX identifiers to all Python source files
- Rationale: Apache 2.0 includes patent retaliation clause and explicit
  patent grant; aligns with pending patent application IDF-SULCI-2026-001

### No code changes — library behaviour is unchanged

---

## [0.3.0] — 2026-03-25

### Added

- **Sulci Cloud backend** — `Cache(backend="sulci", api_key="sk-sulci-...")` routes
  cache operations to `api.sulci.io` via HTTPS. Zero infrastructure for the user —
  one parameter change from any self-hosted backend.
- `sulci/backends/cloud.py` — `SulciCloudBackend` via httpx
  - `search()` returns `(None, 0.0)` on timeout or any error — never crashes caller
  - `upsert()` failure is silent — fire and forget
  - `delete_user()` and `clear()` also fail silently
- `sulci.connect(api_key, telemetry=True)` — opt-in gateway to Sulci Cloud
  - Stores API key at module level for all `Cache(backend="sulci")` instances
  - Enables optional usage telemetry — flushed to `api.sulci.io` every 60 seconds
  - Strictly opt-in: `_telemetry_enabled = False` until `connect()` is called
- `Cache` gains two new constructor parameters:
  - `api_key` — API key for `backend="sulci"` (resolution: arg > env > `connect()`)
  - `telemetry` — per-instance opt-out (default `True`)
- `SULCI_API_KEY` environment variable — zero-code alternative to `api_key=`
- `sulci[cloud]` install extra — `pip install "sulci[cloud]"`
- `tests/test_connect.py` — 32 tests covering `sulci.connect()` and telemetry
- `tests/test_cloud_backend.py` — 25 tests covering `SulciCloudBackend` and wiring

### Changed

- Version bumped to `0.3.0`
- `README.md` updated with Sulci Cloud section and `sulci.connect()` docs
- `LOCAL_SETUP.md` updated with Week 2 and Week 3 setup instructions
- `pyproject.toml` — added `cloud = ["httpx>=0.27.0"]` extra

### Backward compatibility

- All existing code using local backends (`sqlite`, `chroma`, `faiss`, etc.) is
  completely unaffected — zero breaking changes
- `connect()` and `api_key=` are purely additive
- Default backend behaviour unchanged

---

## [0.2.5] — 2026-03-17

### Repository & Housekeeping

- Transferred repository from `id4git/sulci` to `sulci-io/sulci-oss` under new GitHub org
- Renamed repo from `sulci` to `sulci-oss` (PyPI package name `sulci-cache` and import `from sulci` unchanged)
- Added `LICENSE` (MIT) and `NOTICE` files to repo root with clear OSS/enterprise demarcation
- Updated `pyproject.toml` repository URLs to reflect new org and repo name

### Docs

- Added `LOCAL_SETUP.md` — full local development guide: venv setup, install, test runs, smoke test, troubleshooting
- Corrected test counts across `README.md` and `LOCAL_SETUP.md`:
  - `test_core.py`: 27 tests (was 26)
  - `test_context.py`: 35 tests (was 27)
  - `test_backends.py`: 9 tests (was unknown)
  - Total: 71 tests (was 53)
- Updated project structure tree in both docs to match actual repo layout (7 directories, 29 files)
- Removed inline changelog table from `README.md` — full history lives in `CHANGELOG.md`
- Fixed `pyproject.toml` comment to correctly distinguish repo root (`sulci-oss/`) from package directory (`sulci/`)

### No code changes — library behaviour is identical to 0.2.4

---

## [0.2.4] — 2026-03-16

- Release v0.2.4 — Developer Edition baseline — pre-enterprise transition

---

## [0.2.3] — 2026-03-16

- Release v0.2.3 — correct test counts, updated docs

---

## [0.2.2] — 2026-03-15

- Packaging fix: re-publish of 0.2.1 (PyPI file conflict resolution)

---

## [0.2.1] — 2026-03-11

- Context-aware benchmark suite: `--context` flag
- 25 session pools, brute-force cosine scan
- Results: +20.8pp resolution accuracy

---

## [0.2.0] — 2026-03-10

### Added

- **Context-aware caching** for multi-turn LLM conversations
- `sulci/context.py` — new module with `ContextWindow` and `SessionStore`
  - `ContextWindow`: sliding window of turns per session with exponential
    decay blending (`lookup_vec = α·query + (1-α)·Σwᵢ·historyᵢ`)
  - `SessionStore`: concurrent session manager with TTL-based eviction
- `Cache` gains four new init parameters:
  - `context_window` — turns to remember per session (0 = stateless, default)
  - `query_weight` — current query weight vs blended history (default: 0.70)
  - `context_decay` — exponential decay per turn (default: 0.50)
  - `session_ttl` — idle session eviction in seconds (default: 3600)
- `cached_call()`, `get()`, `set()` now accept `session_id` parameter
- All results include `context_depth` field (0 = no context used)
- New context management methods: `get_context()`, `clear_context()`,
  `context_summary()`
- `sulci/__init__.py` now exports `ContextWindow` and `SessionStore`
- `examples/context_aware.py` — 4-demo walkthrough, no API key required
- `tests/test_context.py` — 27 tests covering ContextWindow, SessionStore,
  and Cache integration
- Updated `anthropic_example.py` with `session_id` and `Chat` wrapper

### Fixed

- `tests/test_core.py` — all `cache.get()` call sites updated to unpack
  3-tuple `(response, sim, context_depth)` instead of 2-tuple
- CI workflow updated to also run `test_context.py`

### Changed

- Version bumped to `0.2.0`
- `README.md` updated with context-awareness section and full API reference

### Backward compatibility

- `context_window=0` (default) is identical to v0.1.x behaviour
- No breaking changes — existing code requires zero modifications

---

## [0.1.1] — 2026-03-07

### Added

- Full library structure: `sulci/`, `backends/`, `embeddings/`
- Six vector backends: ChromaDB, Qdrant, FAISS, Redis, SQLite, Milvus
- Two embedding providers: MiniLM/MPNet/BGE (local), OpenAI API
- `Cache.cached_call()` — drop-in LLM wrapper
- `Cache.get()` / `set()` — manual cache control
- `Cache.stats()` — hit rate, cost savings tracking
- TTL-based cache expiry
- Per-user personalized caching via `user_id`
- GitHub Actions: auto-publish on tag, test matrix (Python 3.9–3.12, 3 OS)
- pytest suite: 20 core tests + backend contract tests
- Examples: `basic_usage.py`, `anthropic_example.py`

### Fixed

- `pyproject.toml` build backend changed from `setuptools.backends.legacy`
  to correct `setuptools.build_meta`
- Removed mandatory `numpy>=1.24` core dependency (now optional per backend)

---

## [0.1.0] — 2026-03-07

### Added

- Initial release — 6 backends, MiniLM, TTL, personalization, stats
