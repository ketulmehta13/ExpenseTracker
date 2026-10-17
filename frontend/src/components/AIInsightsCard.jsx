import React, { useState, useEffect, useCallback } from 'react';
import { Sparkles, Loader2, RefreshCw, Lightbulb } from 'lucide-react';
import { getAIInsight, saveAIInsight } from '../services/api';
import { getMonthlyInsight } from '../services/aiService';
import { useAuth } from '../context/AuthContext';
import { Skeleton } from './ui/Skeleton';

/**
 * AIInsightsCard — shows a cached or on-demand AI-generated monthly insight.
 *
 * Props:
 *   summary    — computeSummary() output (must include current_month, previous_month, category_breakdown)
 *   month      — 'YYYY-MM' string for the current month (used as cache key)
 */
const AIInsightsCard = ({ summary, month }) => {
    const { user } = useAuth();

    const [insight, setInsight] = useState('');
    const [generatedAt, setGeneratedAt] = useState(null);
    const [loading, setLoading] = useState(true);    // initial cache fetch
    const [generating, setGenerating] = useState(false); // on-demand generation
    const [error, setError] = useState('');

    // Fetch cached insight on mount
    const fetchCached = useCallback(async () => {
        if (!user?.id || !month) return;
        setLoading(true);
        try {
            const cached = await getAIInsight(user.id, month);
            if (cached) {
                setInsight(cached.insight);
                setGeneratedAt(cached.generated_at);
            }
        } catch {
            // Silently ignore — user will see the Generate button
        } finally {
            setLoading(false);
        }
    }, [user?.id, month]);

    useEffect(() => { fetchCached(); }, [fetchCached]);

    const generate = async () => {
        if (!summary || !user?.id) return;
        setGenerating(true);
        setError('');

        try {
            // Build a compact payload — aggregated totals only, no raw rows
            const topCategories = (summary.category_breakdown ?? [])
                .sort((a, b) => b.total - a.total)
                .slice(0, 5)
                .map((c) => ({ name: c.category__name || c.name, total: c.total }));

            const payload = {
                currentMonth: {
                    income: summary.current_month.income,
                    expense: summary.current_month.expense,
                    balance: summary.current_month.balance,
                    topCategories,
                },
                previousMonth: {
                    income: summary.previous_month.income,
                    expense: summary.previous_month.expense,
                },
                month,
            };

            const result = await getMonthlyInsight(payload);

            if (!result || !result.insight) {
                setError('AI insights are not available right now. Please check back later.');
                return;
            }

            // Save to cache
            await saveAIInsight(user.id, month, result.insight);
            setInsight(result.insight);
            setGeneratedAt(new Date().toISOString());
        } catch (err) {
            setError(err.message || 'Failed to generate insight. Please try again.');
        } finally {
            setGenerating(false);
        }
    };

    const formatDate = (iso) => {
        if (!iso) return '';
        return new Date(iso).toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border bg-gradient-to-r from-primary/5 to-transparent">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                    <Lightbulb size={15} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-foreground leading-none">AI Insights</h3>
                    <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                        {generatedAt ? `Generated ${formatDate(generatedAt)}` : 'Your monthly financial summary'}
                    </p>
                </div>
                <div className="flex items-center gap-1.5">
                    {insight && (
                        <button
                            onClick={generate}
                            disabled={generating}
                            title="Regenerate insight"
                            className="flex items-center justify-center h-7 w-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                        >
                            <RefreshCw size={13} className={generating ? 'animate-spin' : ''} />
                        </button>
                    )}
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground/60 font-medium">
                        <Sparkles size={9} className="text-primary/60" />
                        Powered by AI
                    </div>
                </div>
            </div>

            {/* Body */}
            <div className="px-5 py-4">
                {loading ? (
                    <div className="space-y-2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-5/6" />
                        <Skeleton className="h-4 w-4/6" />
                    </div>
                ) : generating ? (
                    <div className="flex items-center gap-3 text-sm text-muted-foreground py-2">
                        <Loader2 size={16} className="animate-spin text-primary flex-shrink-0" />
                        <div>
                            <p className="font-medium text-foreground">Generating your insight…</p>
                            <p className="text-xs mt-0.5">Analyzing your transactions, this takes a few seconds.</p>
                        </div>
                    </div>
                ) : error ? (
                    <div className="space-y-3">
                        <p className="text-sm text-muted-foreground">{error}</p>
                        <button
                            onClick={generate}
                            className="text-xs text-primary hover:underline font-medium"
                        >
                            Try again
                        </button>
                    </div>
                ) : insight ? (
                    <p className="text-sm text-foreground leading-relaxed">{insight}</p>
                ) : (
                    <div className="space-y-3">
                        <p className="text-sm text-muted-foreground">
                            Get a personalized 2–4 sentence summary of your spending patterns, trends vs last month, and actionable tips.
                        </p>
                        <button
                            onClick={generate}
                            disabled={generating}
                            className="flex items-center gap-2 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary px-4 py-2 text-sm font-semibold transition-colors disabled:opacity-50"
                        >
                            <Sparkles size={13} />
                            Generate Insights
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default AIInsightsCard;
