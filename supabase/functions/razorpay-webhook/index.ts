import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { crypto } from 'https://deno.land/std@0.208.0/crypto/mod.ts';

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------
const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';
const RAZORPAY_WEBHOOK_SECRET = Deno.env.get('RAZORPAY_WEBHOOK_SECRET') ?? '';

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

// Verify Razorpay webhook signature (HMAC-SHA256)
async function verifySignature(rawBody: string, signature: string, secret: string): Promise<boolean> {
  try {
    const encoder = new TextEncoder();
    const keyData = encoder.encode(secret);
    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      keyData,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign', 'verify']
    );
    const computedSignatureBuffer = await crypto.subtle.sign(
      'HMAC',
      cryptoKey,
      encoder.encode(rawBody)
    );
    const computedSignature = bufferToHex(computedSignatureBuffer);
    return computedSignature === signature;
  } catch (err) {
    console.error('Signature verification error:', err);
    return false;
  }
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const signature = req.headers.get('x-razorpay-signature');
    const rawBody = await req.text();

    // ── 1. Verify Signature ────────────────────────────────────────────────
    if (!RAZORPAY_WEBHOOK_SECRET) {
      console.warn('RAZORPAY_WEBHOOK_SECRET not set. Proceeding without signature verification (Development mode only).');
    } else {
      if (!signature) {
        return jsonResponse({ error: 'Missing x-razorpay-signature header' }, 400);
      }
      const isValid = await verifySignature(rawBody, signature, RAZORPAY_WEBHOOK_SECRET);
      if (!isValid) {
        console.error('Invalid webhook signature');
        return jsonResponse({ error: 'Invalid signature' }, 401);
      }
    }

    const payload = JSON.parse(rawBody);
    const event = payload.event as string;
    const eventId = payload.id as string | undefined;

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // ── 2. Log Webhook Event for Audit Trail ──────────────────────────────
    await supabase.from('webhook_events_log').insert({
      event_type: event,
      razorpay_event_id: eventId ?? null,
      payload: payload,
      processed_at: new Date().toISOString(),
    });

    const subscriptionEntity = payload.payload?.subscription?.entity;
    const paymentEntity = payload.payload?.payment?.entity;
    const razorpaySubId = subscriptionEntity?.id || paymentEntity?.subscription_id;

    if (!razorpaySubId) {
      console.log(`Received event ${event} with no associated subscription ID.`);
      return jsonResponse({ status: 'ignored', message: 'No subscription ID in event payload' });
    }

    // Extract metadata/notes
    const userId = subscriptionEntity?.notes?.supabase_user_id;
    const planType = subscriptionEntity?.notes?.plan; // 'monthly' or 'yearly'
    const dbPlan = planType === 'yearly' ? 'pro_yearly' : 'pro_monthly';

    // ── 3. Handle Subscription Lifecycle Events ───────────────────────────
    switch (event) {
      // 1. Subscription Activated (after first payment / trial activation)
      case 'subscription.activated': {
        const currentPeriodEnd = subscriptionEntity.current_end
          ? new Date(subscriptionEntity.current_end * 1000).toISOString()
          : null;
        const trialEnd = subscriptionEntity.start_at
          ? new Date(subscriptionEntity.start_at * 1000).toISOString()
          : null;

        const updateData: Record<string, unknown> = {
          plan: dbPlan,
          status: subscriptionEntity.status === 'trialing' ? 'trialing' : 'active',
          razorpay_subscription_id: razorpaySubId,
          current_period_end: currentPeriodEnd,
          trial_end: trialEnd,
          grace_period_end: null,
          updated_at: new Date().toISOString(),
        };

        if (userId) {
          await supabase.from('subscriptions').upsert({
            user_id: userId,
            ...updateData,
          }, { onConflict: 'user_id' });
        } else {
          await supabase
            .from('subscriptions')
            .update(updateData)
            .eq('razorpay_subscription_id', razorpaySubId);
        }
        break;
      }

      // 2. Subscription Charged (successful recurring payment)
      case 'subscription.charged': {
        const currentPeriodEnd = subscriptionEntity?.current_end
          ? new Date(subscriptionEntity.current_end * 1000).toISOString()
          : new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

        await supabase
          .from('subscriptions')
          .update({
            status: 'active',
            current_period_end: currentPeriodEnd,
            grace_period_end: null,
            updated_at: new Date().toISOString(),
          })
          .eq('razorpay_subscription_id', razorpaySubId);
        break;
      }

      // 3. Payment Failed / Pending -> Grace Period (3 days)
      case 'subscription.pending':
      case 'payment.failed': {
        const graceEnd = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
        await supabase
          .from('subscriptions')
          .update({
            status: 'past_due',
            grace_period_end: graceEnd,
            updated_at: new Date().toISOString(),
          })
          .eq('razorpay_subscription_id', razorpaySubId);
        break;
      }

      // 4. Subscription Cancelled / Halted / Completed
      case 'subscription.cancelled':
      case 'subscription.halted':
      case 'subscription.completed': {
        await supabase
          .from('subscriptions')
          .update({
            status: 'canceled',
            updated_at: new Date().toISOString(),
          })
          .eq('razorpay_subscription_id', razorpaySubId);
        break;
      }

      default:
        console.log(`Unhandled webhook event: ${event}`);
    }

    return jsonResponse({ status: 'success', event });
  } catch (err) {
    console.error('Webhook processing error:', err);
    return jsonResponse({ error: 'Webhook processing failed' }, 500);
  }
});
