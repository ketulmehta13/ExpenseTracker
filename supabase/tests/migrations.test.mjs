// Applies the repo's Supabase migrations to an in-memory Postgres (PGlite) with
// minimal Supabase stand-ins, reproduces the Phase 0 bugs, then checks the fixes.
// Usage: node migrations.test.mjs <repo-root>
import { PGlite } from '@electric-sql/pglite';
import { uuid_ossp } from '@electric-sql/pglite/contrib/uuid_ossp';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const repo = process.argv[2];
const migration = (name) => readFileSync(`${repo}/supabase/migrations/${name}`, 'utf8');
const db = new PGlite({ extensions: { uuid_ossp } });

const USER_A = '11111111-1111-1111-1111-111111111111';
const USER_B = '22222222-2222-2222-2222-222222222222';
const USER_C = '33333333-3333-3333-3333-333333333333';

let passed = 0;
const check = async (name, fn) => {
  await fn();
  passed += 1;
  console.log(`  ok  ${name}`);
};

const asRole = async (role, sub, fn) => {
  await db.exec(`SET ROLE ${role}`);
  await db.query(`SELECT set_config('request.jwt.claim.sub', $1, false)`, [sub ?? '']);
  try {
    return await fn();
  } finally {
    await db.exec('RESET ROLE');
    await db.query(`SELECT set_config('request.jwt.claim.sub', '', false)`);
  }
};

const seedDefaults = () => {
  const sql = migration('20260816000000_production_hardening.sql');
  return sql.slice(sql.indexOf('INSERT INTO public.categories (name, color, icon, user_id)'));
};

const addUser = (id, email, username) =>
  db.query(`INSERT INTO auth.users (id, email, raw_user_meta_data) VALUES ($1, $2, $3)`, [
    id,
    email,
    JSON.stringify(username ? { username } : {}),
  ]);

// ── Supabase stand-ins ──────────────────────────────────────────────────────
await db.exec(`
  CREATE ROLE anon NOLOGIN;
  CREATE ROLE authenticated NOLOGIN;
  CREATE ROLE service_role NOLOGIN BYPASSRLS;
  CREATE SCHEMA auth;
  CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb DEFAULT '{}'::jsonb);
  CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
  CREATE PUBLICATION supabase_realtime;
`);

await db.exec(migration('20260816000000_production_hardening.sql'));
await db.exec(migration('20260818000001_ai_tables.sql'));
await db.exec(migration('20260819000001_subscriptions.sql'));
await addUser(USER_A, 'alice@example.com', 'alice');
await addUser(USER_B, 'bob@example.com', 'bob');

console.log('Before the Phase 0 migration (bugs reproduce):');

await check('re-running the seed duplicates global categories', async () => {
  await db.exec(seedDefaults());
  const { rows } = await db.query(`SELECT count(*)::int AS n FROM categories WHERE user_id IS NULL`);
  assert.equal(rows[0].n, 20);
});

// A transaction pointing at the newer duplicate must survive the merge.
const { rows: dupeRows } = await db.query(
  `SELECT id FROM categories WHERE name = 'Groceries' AND user_id IS NULL ORDER BY created_at DESC, id DESC LIMIT 1`,
);
await db.query(
  `INSERT INTO transactions (user_id, category_id, title, amount, type) VALUES ($1, $2, 'Milk', 60, 'EXPENSE')`,
  [USER_A, dupeRows[0].id],
);

await check('creating a category without user_id is rejected by RLS', async () => {
  await asRole('authenticated', USER_A, () =>
    assert.rejects(db.query(`INSERT INTO categories (name) VALUES ('Coffee')`), /row-level security/),
  );
});

await check('a username collision aborts signup', async () => {
  await assert.rejects(addUser(USER_C, 'carol@example.com', 'alice'), /duplicate key/);
});

await check('any user can read another user\'s plan via get_user_plan', async () => {
  const rows = await asRole('authenticated', USER_A, async () =>
    (await db.query(`SELECT * FROM get_user_plan($1)`, [USER_B])).rows,
  );
  assert.equal(rows.length, 1);
});

// ── Apply the fix (twice: it must be re-runnable) ───────────────────────────
await db.exec(migration('20261017000000_phase0_fixes.sql'));
await db.exec(migration('20261017000000_phase0_fixes.sql'));

console.log('After the Phase 0 migration:');

await check('duplicate global categories are merged into the oldest row', async () => {
  const { rows } = await db.query(
    `SELECT count(*)::int AS n, count(DISTINCT name)::int AS names FROM categories WHERE user_id IS NULL`,
  );
  assert.deepEqual(rows[0], { n: 10, names: 10 });
});

await check('transactions on a removed duplicate now point at the kept category', async () => {
  const { rows } = await db.query(
    `SELECT c.name, c.user_id FROM transactions t JOIN categories c ON c.id = t.category_id WHERE t.title = 'Milk'`,
  );
  assert.deepEqual(rows[0], { name: 'Groceries', user_id: null });
});

await check('re-running the seed is now a no-op', async () => {
  await db.exec(seedDefaults());
  const { rows } = await db.query(`SELECT count(*)::int AS n FROM categories WHERE user_id IS NULL`);
  assert.equal(rows[0].n, 10);
});

await check('creating a category without user_id defaults to the caller', async () => {
  const rows = await asRole('authenticated', USER_A, async () =>
    (await db.query(`INSERT INTO categories (name) VALUES ('Coffee') RETURNING user_id`)).rows,
  );
  assert.equal(rows[0].user_id, USER_A);
});

await check('a user cannot create a category for someone else', async () => {
  await asRole('authenticated', USER_A, () =>
    assert.rejects(
      db.query(`INSERT INTO categories (name, user_id) VALUES ('Sneaky', $1)`, [USER_B]),
      /row-level security/,
    ),
  );
});

await check('is_username_available works for anonymous visitors', async () => {
  const rows = await asRole('anon', null, async () =>
    (await db.query(`SELECT is_username_available('Alice ') AS taken, is_username_available('newbie') AS free`)).rows,
  );
  assert.deepEqual(rows[0], { taken: false, free: true });
});

await check('a username collision no longer aborts signup (suffix fallback)', async () => {
  await addUser(USER_C, 'carol@example.com', 'alice');
  const { rows } = await db.query(`SELECT username FROM profiles WHERE id = $1`, [USER_C]);
  assert.match(rows[0].username, /^alice_[0-9a-f]{6}$/);
  const { rows: subs } = await db.query(`SELECT plan FROM subscriptions WHERE user_id = $1`, [USER_C]);
  assert.equal(subs[0].plan, 'free');
});

const planFor = async (fields) => {
  await db.query(
    `UPDATE subscriptions SET plan = $2, status = $3, current_period_end = $4, grace_period_end = $5,
            cancel_at_period_end = $6 WHERE user_id = $1`,
    [USER_A, fields.plan, fields.status, fields.periodEnd ?? null, fields.graceEnd ?? null, fields.cancelAtPeriodEnd ?? false],
  );
  const rows = await asRole('service_role', null, async () =>
    (await db.query(`SELECT * FROM get_user_plan($1)`, [USER_A])).rows,
  );
  return rows[0];
};
const inDays = (days) => new Date(Date.now() + days * 86400000).toISOString();

await check('get_user_plan: trialing and active are Pro', async () => {
  assert.equal((await planFor({ plan: 'pro_monthly', status: 'trialing', periodEnd: inDays(7) })).is_pro, true);
  assert.equal((await planFor({ plan: 'pro_yearly', status: 'active', periodEnd: inDays(300) })).is_pro, true);
});

await check('get_user_plan: scheduled cancellation keeps Pro and reports the flag', async () => {
  const plan = await planFor({ plan: 'pro_monthly', status: 'active', periodEnd: inDays(10), cancelAtPeriodEnd: true });
  assert.equal(plan.is_pro, true);
  assert.equal(plan.cancel_at_period_end, true);
});

await check('get_user_plan: canceled keeps Pro only until the period ends', async () => {
  assert.equal((await planFor({ plan: 'pro_monthly', status: 'canceled', periodEnd: inDays(5) })).is_pro, true);
  assert.equal((await planFor({ plan: 'pro_monthly', status: 'canceled', periodEnd: inDays(-1) })).is_pro, false);
});

await check('get_user_plan: past_due is Pro only inside the grace period (never NULL)', async () => {
  assert.equal((await planFor({ plan: 'pro_monthly', status: 'past_due', graceEnd: inDays(2) })).is_pro, true);
  assert.equal((await planFor({ plan: 'pro_monthly', status: 'past_due', graceEnd: null })).is_pro, false);
  assert.equal((await planFor({ plan: 'pro_monthly', status: 'pending' })).is_pro, false);
});

await check('get_user_plan is no longer callable by users', async () => {
  for (const role of ['authenticated', 'anon']) {
    await asRole(role, USER_A, () =>
      assert.rejects(db.query(`SELECT * FROM get_user_plan($1)`, [USER_B]), /permission denied/),
    );
  }
});

await check('subscriptions is part of the realtime publication', async () => {
  const { rows } = await db.query(
    `SELECT 1 FROM pg_publication_tables WHERE pubname = 'supabase_realtime' AND tablename = 'subscriptions'`,
  );
  assert.equal(rows.length, 1);
});

await check('users still only see their own subscription row', async () => {
  const rows = await asRole('authenticated', USER_B, async () =>
    (await db.query(`SELECT user_id FROM subscriptions`)).rows,
  );
  assert.deepEqual(rows.map((r) => r.user_id), [USER_B]);
});

await check('deleting the auth user removes every row the user owns (delete-account relies on it)', async () => {
  await db.query(`INSERT INTO categories (name, user_id) VALUES ('Bob only', $1)`, [USER_B]);
  await db.query(`INSERT INTO transactions (user_id, title, amount, type) VALUES ($1, 'Bob tx', 5, 'EXPENSE')`, [USER_B]);
  await db.query(`INSERT INTO ai_rate_limits (user_id, call_count) VALUES ($1, 3)`, [USER_B]);
  await db.query(`INSERT INTO ai_usage_log (user_id, feature) VALUES ($1, 'categorize')`, [USER_B]);
  await db.query(`INSERT INTO ai_insights (user_id, month, insight) VALUES ($1, '2026-10', 'x')`, [USER_B]);
  await db.query(`DELETE FROM auth.users WHERE id = $1`, [USER_B]);
  const owned = [['profiles', 'id'], ['categories', 'user_id'], ['transactions', 'user_id'], ['subscriptions', 'user_id'],
    ['ai_rate_limits', 'user_id'], ['ai_usage_log', 'user_id'], ['ai_insights', 'user_id']];
  for (const [table, col] of owned) {
    const { rows } = await db.query(`SELECT count(*)::int AS n FROM ${table} WHERE ${col} = $1`, [USER_B]);
    assert.equal(rows[0].n, 0, `${table} still has rows`);
  }
});

console.log(`\n${passed} checks passed`);
