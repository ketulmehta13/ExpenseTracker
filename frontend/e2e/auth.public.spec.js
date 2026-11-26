// Email-code confirmation and Google sign-in. Supabase Auth's answers are faked with page.route,
// so no email is sent, no account is created and Google is never contacted.
import { test, expect } from '@playwright/test';

const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) });
const unconfirmedUser = (email) => ({
    id: '00000000-0000-4000-8000-00000000e2e0',
    aud: 'authenticated',
    role: 'authenticated',
    email,
    confirmation_sent_at: new Date().toISOString(),
    app_metadata: { provider: 'email' },
    user_metadata: {},
    identities: [{ id: 'x', provider: 'email' }],
    created_at: new Date().toISOString(),
});

const googleSwitch = (page, enabled) =>
    page.route('**/auth/v1/settings', (route) => route.fulfill(json({ external: { google: enabled, email: true } })));

test('sign-up asks for the emailed code; a wrong code shows an error; you can go back', async ({ page }) => {
    const email = 'code-e2e@example.invalid';
    await page.route('**/rest/v1/rpc/is_username_available', (route) => route.fulfill(json(true)));
    await page.route('**/auth/v1/signup**', (route) => route.fulfill(json(unconfirmedUser(email))));
    let verifyBody = null;
    await page.route('**/auth/v1/verify**', (route) => {
        verifyBody = route.request().postDataJSON();
        return route.fulfill(json({ code: 403, error_code: 'otp_expired', msg: 'Token has expired or is invalid' }, 403));
    });

    await page.goto('/register');
    await page.getByLabel('Username').fill('codee2e');
    await page.getByLabel('Email').fill(email);
    await page.locator('#reg-password').fill('Secret123!');
    await page.getByRole('button', { name: 'Create account' }).click();

    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();
    const verify = page.getByRole('button', { name: 'Verify and continue' });
    await expect(verify).toBeDisabled();
    await expect(page.getByText(/send a new code in \d+s/)).toBeVisible();

    await page.getByLabel('Confirmation code').fill('12a34 56'); // only digits are kept
    await expect(page.getByLabel('Confirmation code')).toHaveValue('123456');
    await verify.click();
    await expect(page.getByText('That code is wrong or has expired. Check it, or send a new one.')).toBeVisible();
    expect(verifyBody).toMatchObject({ email, token: '123456', type: 'email' });

    await page.getByRole('button', { name: 'Use a different email' }).click();
    await expect(page.getByRole('heading', { name: 'Create account' })).toBeVisible();
});

test('signing in before confirming sends a fresh code and asks for it', async ({ page }) => {
    const email = 'unconfirmed-e2e@example.invalid';
    await page.route('**/auth/v1/token?grant_type=password', (route) =>
        route.fulfill(json({ code: 400, error_code: 'email_not_confirmed', msg: 'Email not confirmed' }, 400)));
    let resendBody = null;
    await page.route('**/auth/v1/resend**', (route) => {
        resendBody = route.request().postDataJSON();
        return route.fulfill(json({}));
    });

    await page.goto('/login');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password', { exact: true }).fill('Secret123!');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
    expect(resendBody).toMatchObject({ email, type: 'signup' });
    await page.getByRole('button', { name: 'Back to sign in' }).click();
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});

test('the Google button is hidden until Google is switched on in Supabase', async ({ page }) => {
    await googleSwitch(page, false);
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: /google/i })).toHaveCount(0);
});

test('Continue with Google sends the browser to Supabase with a way back to /login', async ({ page }) => {
    await googleSwitch(page, true);
    let authorizeUrl = null;
    await page.route('**/auth/v1/authorize**', (route) => {
        authorizeUrl = new URL(route.request().url());
        return route.fulfill({ status: 200, contentType: 'text/html', body: '<p>Google (faked)</p>' });
    });

    await page.goto('/register');
    await expect(page.getByRole('button', { name: 'Sign up with Google' })).toBeVisible();
    await page.goto('/login');
    await page.getByRole('button', { name: 'Continue with Google' }).click();

    await expect(page.getByText('Google (faked)')).toBeVisible();
    expect(authorizeUrl.searchParams.get('provider')).toBe('google');
    expect(authorizeUrl.searchParams.get('redirect_to')).toMatch(/\/login$/);
});

test('an error sent back from Google sign-in is shown on the login page', async ({ page }) => {
    await page.goto('/login#error=server_error&error_description=Unsupported+provider%3A+provider+is+not+enabled');
    await expect(page.getByText("Google sign-in isn't switched on yet. Please use your email and password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
});
