# Security checklist and threat model

## Controls

- [x] bcrypt password hashing and generic login failures
- [x] JWT expiry, role checks, inactive-user checks
- [x] Pydantic input validation and bounded text fields
- [x] SQLAlchemy parameterized queries
- [x] TLS at ingress and encrypted PostgreSQL/backup storage in deployment
- [x] Immutable audit events for auth, booking, doctor, and prescription mutations
- [x] Row locking and uniqueness for booking integrity
- [ ] MFA challenge enforcement for privileged production accounts
- [ ] KMS-managed JWT signing keys with rotation and key IDs
- [ ] Redis-backed distributed rate limiting and idempotency store
- [ ] Dependency and container scanning (Dependabot/Trivy)

## Threat model

Assets include identity data, consultation notes, prescriptions, and audit records. Attack surfaces are login, authenticated API routes, metrics, admin routes, CI dependencies, and database credentials. Primary threats are credential stuffing, token theft, IDOR between patients/doctors, double booking, injection, excessive data exposure, and denial of service.

Mitigations are short-lived tokens, bcrypt, MFA for privileged users, least-privilege RBAC, object-level ownership checks, parameterized ORM queries, request limits, rate limiting, TLS, secret managers, audit monitoring, dependency scanning, and alerting on authentication anomalies. Metrics must never contain PHI; application logs should use request IDs and resource IDs rather than notes or prescription content.

