# Amrutam Telemedicine Backend

Production-oriented REST API for user lifecycle, doctor availability, consultations, prescriptions, audit trails, and operational metrics.

## Run locally

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

OpenAPI is available at `http://localhost:8000/docs`; metrics are at `/metrics`.

For the production-shaped stack:

```powershell
docker compose up --build
```

## API and security

- JWT access tokens with role-based authorization (`patient`, `doctor`, `admin`).
- Passwords are bcrypt-hashed; secrets are supplied via environment variables.
- Booking uses a database row lock and a unique slot constraint to prevent double booking.
- `Idempotency-Key` is required for booking and persisted with a unique `(user_id, key)` constraint so safe client retries return the original consultation.
- Pydantic validates request bodies and limits free-text sizes.
- Every security-sensitive mutation creates an audit record.
- Prometheus-compatible request metrics and structured request logs are exposed.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SECURITY.md](docs/SECURITY.md).
