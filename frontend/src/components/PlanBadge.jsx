import React from 'react';
import { Crown, Sparkles, AlertCircle } from 'lucide-react';
import { usePlan } from '../context/PlanContext';

export const PlanBadge = ({ className = '', showUpgradeButton = false, onUpgradeClick }) => {
    const { isPro, isTrialing, isPastDue, plan } = usePlan();

    if (isPastDue) {
        return (
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-destructive/15 text-destructive border border-destructive/20 ${className}`}>
                <AlertCircle size={12} />
                Payment Due
            </span>
        );
    }

    if (isTrialing) {
        return (
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/20 ${className}`}>
                <Sparkles size={12} />
                Pro Trial
            </span>
        );
    }

    if (isPro) {
        return (
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-primary/15 text-primary border border-primary/25 shadow-xs ${className}`}>
                <Crown size={12} />
                {plan === 'pro_yearly' ? 'Pro Yearly' : 'Pro'}
            </span>
        );
    }

    return (
        <div className={`inline-flex items-center gap-2 ${className}`}>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border">
                Free
            </span>
            {showUpgradeButton && (
                <button
                    onClick={onUpgradeClick}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-gradient-to-r from-primary to-primary-hover text-primary-foreground hover:opacity-90 transition active:scale-95 shadow-xs"
                >
                    <Crown size={11} />
                    Upgrade
                </button>
            )}
        </div>
    );
};

export default PlanBadge;
