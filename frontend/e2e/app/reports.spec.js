// Reports baseline, and the totals check: database = Transactions = Reports = Dashboard "All time".
import { test, expect } from '../fixtures.js';
import { seed, cleanup, categoryId, todayIST, money, dbTotals } from '../db.js';

const tag = `rep-${Date.now()}`;

test.beforeAll(async () => {
    await cleanup();
    const food = await categoryId('Food');
    const rent = await categoryId('Rent');
    const today = todayIST();
    await seed([
        { title: `${tag} rent`, amount: 15000, type: 'EXPENSE', date: today, category_id: rent },
        { title: `${tag} pizza`, amount: 649.99, type: 'EXPENSE', date: today, category_id: food },
        { title: `${tag} pay`, amount: 60000, type: 'INCOME', date: today, category_id: null },
    ]);
});

test.afterAll(cleanup);

const tile = (page, label) => page.locator('div.rounded-2xl', { has: page.locator('p', { hasText: new RegExp(`^${label}$`) }) }).first();

test('Reports shows totals, spending over time, by category and top expenses', async ({ page }) => {
    await page.goto('/dashboard/analytics');
    await expect(page.getByRole('heading', { name: 'Reports', level: 1 })).toBeVisible();
    for (const label of ['Total Income', 'Total Expenses', 'Net Savings']) await expect(tile(page, label)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Spending Over Time' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'By Category' })).toBeVisible();
    const top = page.locator('div.rounded-2xl', { has: page.getByRole('heading', { name: 'Top Expenses' }) });
    await expect(top.getByText(`E2E ${tag} rent`)).toBeVisible();
});

test('totals reconcile: database = Transactions = Reports = Dashboard (All time)', async ({ page }) => {
    const db = await dbTotals();

    await page.goto('/dashboard/transactions');
    const totals = page.getByText(/^Spent .*Earned /);
    await expect(page.getByText(new RegExp(`^${db.count} of ${db.count} transactions$`))).toBeVisible();
    const [txSpent, txEarned] = (await totals.innerText()).split('·').map(money);

    await page.goto('/dashboard/analytics');
    await expect(tile(page, 'Total Income')).toBeVisible();
    const repIncome = money(await tile(page, 'Total Income').locator('p').nth(1).innerText());
    const repExpense = money(await tile(page, 'Total Expenses').locator('p').nth(1).innerText());

    await page.goto('/dashboard');
    await page.getByRole('button', { name: 'All time', exact: true }).click();
    const dashCard = (label) => page.locator('div.rounded-2xl', { has: page.locator('p', { hasText: new RegExp(`^${label}$`) }) }).first();
    await expect(dashCard('Income')).toContainText('All time');
    const dashIncome = money(await dashCard('Income').locator('p.text-2xl').innerText());
    const dashExpense = money(await dashCard('Expenses').locator('p.text-2xl').innerText());

    for (const value of [txEarned, repIncome, dashIncome]) expect(value).toBeCloseTo(db.income, 2);
    for (const value of [txSpent, repExpense, dashExpense]) expect(value).toBeCloseTo(db.expense, 2);
});
