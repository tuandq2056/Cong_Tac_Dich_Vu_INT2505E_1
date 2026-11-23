# Services

Three FastAPI applications, one per bounded context. They share no Python code; they share
`contracts/`.

| Directory | Owns | Does not own |
|---|---|---|
| `identity/` | accounts, usernames, password login, Google identity, tokens | friendships, conversations, messages |
| `social/` | friend requests, friendships, conversations, members, permissions | message content, read-state, attachments |
| `chat/` | messages, `seq`, attachments, read-state, summaries, WebSocket | accounts, memberships |

## Conventions

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, pytest.
- `snake_case` JSON, UUID ids, RFC 3339 UTC timestamps.
- Each service has its own database and its own Alembic history.
- Configuration comes from environment variables; `.env` is local and never committed.
- The app factory is `create_app()` so tests can build it with a test database.
- `/healthz` returns 200 without touching another service.

## Commands (per service)

```bash
python -m pip install -e ".[dev]"
alembic upgrade head
pytest -q
uvicorn app.main:create_app --factory --reload
```

The real commands land with the first service; keep them identical across the three so CI needs one
job, not three.
