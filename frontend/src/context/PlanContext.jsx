import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { getSubscription, checkUserPlan } from '../services/api';
import { supabase } from '../services/supabaseClient';

export const PlanContext = createContext();

export const usePlan = () => {
    const context = useContext(PlanContext);
    if (!context) {
        throw new Error('usePlan must be used within a PlanProvider');
    }
    return context;
};

export const PlanProvider = ({ children }) => {
    const { user } = useAuth();
    const [subscription, setSubscription] = useState(null);
    const [planInfo, setPlanInfo] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchPlan = useCallback(async () => {
        if (!user) {
            setSubscription(null);
            setPlanInfo(null);
            setLoading(false);
            return;
        }

        try {
            // First fetch row directly for immediate response
            const sub = await getSubscription(user.id);
            setSubscription(sub);

            // Fetch server-verified plan details
            try {
                const verified = await checkUserPlan();
                if (verified) {
                    setPlanInfo(verified);
                }
            } catch (e) {
                // If Edge Function not deployed yet in dev, fallback to table values
                console.warn('checkUserPlan fallback:', e.message);
            }
        } catch (err) {
            console.error('Error fetching plan:', err);
        } finally {
            setLoading(false);
        }
    }, [user]);

    useEffect(() => {
        fetchPlan();
    }, [fetchPlan]);

    // Listen to real-time updates on user's subscription row (e.g. when webhook fires)
    useEffect(() => {
        if (!user) return;

        const channel = supabase
            .channel(`subscription:${user.id}`)
            .on(
                'postgres_changes',
                {
                    event: '*',
                    schema: 'public',
                    table: 'subscriptions',
                    filter: `user_id=eq.${user.id}`,
                },
                () => {
                    fetchPlan();
                }
            )
            .subscribe();

        return () => {
            supabase.removeChannel(channel);
        };
    }, [user, fetchPlan]);

    const plan = subscription?.plan || 'free';
    const status = subscription?.status || 'active';

    const isPro = Boolean(
        planInfo?.isPro ?? (
            (plan === 'pro_monthly' || plan === 'pro_yearly') &&
            (status === 'active' || status === 'trialing' || status === 'past_due')
        )
    );

    const isTrialing = status === 'trialing';
    const isPastDue = status === 'past_due';
    const isCanceled = status === 'canceled';

    const historyMonths = isPro ? null : 3;
    const canExportCSV = isPro;
    const canUseAI = isPro;

    const value = {
        subscription,
        planInfo,
        plan,
        status,
        isPro,
        isTrialing,
        isPastDue,
        isCanceled,
        trialEnd: subscription?.trial_end,
        periodEnd: subscription?.current_period_end,
        gracePeriodEnd: subscription?.grace_period_end,
        historyMonths,
        canExportCSV,
        canUseAI,
        loading,
        refreshPlan: fetchPlan,
    };

    return (
        <PlanContext.Provider value={value}>
            {children}
        </PlanContext.Provider>
    );
};
