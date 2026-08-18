import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const OPENAI_API_KEY = Deno.env.get('OPENAI_API_KEY') ?? '';
const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';

const MAX_CALLS_PER_HOUR = 50;
const OPENAI_MODEL = 'gpt-4o-mini';
const OPENAI_TIMEOUT_MS = 10_000;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

async function callOpenAI(messages: object[], jsonMode = true): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OPENAI_TIMEOUT_MS);

  try {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${OPENAI_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: OPENAI_MODEL,
        messages,
        temperature: 0.2,
        max_tokens: 256,
        ...(jsonMode ? { response_format: { type: 'json_object' } } : {}),
      }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`OpenAI error ${res.status}: ${err}`);
    }

    const data = await res.json();
    return data.choices?.[0]?.message?.content ?? '';
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Rate limiting (service-role client, bypasses RLS)
// ---------------------------------------------------------------------------
async function checkRateLimit(supabase: ReturnType<typeof createClient>, userId: string): Promise<boolean> {
  const now = new Date();
  const windowStart = new Date(now.getTime() - 60 * 60 * 1000); // 1 hour ago

  const { data, error } = await supabase
    .from('ai_rate_limits')
    .select('call_count, window_start')
    .eq('user_id', userId)
    .maybeSingle();

  if (error) return true; // Allow on DB error (fail open)

  if (!data || new Date(data.window_start) < windowStart) {
    // No record or window expired — reset
    await supabase.from('ai_rate_limits').upsert({
      user_id: userId,
      call_count: 1,
      window_start: now.toISOString(),
    });
    return true;
  }

  if (data.call_count >= MAX_CALLS_PER_HOUR) return false; // Rate limited

  await supabase
    .from('ai_rate_limits')
    .update({ call_count: data.call_count + 1 })
    .eq('user_id', userId);

  return true;
}

async function logUsage(supabase: ReturnType<typeof createClient>, userId: string, feature: string) {
  await supabase.from('ai_usage_log').insert({ user_id: userId, feature });
}

// ---------------------------------------------------------------------------
// AI Handlers
// ---------------------------------------------------------------------------

/** categorize: suggest a category name given a transaction title + existing categories */
async function handleCategorize(payload: { title: string; categories: string[] }) {
  const { title, categories } = payload;

  if (!title || title.trim().length < 2) {
    return { category: null };
  }

  const catList = (categories ?? []).join(', ') || 'Groceries, Dining Out, Transportation, Entertainment, Utilities, Health & Medical, Salary, Freelance, Rent & Housing, Shopping';

  const content = await callOpenAI([
    {
      role: 'system',
      content: `You are a financial categorization assistant. Given a transaction description, suggest the single most appropriate category from the provided list. If none fit well, suggest the closest one. Always respond with valid JSON: {"category": "<name>", "confidence": "high"|"medium"|"low"}`,
    },
    {
      role: 'user',
      content: `Transaction: "${title}"\nAvailable categories: ${catList}`,
    },
  ]);

  try {
    const parsed = JSON.parse(content);
    return { category: parsed.category ?? null, confidence: parsed.confidence ?? 'medium' };
  } catch {
    return { category: null };
  }
}

/** parse_transaction: parse natural language into structured transaction fields */
async function handleParseTransaction(payload: { text: string }) {
  const { text } = payload;

  if (!text || text.trim().length < 3) {
    return { error: 'Input too short' };
  }

  const today = new Date().toISOString().split('T')[0];

  const content = await callOpenAI([
    {
      role: 'system',
      content: `You are a financial data parser. Extract transaction details from natural language. Today's date is ${today}.
      
Always respond with valid JSON matching exactly this schema:
{
  "type": "INCOME" | "EXPENSE",
  "amount": <positive number>,
  "description": "<short title>",
  "category": "<suggested category name>",
  "date": "<YYYY-MM-DD>",
  "confidence": "high" | "medium" | "low"
}

If you cannot confidently extract an amount, set "confidence": "low" and "amount": 0.
Examples:
- "spent 450 on groceries yesterday" → EXPENSE, 450, "Groceries", yesterday's date
- "received 20000 salary today" → INCOME, 20000, "Salary", today
- "uber to airport 280" → EXPENSE, 280, "Transportation", today`,
    },
    {
      role: 'user',
      content: text,
    },
  ]);

  try {
    const parsed = JSON.parse(content);
    if (!parsed.amount || parsed.amount <= 0 || parsed.confidence === 'low') {
      return { error: "Couldn't extract a valid amount. Try including a number (e.g. ₹450)." };
    }
    return parsed;
  } catch {
    return { error: 'Failed to parse. Try: "spent 300 on coffee" or "received 5000 salary".' };
  }
}

/** monthly_insight: generate 2–4 sentence plain-English summary from aggregated data */
async function handleMonthlyInsight(payload: {
  currentMonth: { income: number; expense: number; balance: number; topCategories: { name: string; total: number }[] };
  previousMonth: { income: number; expense: number };
  month: string;
}) {
  const { currentMonth, previousMonth, month } = payload;

  const topCats = (currentMonth.topCategories ?? [])
    .slice(0, 5)
    .map((c) => `${c.name}: ₹${c.total.toFixed(0)}`)
    .join(', ');

  const content = await callOpenAI(
    [
      {
        role: 'system',
        content: `You are a personal finance advisor. Write a friendly, concise 2–4 sentence insight about the user's monthly finances. Be specific with numbers. Use ₹ for currency. No bullet points — flowing prose only.`,
      },
      {
        role: 'user',
        content: `Month: ${month}
Current month — Income: ₹${currentMonth.income.toFixed(0)}, Expenses: ₹${currentMonth.expense.toFixed(0)}, Balance: ₹${currentMonth.balance.toFixed(0)}
Previous month — Income: ₹${previousMonth.income.toFixed(0)}, Expenses: ₹${previousMonth.expense.toFixed(0)}
Top expense categories: ${topCats || 'None yet'}

Write a 2–4 sentence insight about spending patterns, trends vs last month, and one actionable tip.`,
      },
    ],
    false, // plain text, not JSON mode
  );

  return { insight: content.trim() };
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------
serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    // 1. Verify JWT — extract user from Authorization header
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) return jsonResponse({ error: 'Missing Authorization header' }, 401);

    const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const { data: { user }, error: authErr } = await supabaseAdmin.auth.getUser(
      authHeader.replace('Bearer ', ''),
    );

    if (authErr || !user) return jsonResponse({ error: 'Unauthorized' }, 401);

    // 2. Check OpenAI key is configured
    if (!OPENAI_API_KEY) {
      return jsonResponse({ error: 'AI service not configured. Add OPENAI_API_KEY to Supabase secrets.' }, 503);
    }

    // 3. Parse request body
    const body = await req.json();
    const { type, payload } = body as { type: string; payload: Record<string, unknown> };

    if (!type) return jsonResponse({ error: 'Missing type parameter' }, 400);

    // 4. Rate limit check
    const allowed = await checkRateLimit(supabaseAdmin, user.id);
    if (!allowed) {
      return jsonResponse({ error: 'Rate limit exceeded. You can make 50 AI requests per hour.' }, 429);
    }

    // 5. Log usage (non-blocking, don't fail on log error)
    logUsage(supabaseAdmin, user.id, type).catch(() => {});

    // 6. Route to handler
    let result: unknown;
    switch (type) {
      case 'categorize':
        result = await handleCategorize(payload as { title: string; categories: string[] });
        break;
      case 'parse_transaction':
        result = await handleParseTransaction(payload as { text: string });
        break;
      case 'monthly_insight':
        result = await handleMonthlyInsight(payload as Parameters<typeof handleMonthlyInsight>[0]);
        break;
      default:
        return jsonResponse({ error: `Unknown type: ${type}` }, 400);
    }

    return jsonResponse(result);
  } catch (err) {
    console.error('ai-proxy error:', err);
    return jsonResponse({ error: 'Internal server error' }, 500);
  }
});
