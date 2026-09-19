# Reference-project audit and EvoForge design decisions

## Executive finding

The four requested repositories are useful as research components, but none is sufficient as-is for a high-reliability account-aware control plane. The common weakness is assumption drift: hard-coded thresholds, settings, API behavior, concurrency, or local state are treated as if they were permanent platform truth.

EvoForge therefore uses the platform as the authority for account state and deterministic checks, while keeping research evolution behind a separate policy layer.

## Repository audit

| Reference | Strengths reused | Gaps corrected in EvoForge |
|---|---|---|
| `Miasyster/QuantGPT` | Agentic factor loop; parser; mutation/crossover; anti-overfit; persistent reports; BRAIN client | Static thresholds; fixed simulation profile; LLM can influence too much of the control loop; some timeout/retry semantics are permissive; self-modification is not isolated from write safety |
| `yli188/WorldQuant_alpha101_code` | Formulaic Alpha 101 seed bank; direct price/volume formulas; local factor implementations | Legacy/foreign backtest semantics; not BRAIN-schema aware; not sufficient for live account settings or modern data fields |
| `zhutoutoutousan/worldquant-miner` | Continuous orchestration; Docker; LLM generation; multi-arm bandit; genetic search; template validation; decision recording | Multiple generations/branches increase drift; subprocess/log-based coordination is more fragile than a transactional state machine; batch/concurrency assumptions can be stale; not enough separation between learned behavior and safety-critical writes |
| `QuantML-Research/wq-alpha-research` | Live alpha inventory; PnL correlation; self-evolution records; dynamic field catalog; failure/lesson capture | Thresholds are empirical/static; PnL date alignment is incomplete; skill-file updates need human judgment; no durable transactional submission state or live budget authority |
| `wh0amibjm/brainapi-go-sdk` (additional reference) | Dynamic `OPTIONS`; typed errors; long-polling; daily budget abstraction; correlation endpoints; restart-safe patterns | Go SDK is not our application; its platform observations remain community-derived; EvoForge avoids TLS impersonation/CAPTCHA logic and keeps a smaller Python dependency surface |

## Workflow audit

### Reference workflow pattern

```text
LLM/template generation
 -> local validation
 -> simulation
 -> metric filter
 -> mutation/retry
 -> submit
 -> local log/knowledge update
```

### EvoForge workflow

```text
Account + schema discovery
 -> live profile selection
 -> candidate generation
 -> deterministic syntax/security checks
 -> idempotent DB insert
 -> bounded BRAIN simulation
 -> wait using server hints
 -> fetch authoritative alpha metrics
 -> GET /check
 -> pre-submit correlation
 -> budget/permission/write gate
 -> POST /submit
 -> GET /submit until terminal
 -> ACTIVE verification
 -> reward + policy update
 -> schema/health refresh
 -> repeat
```

The extra control-plane steps are intentional: they reduce the probability of duplicate submissions, false success, stale assumptions, and accidental writes after a restart.

## Critical traps addressed

### 1. `201 Created` is not the same as `ACTIVE`

A submission request can be accepted while final checks are still pending. EvoForge only increments the target after an explicit ACTIVE result.

### 2. Cumulative PnL correlation is not a valid duplicate test

The research layer should align dates and difference cumulative PnL into daily changes before correlation. For platform-gating, EvoForge prefers BRAIN's own correlation endpoint/check.

### 3. Hard-coded Sharpe/Fitness gates are unsafe

A static threshold copied from one repository may belong to a particular account, stage, universe, or date. EvoForge treats platform check results and limits as authoritative; static thresholds are only research priors.

### 4. API rate limits and concurrent simulation limits are not constants

EvoForge respects `Retry-After`, uses bounded concurrency, and backs off on 429/503. It does not encode a consultant/non-consultant maximum as universal truth.

### 5. Schema drift

Operators, data fields, simulation settings, checks, and response JSON can change. EvoForge snapshots hashes and periodically re-runs discovery. A future extension should invalidate/re-score candidates when the live schema hash changes.

### 6. Restart races

A process can die after submitting but before recording success. EvoForge stores `SUBMIT_PENDING`, then re-reads the platform before deciding whether another write is needed.

### 7. Authentication challenges

Persona/verification is an explicit pause state. No automated bypass is implemented.

### 8. Self-modifying safety code

The learning system may modify research strategy selection, not credential handling, write permissions, correlation gates, or network endpoints.

## Account-target model

The application's target is:

```text
mission_regular_target = 4
mission_super_target   = 1
```

These are **our mission counts**, not a claim about a WorldQuant platform quota. The mission survives restarts and does not reset at local or BRAIN-day rollover.

Daily platform activity is observed separately. When a machine-readable remaining budget is unavailable, EvoForge fails closed by default.

## SuperAlpha design

SuperAlpha is a separate lane because its type and checks differ from regular alphas. EvoForge follows this order:

1. Discover whether `SUPER` is exposed by the account's live simulation schema.
2. Require enough ACTIVE components for the chosen account-native selection construction.
3. Prefer cloning the shape of an existing SUPER alpha in the same account.
4. Otherwise require a captured account-native JSON template.
5. Never invent a hidden payload schema.
6. Run the normal deterministic checks plus SuperAlpha-specific checks.
7. Count completion only after ACTIVE verification.

## What the reference audit does not prove

Open-source repositories demonstrate possible implementations, not contractual guarantees of current BRAIN behavior. Official WorldQuant rules and the user's actual account responses remain the authority for eligibility, limits, permissions, and competition behavior.
