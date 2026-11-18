// Dashboard baseline: income/expense/net cards, date-range chips, 6-month chart, recent activity.
import { test, expect } from '../fixtures.js';
import { seed, cleanup, categoryId, todayIST, money } from '../db.js';

const tag = `dash-${Date.now()}`;

test.beforeAll(async () => {
    await cleanup();
    const food = await categoryId('Food');
    const salary = await categoryId('Salary');
    const today = todayIST();
    await seed([
        { title: `${tag} salary`, amount: 50000, type: 'INCOME', date: today, category_id: salary },
        { title: `${tag} lunch`, amount: 1200.5, type: 'EXPENSE', date: today, category_id: food },
        // Two years ago: only in "All time"
        { title: `${tag} old`, amount: 999, type: 'EXPENSE', date: `${Number(today.slice(0, 4)) - 2}-01-15`, category_id: food },
    ]);
});

test.afterAll(cleanup);

const card = (page, label) => page.locator('div.rounded-2xl', { has: page.locator('p', { hasText: new RegExp(`^${label}$`) }) }).first();
const cardValue = async (page, label) => money(await card(page, label).locator('p.text-2xl').innerText());

test('shows greeting, the three summary cards and the six range chips', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);
    for (const label of ['Income', 'Expenses', 'Net balance']) await expect(card(page, label)).toBeVisible();
    for (const chip of ['This week', 'This month', 'Last month', 'Last 30 days', 'This year', 'All time']) {
        await expect(page.getByRole('button', { name: chip, exact: true })).toBeVisible();
    }
    // "This month" is the default range
    await expect(card(page, 'Income')).toContainText('This month');
});

test('cards add up for "This month" and change with the chips', async ({ page }) => {
    await page.goto('/dashboard');
    const income = await cardValue(page, 'Income');
    const expense = await cardValue(page, 'Expenses');
    const net = await cardValue(page, 'Net balance');
    expect(income).toBeGreaterThanOrEqual(50000);
    expect(expense).toBeGreaterThanOrEqual(1200.5);
    expect(net).toBeCloseTo(income - expense, 2);

    // The two-year-old expense appears only under "All time"
    await page.getByRole('button', { name: 'All time', exact: true }).click();
    await expect(card(page, 'Expenses')).toContainText('All time');
    expect(await cardValue(page, 'Expenses')).toBeCloseTo(expense + 999, 2);
});

test('6-month chart, recent activity and category breakdown render', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByText('Income vs Expenses')).toBeVisible();
    await expect(page.getByText('Last 6 months')).toBeVisible();
    await expect(page.locator('.recharts-bar-rectangle').first()).toBeVisible();

    const recent = page.locator('div.rounded-2xl', { has: page.getByRole('heading', { name: 'Recent Activity' }) });
    await expect(recent.getByText(`E2E ${tag} lunch`)).toBeVisible();
    await expect(recent.getByText(`E2E ${tag} salary`)).toBeVisible();

    await expect(page.getByText('Expense Breakdown')).toBeVisible();
});
