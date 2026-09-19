# BRAIN-EvoForge

A fail-closed, self-evolving WorldQuant BRAIN research orchestrator designed around live account discovery rather than hard-coded platform assumptions.

## What this project does

BRAIN-EvoForge maintains a durable state machine around the complete research lifecycle:

```text
LIVE ACCOUNT DISCOVERY
  -> account/schema snapshot
  -> candidate generation
  -> deterministic expression validation
  -> BRAIN simulation
  -> platform-authoritative quality checks
  -> self-correlation check
  -> guarded submission
  -> ACTIVE verification
  -> persistent learning
  -> mutation / crossover / exploration
  -> repeat
```

The target objective is **4 newly ACTIVE regular alphas + 1 newly ACTIVE SuperAlpha**. That is an application goal, not an assumed BRAIN quota.

## One-alpha live test

For the first end-to-end test:

```bash
# 1. Copy configuration and set only your own credentials.
cp .env.example .env

# 2. Keep writes OFF while testing authentication/discovery.
WQ_WRITE_ARMED=false wq-evoforge discover

# 3. Complete BRAIN/Persona verification through the normal official flow.
#    Then arm BOTH explicit write switches for exactly one test:
WQ_WRITE_ARMED=true WQ_ONE_ALPHA_WRITE_ARMED=true \
WQ_ALLOW_UNKNOWN_SUBMISSION_BUDGET=false wq-evoforge live-test-one
```

The one-alpha path is hard-bounded:

- one account/schema bootstrap
- one candidate
- one simulation
- at most one `POST /alphas/{id}/submit`
- polling only for that submission's terminal state
- process exits after the test

It does not start the 24/7 research loop.

The selected region/universe/delay comes from your account's discovered configuration rather than a random unsupported combination. If no usable profile can be inferred from the account, the test stops rather than inventing one.

If BRAIN requires Persona/face verification, complete it normally and rerun the command. EvoForge does not bypass identity verification.

By default, an unknown machine-readable submission budget blocks the write. Only set:

```bash
WQ_ALLOW_UNKNOWN_SUBMISSION_BUDGET=true
```

after you have independently confirmed the account's current operational submission allowance.

## Why this is different from the reference projects

The reference projects provide useful ingredients:

- `Miasyster/QuantGPT`: agent loop, mutation engine, knowledge base, WQ integration, anti-overfit concepts.
- `yli188/WorldQuant_alpha101_code`: reusable Alpha101 seed/formula bank.
- `zhutoutoutousan/worldquant-miner`: continuous orchestration, local LLMs, batch mining, state/decision tracking, mutation/bandit concepts.
- `QuantML-Research/wq-alpha-research`: self-evolution records, live alpha snapshots, PnL-based correlation analysis.
- `wh0amibjm/brainapi-go-sdk`: dynamic OPTIONS discovery, structured error taxonomy, daily budget modeling, long-polling, correlation endpoints.

EvoForge changes the critical control plane: **live discovery first, immutable safety gates, durable idempotent state, fail-closed ambiguity handling, and learning restricted to research policy—not platform safety or write logic.**

## Core safety properties

1. **No hard-coded submission threshold is treated as platform truth.** The platform's check results are read and evaluated.
2. **No cumulative-PnL correlation.** Correlation gates consume a platform correlation verdict; local research can store daily PnL later.
3. **No blind resubmission after restart.** The database stores pending state and the platform is re-probed before any write.
4. **No CAPTCHA/Persona bypass.** An interactive verification requirement pauses the service.
5. **No stealth browser or TLS impersonation.** The project uses ordinary HTTPS API access.
6. **LLM/research evolution cannot mutate write safety.** Gates are ordinary Python code outside the policy learner.
7. **Idempotent candidate fingerprints** prevent duplicate experiments in the local state machine.
8. **WAL SQLite** allows restart recovery and simple single-host deployment.
9. **Structured retries** honor `Retry-After` and stop after bounded retry budgets.
10. **SuperAlpha is schema-discovery gated.** The project never guesses a hidden SUPER request payload.

## Important platform distinction

Competition rules and account/API limits are different things. A public competition guideline is not evidence of an account-specific API quota, simulation limit, or permission. EvoForge therefore treats the user's live account response as authoritative for configuration, checks, permissions, and available operations.

Open-source BRAIN SDKs are implementation references rather than contractual platform guarantees. EvoForge re-discovers the live schema instead of treating repository constants as permanent truth.

## Installation

### Local / VPS

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
# edit .env
wq-evoforge discover
wq-evoforge once
```

Only after discovery succeeds and the dry-run path is understood:

```bash
WQ_WRITE_ARMED=true wq-evoforge run
```

### Docker

```bash
cp .env.example .env
# edit .env

docker compose build
docker compose run --rm brain-evoforge wq-evoforge discover
docker compose up -d
```

For a genuine 24/7 service, use an always-on VM/VPS or equivalent. Google Colab is not a reliable always-on production host.

## SuperAlpha

SuperAlpha is deliberately separated because its request schema and checks differ from regular alphas. The project discovers whether the account exposes the `SUPER` type and whether enough ACTIVE regular components exist. It then requires a user-provided live payload template via:

```text
WQ_SUPER_TEMPLATE_JSON=/secure/path/live_super_template.json
```

The template should be captured from the user's own account/environment, not guessed from a blog or repository. The adapter only replaces the selection/combo code fields and refuses to send anything when the schema is unclear.

## State machine

```text
CREATED
  -> STATIC_VALID -> SIM_DONE -> QUALITY_REJECTED
                               -> CORR_REJECTED
                               -> SUBMIT_PENDING -> ACTIVE
                                                 -> SUBMIT_REJECTED
```

Operational failures become `RETRYABLE` or `UNKNOWN`; `UNKNOWN` requires platform re-probing rather than speculative writes.

## Self-evolution

The learner is intentionally constrained:

- Strategy arms decide whether to explore window changes, operator changes, normalization changes, live-field substitutions, crossover, or new families.
- Rewards are bounded and stored in SQLite.
- A strategy can improve its future selection probability only through observed outcomes.
- The learner cannot change: write arming, account identity, credential handling, submission endpoint, correlation gate, or target completion checks.

This is the critical distinction between **self-evolving research** and **self-modifying infrastructure**.

## Live-account adaptation

On startup the system discovers:

- `/users/self`
- `/users/self/alphas` (all pages)
- `/users/self/competitions`
- `/users/self/activities/submissions`
- `/users/self/activities/simulations`
- `/operators`
- `OPTIONS /simulations`
- live data fields for the discovered region/universe/delay

It builds a hashed account snapshot. On future cycles, schema changes can invalidate prior assumptions and the next implementation stage should use those hashes as a revalidation trigger.

## What is not guaranteed

No software can guarantee zero defects against an external platform whose API, checks, permissions, scoring, quotas, schemas, or authentication flows can change without notice. EvoForge is designed so that uncertainty causes a pause or safe degradation rather than a fabricated success.

Before live write enablement, run the test suite and a read-only discovery pass. Never commit `.env` or credential files.
