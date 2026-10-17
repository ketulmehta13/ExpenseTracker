import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------
const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';
const RAZORPAY_WEBHOOK_SECRET = Deno.env.get('RAZORPAY_WEBHOOK_SECRET') ?? '';

const GRACE_PERIOD_MS = 3 * 24 * 60 * 60 * 1000;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-razorpay-signature',
};

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

// Convert ArrayBuffer to hex string
function bufferToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// Compare without returning early, so response timing doesn't reveal how much of a signature matched
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

// Verify Razorpay webhook signature (HMAC-SHA256)
async function verifySignature(rawBody: string, signature: string, secret: string): Promise<boolean> {
  try {
    const encoder = new TextEncoder();
    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      encoder.encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign'],
    );
    const computed = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(rawBody));
    return timingSafeEqual(bufferToHex(computed), signature);
  } catch (err) {
    console.error('Signature verification error:', err);
    return false;
  }
}

// Razorpay timestamps are unix seconds
function toIso(unixSeconds?: number | null): string | null {
  return unixSeconds ? new Date(unixSeconds * 1000).toISOString() : null;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    // ── 1. Verify Signature (fail closed) ─────────────────────────────────
    if (!RAZORPAY_WEBHOOK_SECRET) {
      console.error('RAZORPAY_WEBHOOK_SECRET is not set; refusing to process webhooks.');
      return jsonResponse({ error: 'Webhook not configured' }, 500);
    }

    const signature = req.headers.get('x-razorpay-signature');
    const rawBody = await req.text();
    if (!signature) {
      return jsonResponse({ error: 'Missing x-razorpay-signature header' }, 400);
    }
    if (!(await verifySignature(rawBody, signature, RAZORPAY_WEBHOOK_SECRET))) {
      console.error('Invalid webhook signature');
      return jsonResponse({ error: 'Invalid signature' }, 401);
    }

    const payload = JSON.parse(rawBody);
    const event = payload.event as string;
    // Razorpay sends the event id as a header; retried deliveries reuse it
    const eventId = req.headers.get('x-razorpay-event-id') ?? (payload.id as string | undefined) ?? null;

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // ── 2. Skip Events Already Processed ──────────────────────────────────
    if (eventId) {
      const { data: seen } = await supabase
        .from('webhook_events_log')
        .select('id')
        .eq('razorpay_event_id', eventId)
        .limit(1)
        .maybeSingle();
      if (seen) return jsonResponse({ status: 'duplicate', event });
    }

    const subscriptionEntity = payload.payload?.subscription?.entity;
    const paymentEntity = payload.payload?.payment?.entity;
    const razorpaySubId = subscriptionEntity?.id || paymentEntity?.subscription_id;

    // Extract metadata/notes
    const userId = subscriptionEntity?.notes?.supabase_user_id;
    const planType = subscriptionEntity?.notes?.plan; // 'monthly' or 'yearly'
    const dbPlan = planType === 'yearly' ? 'pro_yearly' : 'pro_monthly';
    const now = new Date().toISOString();

    // Insert-or-update the user's row (lifecycle events carry the user id in notes)
    const upsertForUser = async (fields: Record<string, unknown>) => {
      const { error } = userId
        ? await supabase
          .from('subscriptions')
          .upsert({ user_id: userId, ...fields, updated_at: now }, { onConflict: 'user_id' })
        : await supabase
          .from('subscriptions')
          .update({ ...fields, updated_at: now })
          .eq('razorpay_subscription_id', razorpaySubId);
      if (error) throw error;
    };

    const updateBySubscription = async (fields: Record<string, unknown>, onlyStatuses?: string[]) => {
      let query = supabase
        .from('subscriptions')
        .update({ ...fields, updated_at: now })
        .eq('razorpay_subscription_id', razorpaySubId);
      if (onlyStatuses) query = query.in('status', onlyStatuses);
      const { error } = await query;
      if (error) throw error;
    };

    // ── 3. Handle Subscription Lifecycle Events ───────────────────────────
    if (!razorpaySubId) {
      console.log(`Received event ${event} with no associated subscription ID.`);
    } else {
      switch (event) {
        // 1. Mandate authorized. Checkout starts billing 7 days later, so this is the free trial.
        case 'subscription.authenticated': {
          const trialEnd = toIso(subscriptionEntity?.start_at);
          await upsertForUser({
            plan: dbPlan,
            status: 'trialing',
            razorpay_subscription_id: razorpaySubId,
            trial_end: trialEnd,
            current_period_end: trialEnd,
            grace_period_end: null,
            cancel_at_period_end: false,
          });
          break;
        }

        // 2. First billing cycle started (trial over, first charge made)
        case 'subscription.activated': {
          await upsertForUser({
            plan: dbPlan,
            status: 'active',
            razorpay_subscription_id: razorpaySubId,
            current_period_end: toIso(subscriptionEntity?.current_end),
            grace_period_end: null,
          });
          break;
        }

        // 3. Subscription Charged (successful recurring payment)
        case 'subscription.charged': {
          await updateBySubscription({
            status: 'active',
            current_period_end: toIso(subscriptionEntity?.current_end)
              ?? new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
            grace_period_end: null,
          });
          break;
        }

        // 4. Renewal payment failed -> grace period. Only for live subscriptions: a card
        //    declined during checkout must not grant Pro for the grace period.
        case 'subscription.pending':
        case 'payment.failed': {
          await updateBySubscription(
            {
              status: 'past_due',
              grace_period_end: new Date(Date.now() + GRACE_PERIOD_MS).toISOString(),
            },
            ['active', 'trialing'],
          );
          break;
        }

        // 5. Subscription ended. Pro stays until current_period_end (see get_user_plan).
        case 'subscription.cancelled':
        case 'subscription.halted':
        case 'subscription.completed': {
          await updateBySubscription({ status: 'canceled', cancel_at_period_end: false });
          break;
        }

        default:
          console.log(`Unhandled webhook event: ${event}`);
      }
    }

    // ── 4. Log Webhook Event (audit trail; also marks it as processed) ────
    // Logged after processing so a failed attempt is retried by Razorpay instead of skipped.
    const { error: logErr } = await supabase.from('webhook_events_log').insert({
      event_type: event,
      razorpay_event_id: eventId,
      payload: payload,
      processed_at: now,
    });
    if (logErr) console.error('Failed to log webhook event:', logErr);

    return jsonResponse({ status: 'success', event });
  } catch (err) {
    console.error('Webhook processing error:', err);
    return jsonResponse({ error: 'Webhook processing failed' }, 500);
  }
});
