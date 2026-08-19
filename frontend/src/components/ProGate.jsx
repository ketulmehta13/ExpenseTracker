import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Crown, Lock } from 'lucide-react';
import { usePlan } from '../context/PlanContext';

/**
 * ProGate component:
 * Wraps Pro-only UI elements. If user is Free, displays locked state or upgrade prompt.
 *
 * Props:
 *   featureName - String name of feature (e.g. "CSV Export", "Custom Categories")
 *   fallback - Custom fallback React node (optional)
 *   compact - Boolean for inline button locks (optional)
 */
export const ProGate = ({
    children,
    featureName = 'Pro feature',
    fallback = null,
    compact = false,
}) => {
    const { isPro, loading } = usePlan();
    const navigate = useNavigate();

    if (loading) {
        return children;
    }

    if (isPro) {
        return children;
    }

    if (fallback) {
        return fallback;
    }

    if (compact) {
        return (
            <button
                type="button"
                onClick={() => navigate('/dashboard/upgrade')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-primary/30 bg-primary/10 text-primary text-xs font-semibold hover:bg-primary/20 transition-all shadow-xs"
                title={`Upgrade to Pro to unlock ${featureName}`}
            >
                <Lock size={12} className="text-primary" />
                <span>Unlock {featureName}</span>
            </button>
        );
    }

    return (
        <div className="relative rounded-2xl border border-dashed border-primary/30 bg-primary/[0.03] p-6 text-center overflow-hidden">
            <div className="flex flex-col items-center max-w-sm mx-auto">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary mb-3">
                    <Crown size={20} />
                </div>
                <h3 className="text-sm font-bold text-foreground mb-1">
                    {featureName} is a Pro Feature
                </h3>
                <p className="text-xs text-muted-foreground mb-4">
                    Upgrade to Pro to unlock unlimited history, unlimited categories, full analytics, and CSV exports with a 7-day free trial.
                </p>
                <button
                    type="button"
                    onClick={() => navigate('/dashboard/upgrade')}
                    className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition active:scale-95"
                >
                    <Crown size={14} />
                    Upgrade to Pro
                </button>
            </div>
        </div>
    );
};

export default ProGate;
