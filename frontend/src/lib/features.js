/** Feature switches read from build-time env vars. */

/**
 * The self-hosted ML service (ml-service/): Quick Add, category suggestions, insights, bill
 * scanning and the chatbot.
 * Set VITE_ML_API_URL to its base URL, e.g. http://localhost:8000; unset hides ML features.
 */
export const ML_API_URL = (import.meta.env.VITE_ML_API_URL || '').replace(/\/+$/, '');
export const ML_ENABLED = Boolean(ML_API_URL);

/**
 * Subscriptions (Pro plan, Razorpay). Off for now: every feature is free and unlimited,
 * and no plan labels or upgrade prompts show. VITE_ENABLE_BILLING=true brings them back.
 */
export const BILLING_ENABLED = import.meta.env.VITE_ENABLE_BILLING === 'true';
