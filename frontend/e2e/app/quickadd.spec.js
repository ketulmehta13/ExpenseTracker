// Quick Add baseline: the parsed amount, date, title and type pre-fill the form, and a
// suggested category is selected when its name matches one of the user's categories.
// The ML service's reply is faked (fixtures.js), so this checks the app's side only. Nothing is saved.
import { test, expect, parseReplies } from '../fixtures.js';
import { categoryId, todayIST } from '../db.js';

const draft = (overrides) => ({
    title: 'chai', amount: 20, date: todayIST(), type: 'EXPENSE',
    found: { amount: true, date: false, type: false }, llm_filled: [], suggestion: null, model_version: null,
    ...overrides,
});

const submit = async (page, text) => {
    await page.goto('/dashboard');
    const input = page.getByPlaceholder('Try: "spent 450 on groceries yesterday"');
    await input.fill(text);
    await input.press('Enter');
};

test('parsed amount, date, title and type pre-fill the form', async ({ page }) => {
    parseReplies.next = draft({ title: 'Salary', amount: 20000, type: 'INCOME', date: '2026-01-05' });
    await submit(page, 'received 20000 salary on 5 jan');
    await expect(page.getByRole('dialog').getByRole('heading', { name: '+ Add Income' })).toBeVisible();
    await expect(page.locator('#tx-title')).toHaveValue('Salary');
    await expect(page.locator('#tx-amount')).toHaveValue('20000');
    await expect(page.locator('#tx-date')).toHaveValue('2026-01-05');
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
});

test('a suggestion whose name matches a category is preselected', async ({ page }) => {
    const food = await categoryId('Food');
    parseReplies.next = draft({
        title: 'groceries', amount: 450,
        suggestion: { category_id: food, category_name: 'Food', label: 'food', confidence: 0.9, source: 'model' },
    });
    await submit(page, 'spent 450 on groceries');
    await expect(page.locator('#tx-amount')).toHaveValue('450');
    await expect(page.locator('#tx-date')).toHaveValue(todayIST());
    await expect(page.locator('#tx-category')).toHaveValue(String(food));
});

test('without a suggestion no category is selected (current behaviour)', async ({ page }) => {
    parseReplies.next = draft();
    await submit(page, 'chai 20');
    await expect(page.locator('#tx-title')).toHaveValue('chai');
    await expect(page.locator('#tx-amount')).toHaveValue('20');
    await expect(page.locator('#tx-category')).toHaveValue('');
});
