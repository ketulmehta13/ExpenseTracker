// Transactions baseline: add/edit/delete with validation, search, filters, chips, counter,
// totals, pagination and CSV export.
import fs from 'node:fs';
import { test, expect } from '../fixtures.js';
import { seed, cleanup, categoryId, todayIST, money } from '../db.js';

const tag = `tx-${Date.now()}`;
const today = todayIST();

test.afterAll(cleanup);

const search = (page, text) => page.getByPlaceholder('Search title or category…').fill(text);
const counter = (page) => page.getByText(/^\d+ of \d+ transactions$/);
const openAdd = (page) => page.getByRole('button', { name: 'Add Transaction' }).first().click();
const modal = (page) => page.getByRole('dialog');

test('add form requires a title and a positive amount', async ({ page }) => {
    await page.goto('/dashboard/transactions');
    await openAdd(page);
    await expect(modal(page).getByRole('heading', { name: '+ Add Expense' })).toBeVisible();

    await modal(page).getByRole('button', { name: 'Save' }).click();
    await expect(modal(page).getByText('Title is required.')).toBeVisible();
    await expect(modal(page).getByText('Enter a valid positive amount.')).toBeVisible();

    await page.locator('#tx-title').fill(`E2E ${tag} invalid`);
    for (const bad of ['0', '-5']) {
        await page.locator('#tx-amount').fill(bad);
        await modal(page).getByRole('button', { name: 'Save' }).click();
        await expect(modal(page).getByText('Enter a valid positive amount.')).toBeVisible();
    }
    await modal(page).getByRole('button', { name: 'Cancel' }).click();
    await expect(modal(page)).toBeHidden();
});

test('add, edit and delete a transaction', async ({ page }) => {
    const title = `E2E ${tag} groceries`;
    await page.goto('/dashboard/transactions');

    // Add
    await openAdd(page);
    await page.locator('#tx-title').fill(title);
    await page.locator('#tx-amount').fill('345.67');
    await page.locator('#tx-category').selectOption({ label: 'Food' });
    await modal(page).getByRole('button', { name: 'Save' }).click();
    await expect(modal(page)).toBeHidden();
    await search(page, tag);
    const row = page.getByRole('row', { name: new RegExp(title) });
    await expect(row).toContainText('Food');
    await expect(row).toContainText('345.67');

    // Edit
    await page.getByRole('button', { name: `Edit ${title}` }).click();
    await expect(modal(page).getByRole('heading', { name: 'Edit Transaction' })).toBeVisible();
    await expect(page.locator('#tx-amount')).toHaveValue('345.67');
    await page.locator('#tx-title').fill(`${title} edited`);
    await page.locator('#tx-amount').fill('400');
    await modal(page).getByRole('button', { name: 'Update' }).click();
    await expect(modal(page)).toBeHidden();
    const edited = page.getByRole('row', { name: new RegExp(`${title} edited`) });
    await expect(edited).toContainText('400.00');

    // Delete, through the "cannot be undone" confirmation
    await page.getByRole('button', { name: `Delete ${title} edited` }).click();
    await expect(page.getByText(`"${title} edited" will be permanently removed. This action cannot be undone.`)).toBeVisible();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(page.getByText(`"${title} edited" deleted.`)).toBeVisible();
    await expect(edited).toHaveCount(0);
});

test.describe('with seeded data', () => {
    test.beforeAll(async () => {
        await cleanup();
        const food = await categoryId('Food');
        const travel = await categoryId('Travel');
        const rows = [
            { title: `${tag} cab`, amount: 250, type: 'EXPENSE', date: today, category_id: travel },
            { title: `${tag} bonus`, amount: 5000, type: 'INCOME', date: today, category_id: null },
            { title: `${tag} old dinner`, amount: 800, type: 'EXPENSE', date: `${Number(today.slice(0, 4)) - 2}-03-10`, category_id: food },
        ];
        // 30 small food rows today, for pagination (25 per page)
        for (let i = 1; i <= 30; i++) {
            rows.push({ title: `${tag} snack ${String(i).padStart(2, '0')}`, amount: 10, type: 'EXPENSE', date: today, category_id: food });
        }
        await seed(rows);
    });

    test('search narrows the list; the counter and totals cover the whole filtered set', async ({ page }) => {
        await page.goto('/dashboard/transactions');
        await search(page, tag);
        await expect(counter(page)).toHaveText(new RegExp(`^33 of \\d+ transactions$`));
        await expect(page.getByText('Page 1 of 2 · 33 results')).toBeVisible();
        const totals = page.getByText(/^Spent .*Earned /);
        await expect(totals).toBeVisible();
        const text = await totals.innerText();
        const [spent, earned] = text.split('·').map(money);
        expect(spent).toBeCloseTo(250 + 800 + 300, 2);
        expect(earned).toBeCloseTo(5000, 2);

        // 25 rows on page 1, 8 on page 2
        await expect(page.locator('tbody tr')).toHaveCount(25);
        await page.getByRole('button', { name: '2', exact: true }).click();
        await expect(page.locator('tbody tr')).toHaveCount(8);

        await search(page, `${tag} cab`);
        await expect(counter(page)).toHaveText(/^1 of \d+ transactions$/);
        // Search also matches the category name
        await search(page, 'travel');
        await expect(page.getByRole('row', { name: new RegExp(`${tag} cab`) })).toBeVisible();
    });

    test('type filter and period chips', async ({ page }) => {
        await page.goto('/dashboard/transactions');
        await search(page, tag);
        await page.getByRole('button', { name: 'Filters' }).click();
        await page.locator('select').filter({ has: page.locator('option[value="INCOME"]') }).selectOption('INCOME');
        await expect(counter(page)).toHaveText(/^1 of \d+ transactions$/);
        await page.locator('select').filter({ has: page.locator('option[value="INCOME"]') }).selectOption('');

        for (const chip of ['All time', 'This week', 'Last week', 'This month', 'Last month', 'This year']) {
            await expect(page.getByRole('button', { name: chip, exact: true })).toBeVisible();
        }
        await page.getByRole('button', { name: 'This month', exact: true }).click();
        await expect(counter(page)).toHaveText(/^32 of \d+ transactions$/); // the old dinner is excluded
        await page.getByRole('button', { name: 'All time', exact: true }).click();
        await expect(counter(page)).toHaveText(/^33 of \d+ transactions$/);

        // Custom From/To dates in the filter panel
        const year = Number(today.slice(0, 4)) - 2;
        await page.locator('input[type="date"]').first().fill(`${year}-03-01`);
        await page.locator('input[type="date"]').nth(1).fill(`${year}-03-31`);
        await expect(counter(page)).toHaveText(/^1 of \d+ transactions$/);
        await page.getByRole('button', { name: 'Clear' }).click();
    });

    test('category filter shows only that category', async ({ page }) => {
        // KNOWN BUG in the live app (found by this suite, not fixed yet): the filter compares the
        // dropdown's text value with the numeric category_id, so every category shows 0 results.
        // Remove this line once it is fixed; Playwright reports it if it starts passing.
        test.fail();
        await page.goto('/dashboard/transactions');
        await search(page, tag);
        await page.getByRole('button', { name: 'Filters' }).click();
        await page.locator('select').filter({ has: page.locator('option', { hasText: 'All categories' }) }).selectOption({ label: 'Travel' });
        await expect(counter(page)).toHaveText(/^1 of \d+ transactions$/);
        await expect(page.getByRole('row', { name: new RegExp(`${tag} cab`) })).toBeVisible();
    });

    test('CSV export downloads the filtered list', async ({ page }) => {
        await page.goto('/dashboard/transactions');
        await search(page, `${tag} cab`);
        // Export only once the list has loaded: before that the filtered list is empty
        await expect(counter(page)).toHaveText(/^1 of \d+ transactions$/);
        const [download] = await Promise.all([
            page.waitForEvent('download'),
            page.getByRole('button', { name: 'CSV' }).click(),
        ]);
        expect(download.suggestedFilename()).toBe('transactions.csv');
        const csv = fs.readFileSync(await download.path(), 'utf8').trimStart(); // also drops the byte-order mark
        const lines = csv.trim().split('\n');
        expect(lines[0]).toBe('Date,Title,Category,Type,Amount,Is Recurring');
        expect(lines).toHaveLength(2);
        expect(lines[1]).toContain(`"E2E ${tag} cab","Travel",EXPENSE,250`);
    });
});

test('a category suggestion still applies, and saving sends nothing to ml_feedback', async ({ page }) => {
    const food = await categoryId('Food');
    // Answer this test's category suggestion with "Food" (added last, so it runs before the fixture's route)
    await page.route('http://ml.e2e.invalid/v1/categorize', (route) => route.fulfill({
        status: 200,
        headers: { 'access-control-allow-origin': '*' },
        contentType: 'application/json',
        body: JSON.stringify({
            suggestion: { category_id: food, category_name: 'Food', label: 'food', confidence: 0.92, source: 'model' },
            model_version: 'e2e',
        }),
    }));
    const feedbackCalls = [];
    page.on('request', (r) => { if (r.url().includes('/rest/v1/ml_feedback')) feedbackCalls.push(r.url()); });

    const title = `E2E ${tag} masala chai`;
    await page.goto('/dashboard/transactions');
    await openAdd(page);
    await page.locator('#tx-title').fill(title);
    await page.locator('#tx-amount').fill('25');
    await expect(modal(page).getByText('tap to apply')).toBeVisible();
    await modal(page).getByRole('button', { name: 'Food' }).click();
    await expect(page.locator('#tx-category')).toHaveValue(String(food));
    await modal(page).getByRole('button', { name: 'Save' }).click();
    await expect(modal(page)).toBeHidden();
    await search(page, title);
    await expect(page.getByRole('row', { name: new RegExp(title) })).toContainText('Food');
    expect(feedbackCalls).toEqual([]);
});
