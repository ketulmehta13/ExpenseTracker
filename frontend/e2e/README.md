# End-to-end tests (Playwright)

The regression guard for the live app's main flows: sign-in, Dashboard, add/edit/delete,
search and filters, Reports, Settings, Quick Add, the 618 px mobile layout, and totals that
agree between the database, Transactions, Reports and Dashboard.

## Setup (once)

1. Create a **dedicated test account** on the site. Its email must contain `e2e` or `test`,
   otherwise the suite refuses to run (a guard against using a real account).
2. Create `frontend/.env.e2e.local` (git-ignored, never commit it):

   ```
   E2E_EMAIL=your-e2e-account@example.com
   E2E_PASSWORD=...
   ```

3. `npm install` and `npx playwright install chromium`.

## Run

```
npm run test:e2e          # everything
npm run test:e2e:public   # only the signed-out pages (no account needed)
```

To use the Google Chrome already installed instead of Playwright's Chromium (whose download
stalled on this PC), set `E2E_CHANNEL=chrome`, e.g. in Git Bash: `E2E_CHANNEL=chrome npm run test:e2e`.

The suite starts its own dev server on port 5181. It talks to the Supabase project in
`.env.local`, as the test account only. Every row it creates has a title starting with
`E2E `, and those rows are deleted at the end of the run (also after failures). Profile
name and budget are put back. The ML service is not called: its replies are faked in the
browser (`fixtures.js`), so Quick Add tests check the app's side of the flow.
