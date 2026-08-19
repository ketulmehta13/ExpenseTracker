import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';
const RAZORPAY_KEY_ID = Deno.env.get('RAZORPAY_KEY_ID') ?? '';
const RAZORPAY_KEY_SECRET = Deno.env.get('RAZORPAY_KEY_SECRET') ?? '';

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

function razorpayAuth() {
  return 'Basic ' + btoa(`${RAZORPAY_KEY_ID}:${RAZORPAY_KEY_SECRET}`);
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) return jsonResponse({ error: 'Missing Authorization header' }, 401);

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const { data: { user }, error: authErr } = await supabase.auth.getUser(
      authHeader.replace('Bearer ', ''),
    );
    if (authErr || !user) return jsonResponse({ error: 'Unauthorized' }, 401);

    // ── 1. Fetch user's subscription record ────────────────────────────────
    const { data: sub, error: subErr } = await supabase
      .from('subscriptions')
      .select('*')
      .eq('user_id', user.id)
      .single();

    if (subErr || !sub || !sub.razorpay_subscription_id) {
      return jsonResponse({ error: 'No active Razorpay subscription found' }, 404);
    }

    // ── 2. Call Razorpay API to cancel at cycle end ────────────────────────
    // cancel_at_cycle_end: 1 ensures user gets remaining paid time
    if (RAZORPAY_KEY_ID && RAZORPAY_KEY_SECRET) {
      const rzpRes = await fetch(
        `https://api.razorpay.com/v1/subscriptions/${sub.razorpay_subscription_id}/cancel`,
        {
          method: 'POST',
          headers: {
            Authorization: razorpayAuth(),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ cancel_at_cycle_end: 1 }),
        }
      );

      if (!rzpRes.ok) {
        const errText = await rzpRes.text();
        console.error('Razorpay cancel error:', errText);
      }
    }

    // ── 3. Update subscription status in DB ────────────────────────────────
    await supabase
      .from('subscriptions')
      .update({
        status: 'canceled',
        updated_at: new Date().toISOString(),
      })
      .eq('user_id', user.id);

    return jsonResponse({ success: true, message: 'Subscription canceled successfully. Access continues until end of billing period.' });
  } catch (err) {
    console.error('razorpay-cancel error:', err);
    return jsonResponse({ error: 'Internal server error' }, 500);
  }
});
