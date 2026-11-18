// Reads frontend/.env, .env.local and .env.e2e.local (test account) into process.env.
// Same precedence as Vite: a later file overrides an earlier one, and variables already set in
// the shell override every file.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let loaded = false;

export function loadEnv() {
    if (loaded) return;
    loaded = true;
    const fromFiles = {};
    for (const name of ['.env', '.env.local', '.env.e2e.local']) {
        const file = path.join(root, name);
        if (!fs.existsSync(file)) continue;
        for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
            const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
            if (!match) continue;
            fromFiles[match[1]] = match[2].replace(/^(['"])(.*)\1$/, '$2');
        }
    }
    for (const [key, value] of Object.entries(fromFiles)) {
        if (process.env[key] === undefined) process.env[key] = value;
    }
}

export const hasTestAccount = () => Boolean(process.env.E2E_EMAIL && process.env.E2E_PASSWORD);
