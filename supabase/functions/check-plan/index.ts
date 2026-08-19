import { serve } from 'https://deno.land/std@0.208.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? '';
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '';

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

    // Call stored procedure get_user_plan
    const { data: planInfo, error: planErr } = await supabase
      .rpc('get_user_plan', { uid: user.id })
      .single();

    if (planErr || !planInfo) {
      // Fallback default free
      return jsonResponse({
        plan: 'free',
        status: 'active',
        isPro: false,
        isTrialing: false,
        canAddCategory: true,
        canExportCSV: false,
        canUseAI: false,
        historyMonths: 3,
      });
    }

    const isPro = Boolean(planInfo.is_pro);
    const isTrialing = planInfo.status === 'trialing';

    // Count user's custom categories
    const { count: customCategoryCount } = await supabase
      .from('categories')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', user.id);

    const canAddCategory = isPro || (customCategoryCount ?? 0) < 5;

    return jsonResponse({
      plan: planInfo.plan,
      status: planInfo.status,
      isPro,
      isTrialing,
      trialEnd: planInfo.trial_end,
      periodEnd: planInfo.period_end,
      customCategoryCount: customCategoryCount ?? 0,
      canAddCategory,
      canExportCSV: isPro,
      canUseAI: isPro,
      historyMonths: isPro ? null : 3,
    });
  } catch (err) {
    console.error('check-plan error:', err);
    return jsonResponse({ error: 'Internal server error' }, 500);
  }
});
