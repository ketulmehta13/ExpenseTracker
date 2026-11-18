// Signs the test account in through the real login form once, and saves the session for the
// signed-in tests. Also removes leftovers of an earlier interrupted run.
import { test as setup, expect } from '@playwright/test';
import { assertTestAccount, cleanup } from './db.js';

setup('sign in as the test account', async ({ page }) => {
    assertTestAccount();
    await cleanup();

    await page.goto('/login');
    await page.getByLabel('Email').fill(process.env.E2E_EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(process.env.E2E_PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);

    await page.context().storageState({ path: 'e2e/.auth/user.json' });
});
