import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

// ---------------------------------------------------------------------------
// Environment (set via: supabase secrets set KEY=value)
// ---------------------------------------------------------------------------
const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';
const RAZORPAY_KEY_ID = Deno.env.get('RAZORPAY_KEY_ID') ?? '';
const RAZORPAY_KEY_SECRET = Deno.env.get('RAZORPAY_KEY_SECRET') ?? '';
const RAZORPAY_PLAN_ID_MONTHLY = Deno.env.get('RAZORPAY_PLAN_ID_MONTHLY') ?? '';
const RAZORPAY_PLAN_ID_YEARLY = Deno.env.get('RAZORPAY_PLAN_ID_YEARLY') ?? '';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

// Razorpay Basic Auth header (Key ID : Key Secret, base64 encoded)
function razorpayAuth() {
  return 'Basic ' + btoa(`${RAZORPAY_KEY_ID}:${RAZORPAY_KEY_SECRET}`);
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    // ── 1. Verify JWT ──────────────────────────────────────────────────────
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) return jsonResponse({ error: 'Missing Authorization header' }, 401);

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const { data: { user }, error: authErr } = await supabase.auth.getUser(
      authHeader.replace('Bearer ', ''),
    );
    if (authErr || !user) return jsonResponse({ error: 'Unauthorized' }, 401);

    // ── 2. Parse request ───────────────────────────────────────────────────
    const { plan } = await req.json() as { plan: 'monthly' | 'yearly' };
    if (!plan || !['monthly', 'yearly'].includes(plan)) {
      return jsonResponse({ error: 'plan must be "monthly" or "yearly"' }, 400);
    }

    // ── 3. Validate secrets are configured ────────────────────────────────
    if (!RAZORPAY_KEY_ID || !RAZORPAY_KEY_SECRET) {
      return jsonResponse({ error: 'Razorpay not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.' }, 503);
    }
    const planId = plan === 'monthly' ? RAZORPAY_PLAN_ID_MONTHLY : RAZORPAY_PLAN_ID_YEARLY;
    if (!planId) {
      return jsonResponse({ error: `Razorpay plan ID not configured for ${plan}` }, 503);
    }

    // ── 4. Check if user already has an active subscription ───────────────
    const { data: existingSub } = await supabase
      .from('subscriptions')
      .select('razorpay_subscription_id, status, plan')
      .eq('user_id', user.id)
      .maybeSingle();

    // If already pro and active, return early
    if (
      existingSub &&
      existingSub.plan !== 'free' &&
      ['active', 'trialing'].includes(existingSub.status) &&
      existingSub.razorpay_subscription_id
    ) {
      return jsonResponse({
        subscriptionId: existingSub.razorpay_subscription_id,
        keyId: RAZORPAY_KEY_ID,
        alreadySubscribed: true,
      });
    }

    // ── 5. Create Razorpay Subscription ───────────────────────────────────
    const rzpBody = {
      plan_id: planId,
      total_count: plan === 'yearly' ? 12 : 120, // max billing cycles
      quantity: 1,
      // 7-day free trial
      start_at: Math.floor((Date.now() + 7 * 24 * 60 * 60 * 1000) / 1000),
      // Expire link after 24h if not paid
      expire_by: Math.floor((Date.now() + 24 * 60 * 60 * 1000) / 1000),
      customer_notify: 1,
      notes: {
        supabase_user_id: user.id,
        user_email: user.email ?? '',
        plan,
      },
    };

    const rzpRes = await fetch('https://api.razorpay.com/v1/subscriptions', {
      method: 'POST',
      headers: {
        Authorization: razorpayAuth(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(rzpBody),
    });

    if (!rzpRes.ok) {
      const errText = await rzpRes.text();
      console.error('Razorpay create subscription error:', errText);
      return jsonResponse({ error: 'Failed to create subscription. Please try again.' }, 502);
    }

    const rzpSub = await rzpRes.json();

    // ── 6. Store pending subscription in our DB ────────────────────────────
    const dbPlan = plan === 'monthly' ? 'pro_monthly' : 'pro_yearly';
    await supabase.from('subscriptions').upsert({
      user_id: user.id,
      plan: dbPlan,
      status: 'pending',
      razorpay_subscription_id: rzpSub.id,
      trial_end: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      updated_at: new Date().toISOString(),
    }, { onConflict: 'user_id' });

    // ── 7. Return subscription ID + public key to frontend ─────────────────
    return jsonResponse({
      subscriptionId: rzpSub.id,
      keyId: RAZORPAY_KEY_ID,
    });
  } catch (err) {
    console.error('razorpay-checkout error:', err);
    return jsonResponse({ error: 'Internal server error' }, 500);
  }
});
