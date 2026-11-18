// End-to-end regression suite. See e2e/README.md for setup.
import { defineConfig, devices } from '@playwright/test';
import { loadEnv } from './e2e/env.js';

loadEnv();

const PORT = 5181; // 5173 is left free for the normal dev server
export const ML_FAKE_URL = 'http://ml.e2e.invalid';

// E2E_CHANNEL=chrome uses the installed Google Chrome instead of Playwright's own Chromium
const browser = {
    ...devices['Desktop Chrome'],
    ...(process.env.E2E_CHANNEL ? { channel: process.env.E2E_CHANNEL } : {}),
};
const signedIn = { ...browser, storageState: 'e2e/.auth/user.json' };

export default defineConfig({
    testDir: './e2e',
    // Every signed-in test uses the same test account, so run one at a time
    workers: 1,
    fullyParallel: false,
    retries: 0,
    timeout: 45_000,
    expect: { timeout: 10_000 },
    reporter: [['list']],
    globalTeardown: './e2e/global-teardown.js',
    use: {
        baseURL: `http://localhost:${PORT}`,
        trace: 'retain-on-failure',
        locale: 'en-IN',
        timezoneId: 'Asia/Kolkata',
    },
    projects: [
        { name: 'public', testMatch: /public\.spec\.js/, use: browser },
        { name: 'setup', testMatch: /auth\.setup\.js/, use: browser },
        {
            name: 'signed-in',
            testMatch: /app[\\/].*\.spec\.js/,
            testIgnore: /mobile\.spec\.js/,
            dependencies: ['setup'],
            use: signedIn,
        },
        {
            // The width the user checks on their phone
            name: 'mobile-618',
            testMatch: /app[\\/]mobile\.spec\.js/,
            dependencies: ['setup'],
            use: { ...signedIn, viewport: { width: 618, height: 900 } },
        },
    ],
    webServer: {
        command: `npm run dev -- --port ${PORT} --strictPort`,
        url: `http://localhost:${PORT}`,
        reuseExistingServer: false,
        timeout: 120_000,
        // Production has the ML service switched on; a fake URL keeps the same UI, and the tests answer its calls
        env: { VITE_ML_API_URL: ML_FAKE_URL },
    },
});
