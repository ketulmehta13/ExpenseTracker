// Pages that work without signing in. Nothing here creates an account or writes data.
import { test, expect } from '@playwright/test';

test('home page loads, and its buttons lead to sign-in and sign-up', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Get Started Free' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'I have an account' })).toBeVisible();
    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page).toHaveURL(/\/login$/);
});

test('signed-out visitors are sent from the dashboard to the login page', async ({ page }) => {
    for (const path of ['/dashboard', '/dashboard/transactions', '/dashboard/analytics', '/dashboard/settings']) {
        await page.goto(path);
        await expect(page).toHaveURL(/\/login$/);
    }
});

test('login page shows the form, and wrong credentials show an error', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await page.getByLabel('Email').fill('nobody-e2e@example.invalid');
    await page.getByLabel('Password', { exact: true }).fill('wrong-password-123');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.locator('[data-sonner-toast][data-type="error"]')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
});

test('sign-up validates username, email and password before calling the server', async ({ page }) => {
    let signupCalled = false;
    page.on('request', (r) => { if (r.url().includes('/auth/v1/signup')) signupCalled = true; });
    await page.goto('/register');
    await expect(page.getByRole('heading', { name: 'Create account' })).toBeVisible();

    await page.getByLabel('Username').fill('a');
    await page.getByLabel('Email').fill('not-an-email');
    await page.locator('#reg-password').fill('123');
    await page.getByRole('button', { name: 'Create account' }).click();

    await expect(page.getByText('Username must be 3-20 chars (letters, numbers, @.+_-)')).toBeVisible();
    await expect(page.getByText('Enter a valid email address')).toBeVisible();
    await expect(page.getByText('Password must be at least 6 characters')).toBeVisible();
    expect(signupCalled).toBe(false);
});

test('forgot-password and 404 pages render', async ({ page }) => {
    await page.goto('/forgot-password');
    await expect(page.getByText("Enter your email and we'll send you a reset link.")).toBeVisible();
    await page.goto('/no-such-page-e2e');
    await expect(page.getByText(/404|not found/i).first()).toBeVisible();
});
