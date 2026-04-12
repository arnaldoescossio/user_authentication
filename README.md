# Auth System — FastAPI + OAuth2 + JWT + Redis

Production-grade authentication and authorization API.

## Stack

| Layer | Library | Version |
|---|---|---|
| HTTP framework | FastAPI | 0.115.6 |
| ASGI server | Uvicorn | 0.32.1 |
| ORM | SQLAlchemy 2.0 (async) | 2.0.36 |
| Database | PostgreSQL via asyncpg | 0.30.0 |
| Migrations | Alembic | 1.14.0 |
| Token cache | Redis (async) | 5.2.1 |
| JWT | python-jose | 3.3.0 |
| Password hashing | bcrypt | 5.0.0 |
| Validation | Pydantic v2 | 2.10.3 |
| Settings | pydantic-settings | 2.7.0 |
| Python | CPython | ≥ 3.13 |

---

## Project Structure

```
auth_system/
├── app/
│   ├── main.py                          # App factory, middleware stack, lifespan
│   ├── core/
│   │   ├── config.py                    # Settings (pydantic-settings + .env)
│   │   ├── dependencies.py              # FastAPI DI — repo/service factories + auth guards
│   │   ├── exceptions.py                # Typed HTTP exceptions
│   │   ├── logging.py                   # JSON structured logging + request-id middleware
│   │   └── rate_limit.py                # Redis sliding-window rate limiter middleware
│   ├── domain/
│   │   ├── entities/user.py             # Pure Pydantic User entity (no ORM)
│   │   └── repositories/user_repository.py  # AbstractUserRepository (Port)
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── models.py                # SQLAlchemy 2.0 ORM model (Mapped[] columns)
│   │   │   ├── session.py               # Async engine + session factory + get_db()
│   │   │   └── user_repository.py       # SQLUserRepository (Adapter)
│   │   ├── cache/
│   │   │   └── token_cache.py           # Redis: refresh store + access denylist
│   │   └── security/
│   │       ├── jwt.py                   # JWTService — create/verify access + refresh
│   │       └── password.py              # bcrypt hash + verify
│   ├── services/
│   │   ├── auth_service.py              # register / login / refresh / logout / get_current_user
│   │   └── user_service.py              # profile / password change / email verify / pwd reset
│   └── api/v1/
│       ├── schemas.py                   # Pydantic request + response models
│       ├── router.py                    # Aggregates all v1 routers
│       └── endpoints/
│           ├── auth.py                  # /auth/* — register, login, refresh, logout, me
│           ├── users.py                 # /users/* — profile CRUD + admin ops
│           └── account.py              # /account/* — password change, forgot/reset, verify
├── alembic/
│   ├── env.py                           # Async-compatible Alembic environment
│   └── versions/0001_create_users.py   # Initial migration (users table + enums + trigger)
├── scripts/
│   └── seed_admin.py                    # Bootstrap first superadmin (idempotent)
├── tests/
│   ├── test_auth.py                     # Auth flows, JWT, password, AuthService
│   └── test_user_service.py             # UserService — profile, pwd change, verify, reset
├── docker-compose.yml                   # postgres + redis + api
├── Dockerfile
├── pyproject.toml
├── alembic.ini
└── requirements.txt
```

---

## Quick Start

### Docker Compose (recommended)

```bash
cp .env.example .env
# Edit SECRET_KEY in .env!
docker compose up --build
```

- API:       http://localhost:8000
- Swagger:   http://localhost:8000/docs
- ReDoc:     http://localhost:8000/redoc

### Local

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

### Seed first admin

```bash
python -m scripts.seed_admin \
  --email admin@example.com \
  --username admin \
  --password "Admin1234!" \
  --full-name "System Admin"
```

### Run migrations

```bash
alembic upgrade head
# After model changes:
alembic revision --autogenerate -m "describe change"
```

### Run tests

```bash
pytest tests/ -v
```

---

## API Reference

### Authentication `/api/v1/auth`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/register` | — | Register new account |
| POST | `/login` | — | Login (JSON body) |
| POST | `/login/form` | — | Login (OAuth2 form — Swagger UI) |
| POST | `/refresh` | — | Rotate token pair |
| POST | `/logout` | Bearer | Revoke tokens |
| GET  | `/me` | Bearer | Current user |

### Account `/api/v1/account`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/change-password` | Bearer | Change own password |
| POST | `/forgot-password` | — | Request reset token (email-safe) |
| POST | `/reset-password` | — | Confirm reset token + new password |
| POST | `/send-verification` | Bearer | Send email verification token |
| POST | `/verify-email` | — | Confirm verification token |

### Users `/api/v1/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET    | `/me` | Bearer | Own profile |
| PATCH  | `/me` | Bearer | Update own profile |
| GET    | `/{id}` | Admin | Get any user |
| PATCH  | `/{id}` | Admin | Update role / status |
| DELETE | `/{id}` | Admin | Delete user |

---

## Security Design

| Concern | Approach |
|---|---|
| Access tokens | Short-lived JWT (30 min). JTI added to Redis denylist on logout. |
| Refresh tokens | Stored in Redis by JTI. **Rotated on every use** — old JTI deleted immediately. |
| Password hashing | bcrypt, 12 rounds, random salt per hash. |
| Password reset | Opaque random token in Redis (1 hr TTL). Email-enumeration safe (always 200). |
| Email verification | Opaque random token in Redis (24 hr TTL). |
| Rate limiting | Redis sliding-window per IP per route (login: 10/min, register: 5/min). |
| Role guards | `require_roles(UserRole.ADMIN)` dependency factory — composable. |
| Structured logging | JSON logs with request-id propagated via `contextvars`. |
| Request tracing | `X-Request-ID` header on every response. |
