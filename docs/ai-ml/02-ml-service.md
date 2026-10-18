# Step 2 — ML service foundation

**What it is:** a Python FastAPI service (`ml-service/`) that will host every ML feature. The React app calls it with the user's Supabase access token.

## Design decisions

### Why a separate Python service?
The ML ecosystem (scikit-learn, pandas, LangChain, LangGraph) is Python. Supabase Edge Functions run Deno/TypeScript and suit short glue code, not model inference. A separate service also scales and deploys independently of the frontend.

### Authentication: ask the auth server, then cache
Each request carries `Authorization: Bearer <access token>`. The service validates it by calling Supabase Auth (`GET /auth/v1/user`).

| Option | Pros | Cons |
|---|---|---|
| **Ask the auth server** (chosen) | Works with any signing method; notices revoked sessions | A network round trip per check |
| Verify the signature locally (JWKS) | No round trip | Needs asymmetric signing keys; a revoked session stays valid until it expires |

The round trip is amortised with a **TTL cache** keyed by a SHA-256 hash of the token, so raw tokens are never stored. Validated tokens are trusted for 60 seconds.

### Data access that keeps row level security
The service reads data through Supabase's REST API **with the user's token**, not an admin key, so Postgres RLS still decides what each user can see. A bug in the service can't leak another user's rows. That's the principle of least privilege.

### Pagination
PostgREST caps every response at a max-rows setting (1000 by default). The client asks for `Prefer: count=exact`, reads the total from the `Content-Range` header, and fetches pages until it has every row. That still works if the server's cap is lower than the client's page size, and it requires a unique final sort column (e.g. `date.desc,id.desc`) so pages don't overlap.

### Testability: the app factory and dependency injection
`create_app(settings, transport)` builds the app. Tests pass fake settings and an httpx `MockTransport` that simulates Supabase, so the suite runs in under a second with no network. FastAPI dependencies (`get_current_user`, `get_data`) keep endpoints free of auth plumbing.

### Operational basics
- One pooled `httpx.AsyncClient` per app lifetime (created in the lifespan hook), rather than a new connection per request.
- A middleware logs method, path, status and latency for every request. That becomes the basis for monitoring in step 9.
- The container runs as a non-root user and respects the host's `PORT`.

## Interview questions this step answers
- *How does your ML service authenticate users?* Bearer tokens validated by the identity provider, cached with a TTL; I can contrast that with local JWKS verification.
- *How do you stop a bug in the service from leaking other users' data?* Every query runs with the user's own token under database row level security.
- *How do you test code that calls external APIs?* Dependency injection plus a mock transport; no network in tests.
- *How do you paginate reliably?* An exact count plus a unique sort tiebreaker, and never trusting a single response to be complete.
