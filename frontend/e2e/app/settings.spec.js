// Settings baseline: profile, password validation, monthly budget, currency, and the full
// CSV export (now on the Transactions page). Every value changed here is put back afterwards.
import fs from 'node:fs';
import { test, expect } from '../fixtures.js';
import { cleanup, getProfile, updateProfile, seed, todayIST, dbTotals } from '../db.js';

let original;

test.beforeAll(async () => {
    original = await getProfile();
    await cleanup();
    await seed([{ title: `settings-${Date.now()} tea`, amount: 20, type: 'EXPENSE', date: todayIST(), category_id: null }]);
});

test.afterAll(async () => {
    await updateProfile({ first_name: original.first_name, monthly_budget: original.monthly_budget });
    await cleanup();
});

test('all sections are present', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
    for (const name of ['Profile', 'Security', 'Preferences', 'Danger Zone']) {
        await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    }
    // The duplicate "Data & Exports" section was removed (task A3)
    await expect(page.getByRole('heading', { name: 'Data & Exports' })).toHaveCount(0);
    // The "Help improve category suggestions" opt-in was removed (task A2)
    await expect(page.getByText('Help improve category suggestions')).toHaveCount(0);
});

test('profile name saves and persists', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.locator('#first_name').fill('E2Etester');
    await page.getByRole('button', { name: 'Save Profile' }).click();
    await expect(page.getByText('Profile updated!')).toBeVisible();
    await page.reload();
    await expect(page.locator('#first_name')).toHaveValue('E2Etester');
    expect((await getProfile()).first_name).toBe('E2Etester');
});

test('password form validates length and match (no real change)', async ({ page }) => {
    let updateCalled = false;
    page.on('request', (r) => { if (r.url().includes('/auth/v1/user') && r.method() === 'PUT') updateCalled = true; });
    await page.goto('/dashboard/settings');
    await page.locator('#new_pw').fill('123');
    await page.locator('#confirm_pw').fill('456');
    await page.getByRole('button', { name: 'Update Password' }).click();
    await expect(page.getByText('Password must be at least 6 characters.')).toBeVisible();
    await expect(page.getByText('Passwords do not match.')).toBeVisible();
    expect(updateCalled).toBe(false);
});

test('monthly budget saves and persists', async ({ page }) => {
    await page.goto('/dashboard/settings');
    const budget = page.locator('input[type="number"][placeholder="0.00"]');
    await budget.fill('12345');
    await budget.press('Enter');
    await expect(page.getByText('Budget updated!')).toBeVisible();
    await page.reload();
    await expect(budget).toHaveValue('12345');
    expect(Number((await getProfile()).monthly_budget)).toBe(12345);
});

test('display currency changes only the symbol, and INR is the default', async ({ page }) => {
    await page.goto('/dashboard/settings');
    expect(await page.evaluate(() => localStorage.getItem('et-currency'))).toBeNull();
    await page.getByRole('button', { name: '$ US Dollar' }).click();
    await expect(page.getByText('Currency set to USD')).toBeVisible();
    await page.goto('/dashboard/transactions');
    await expect(page.getByText(/^Spent \$/)).toBeVisible();
    await page.goto('/dashboard/settings');
    await page.getByRole('button', { name: '₹ Indian Rupee' }).click();
    await page.goto('/dashboard/transactions');
    await expect(page.getByText(/^Spent ₹/)).toBeVisible();
});

// Settings' own "Export as CSV" was removed (task A3). The full export it gave is the
// Transactions page's CSV with no filters on "All time", which this checks.
test('full export: Transactions CSV with no filters has every transaction', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await expect(page.getByRole('button', { name: 'Export as CSV' })).toHaveCount(0);

    const { count } = await dbTotals();
    await page.goto('/dashboard/transactions');
    await expect(page.getByText(new RegExp(`^${count} of ${count} transactions$`))).toBeVisible();
    const [download] = await Promise.all([
        page.waitForEvent('download'),
        page.getByRole('button', { name: 'CSV' }).click(),
    ]);
    const csv = fs.readFileSync(await download.path(), 'utf8').trimStart(); // also drops the byte-order mark
    const lines = csv.trim().split('\n');
    expect(lines[0]).toBe('Date,Title,Category,Type,Amount,Is Recurring');
    expect(lines).toHaveLength(count + 1);
    expect(csv).toContain('tea"');
});
