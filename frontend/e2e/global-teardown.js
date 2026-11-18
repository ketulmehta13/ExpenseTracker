import { cleanup } from './db.js';
import { hasTestAccount } from './env.js';

// Remove every "E2E …" transaction, even when a test failed half-way
export default async function globalTeardown() {
    if (hasTestAccount()) await cleanup();
}
