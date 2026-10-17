import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient, type SupabaseClient } from 'https://esm.sh/@supabase/supabase-js@2';

// ---------------------------------------------------------------------------
// Permanently deletes the caller's account: stops Razorpay billing, removes
// their files, then deletes the auth user (profiles, categories, transactions
// and subscriptions cascade from auth.users).
// ---------------------------------------------------------------------------
const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';
const RAZORPAY_KEY_ID = Deno.env.get('RAZORPAY_KEY_ID') ?? '';
const RAZORPAY_KEY_SECRET = Deno.env.get('RAZORPAY_KEY_SECRET') ?? '';

// Razorpay subscription states in which the customer can still be charged
const BILLABLE_STATUSES = ['created', 'authenticated', 'active', 'pending', 'halted', 'paused'];
// Storage buckets that keep per-user files under a "<user_id>/" prefix
const USER_BUCKETS = ['avatars', 'receipts', 'imports'];

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

async function cancelRazorpaySubscription(subscriptionId: string): Promise<void> {
  const lookup = await fetch(`https://api.razorpay.com/v1/subscriptions/${subscriptionId}`, {
    headers: { Authorization: razorpayAuth() },
  });
  if (!lookup.ok) throw new Error(`Razorpay lookup failed: ${await lookup.text()}`);

  const { status } = await lookup.json();
  if (!BILLABLE_STATUSES.includes(status)) return;

  const cancel = await fetch(`https://api.razorpay.com/v1/subscriptions/${subscriptionId}/cancel`, {
    method: 'POST',
    headers: { Authorization: razorpayAuth(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ cancel_at_cycle_end: 0 }),
  });
  if (!cancel.ok) throw new Error(`Razorpay cancel failed: ${await cancel.text()}`);
}

async function deleteUserFiles(supabase: SupabaseClient, userId: string): Promise<void> {
  for (const bucket of USER_BUCKETS) {
    // Listing returns at most `limit` files, so keep removing until the folder is empty
    for (let batch = 0; batch < 100; batch++) {
      const { data: files, error } = await supabase.storage.from(bucket).list(userId, { limit: 1000 });
      // A missing bucket just means that feature has never stored anything
      if (error || !files?.length) break;

      const { error: removeErr } = await supabase.storage
        .from(bucket)
        .remove(files.map((file) => `${userId}/${file.name}`));
      if (removeErr) throw removeErr;
    }
  }
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'POST') return jsonResponse({ error: 'Method not allowed' }, 405);

  try {
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) return jsonResponse({ error: 'Missing Authorization header' }, 401);

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const { data: { user }, error: authErr } = await supabase.auth.getUser(
      authHeader.replace('Bearer ', ''),
    );
    if (authErr || !user) return jsonResponse({ error: 'Unauthorized' }, 401);

    // ── 1. Stop billing first: never delete an account that can still be charged ──
    const { data: sub, error: subErr } = await supabase
      .from('subscriptions')
      .select('razorpay_subscription_id')
      .eq('user_id', user.id)
      .maybeSingle();
    if (subErr) throw subErr;

    if (sub?.razorpay_subscription_id) {
      if (!RAZORPAY_KEY_ID || !RAZORPAY_KEY_SECRET) {
        return jsonResponse({ error: 'Razorpay not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.' }, 503);
      }
      try {
        await cancelRazorpaySubscription(sub.razorpay_subscription_id);
      } catch (err) {
        console.error('delete-account: could not cancel subscription:', err);
        return jsonResponse({
          error: 'We could not cancel your subscription, so your account was not deleted. Please try again.',
        }, 502);
      }
    }

    // ── 2. Remove stored files ───────────────────────────────────────────────
    await deleteUserFiles(supabase, user.id);

    // ── 3. Delete the auth user (cascades to all of the user's rows) ─────────
    const { error: deleteErr } = await supabase.auth.admin.deleteUser(user.id);
    if (deleteErr) throw deleteErr;

    return jsonResponse({ success: true });
  } catch (err) {
    console.error('delete-account error:', err);
    return jsonResponse({ error: 'Failed to delete account. Please try again.' }, 500);
  }
});
