# Contributing

## Workflow

1. Branch from `main`: `feature/<name>`, `fix/<name>` or `chore/<name>`.
2. Make small, focused commits in Conventional Commit style: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`.
3. Push the branch. CI runs on every push: frontend lint and build, Edge Function type check, migration tests, and ML service tests.
4. Open a pull request into `main` using the template, and merge only when CI is green.
5. `main` deploys the frontend to production on Vercel. Apply migrations and deploy Edge Functions **before** merging frontend code that depends on them.

## Definition of done

- Lint, build and tests pass locally and in CI.
- New behaviour has tests: pytest for `ml-service/`, the PGlite suites in `supabase/tests/` for SQL.
- ML features record their evaluation metric in their doc under `docs/ai-ml/`.
- Secrets never land in git. `.env*` files are ignored; `.env.example` lists the variable names.

## Local setup

| Part | Commands |
|---|---|
| Frontend | `cd frontend && npm install && npm run dev` |
| ML service | see `ml-service/README.md` |
| Migration tests | `cd supabase/tests && npm install && npm test` |
| Edge Functions | `deno check supabase/functions/*/index.ts` |
