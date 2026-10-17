/**
 * Feature switches read from build-time env vars.
 *
 * AI widgets (Quick Add, AI Insights, category suggestions) call the ai-proxy Edge
 * Function, which only works once an LLM key is set as a Supabase secret. Keep them
 * off until then so users never see buttons that can't work: VITE_ENABLE_AI=true.
 */
export const AI_ENABLED = import.meta.env.VITE_ENABLE_AI === 'true';
