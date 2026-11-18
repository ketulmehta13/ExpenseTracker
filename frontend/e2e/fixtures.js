// Shared test fixture: answers the ML service's calls in the browser, so the signed-in pages
// render as in production (Quick Add, Scan bill, chatbot button) without a real ML service.
import { test as base, expect } from '@playwright/test';

const ML = 'http://ml.e2e.invalid';

/** What /v1/parse returns for the next Quick Add submit; tests can replace it. */
export const parseReplies = { next: null };

export const test = base.extend({
    page: async ({ page }, use) => {
        await page.route(`${ML}/**`, async (route) => {
            const url = new URL(route.request().url());
            // The app runs on another origin, so answer the browser's CORS checks like the real service
            const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' };
            if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
            const json = (body) => route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) });
            if (url.pathname === '/v1/parse') return json(parseReplies.next);
            if (url.pathname === '/v1/categorize') return json({ suggestion: null, model_version: null });
            if (url.pathname === '/v1/insights') {
                return json({ as_of: url.searchParams.get('today'), unusual: [], recurring: [], recurring_monthly_total: 0, forecast: null });
            }
            if (url.pathname === '/v1/insights/summary') return json({ text: '', source: 'template' });
            if (url.pathname === '/health') return json({ status: 'ok' });
            return route.fulfill({ status: 404, headers, body: '' });
        });
        await use(page);
    },
});

export { expect };
