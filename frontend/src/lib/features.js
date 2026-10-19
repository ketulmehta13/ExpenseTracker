/**
 * Feature switches read from build-time env vars.
 *
 * AI widgets (Quick Add, AI Insights, category suggestions) call the ai-proxy Edge
 * Function, which only works once an LLM key is set as a Supabase secret. Keep them
 * off until then so users never see buttons that can't work: VITE_ENABLE_AI=true.
 */
export const AI_ENABLED = import.meta.env.VITE_ENABLE_AI === 'true';

/**
 * The self-hosted ML service (ml-service/): category suggestions and, later, insights.
 * Set VITE_ML_API_URL to its base URL, e.g. http://localhost:8000; unset hides ML features.
 */
export const ML_API_URL = (import.meta.env.VITE_ML_API_URL || '').replace(/\/+$/, '');
export const ML_ENABLED = Boolean(ML_API_URL);

/**
 * Subscriptions (Pro plan, Razorpay). Off for now: every feature is free and unlimited,
 * and no plan labels or upgrade prompts show. VITE_ENABLE_BILLING=true brings them back.
 */
export const BILLING_ENABLED = import.meta.env.VITE_ENABLE_BILLING === 'true';
