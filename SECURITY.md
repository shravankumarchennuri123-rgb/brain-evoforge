# Security Policy

## Scope

BRAIN-EvoForge handles WorldQuant BRAIN credentials and may perform account-level write operations. Treat deployments as sensitive systems.

## Rules

- Never commit credentials, cookies, tokens, or private alpha records.
- Keep `.env`, cookie jars, local databases, logs, and account snapshots outside version control.
- Keep `WQ_WRITE_ARMED=false` during initial setup and development.
- Do not add automation intended to bypass authentication, identity verification, rate limits, or platform safeguards.
- Report security issues privately to the repository owner rather than opening a public issue with secrets or exploit details.
