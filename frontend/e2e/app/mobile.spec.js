// At the phone width (618 px) the mobile layout is used: card list instead of the table.
import { test, expect } from '../fixtures.js';
import { seed, cleanup, todayIST } from '../db.js';

const tag = `mob-${Date.now()}`;

test.beforeAll(async () => {
    await cleanup();
    await seed([{ title: `${tag} juice`, amount: 60, type: 'EXPENSE', date: todayIST(), category_id: null }]);
});
test.afterAll(cleanup);

test('Transactions shows cards with one visible Edit and Delete per row', async ({ page }) => {
    await page.goto('/dashboard/transactions');
    await page.getByPlaceholder('Search title or category…').fill(tag);
    await expect(page.locator('table')).toBeHidden();
    await expect(page.getByText(`E2E ${tag} juice`).filter({ visible: true })).toHaveCount(1);
    await expect(page.getByRole('button', { name: `Edit E2E ${tag} juice` })).toHaveCount(1);
    await expect(page.getByRole('button', { name: `Delete E2E ${tag} juice` })).toHaveCount(1);
});

test('pages fit the width without horizontal scrolling', async ({ page }) => {
    for (const path of ['/dashboard', '/dashboard/transactions', '/dashboard/analytics', '/dashboard/settings']) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, path).toBeLessThanOrEqual(0);
    }
});
