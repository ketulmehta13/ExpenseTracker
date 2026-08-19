import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Check, Crown, Sparkles, Shield, Zap,
    ArrowRight, Loader2, AlertCircle, HelpCircle, FileText
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { usePlan } from '../context/PlanContext';
import { createCheckoutSubscription } from '../services/api';

const loadRazorpayScript = () => {
    return new Promise((resolve) => {
        if (window.Razorpay) {
            resolve(true);
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://checkout.razorpay.com/v1/checkout.js';
        script.onload = () => resolve(true);
        script.onerror = () => resolve(false);
        document.body.appendChild(script);
    });
};

const FEATURES = [
    { name: 'Transaction History', free: 'Last 3 months', pro: 'Unlimited history' },
    { name: 'Custom Categories', free: 'Up to 5 categories', pro: 'Unlimited categories' },
    { name: 'CSV & Data Export', free: 'Not included', pro: 'Unlimited CSV / PDF export' },
    { name: 'AI Features (Auto-Categorization & Insights)', free: 'Not included', pro: 'Full access' },
    { name: 'Budget Alerts & Analytics', free: 'Basic overview', pro: 'Advanced breakdowns & alerts' },
    { name: 'Recurring Transactions', free: 'Basic', pro: 'Full automated tracking' },
    { name: 'Free Trial', free: '—', pro: '7 Days Free Trial' },
];

const Upgrade = () => {
    const { user } = useAuth();
    const { isPro, isTrialing, plan, refreshPlan } = usePlan();
    const navigate = useNavigate();

    const [billingCycle, setBillingCycle] = useState('yearly'); // 'monthly' | 'yearly'
    const [submitting, setSubmitting] = useState(false);
    const [paymentStatus, setPaymentStatus] = useState(null); // { success: boolean, message: string }

    const handleSubscribe = async (selectedCycle = billingCycle) => {
        if (!user) {
            navigate('/login');
            return;
        }

        setSubmitting(true);
        setPaymentStatus(null);

        try {
            // 1. Ensure Razorpay checkout script is loaded
            const scriptLoaded = await loadRazorpayScript();
            if (!scriptLoaded) {
                toast.error('Failed to load Razorpay checkout SDK. Please check your internet connection.');
                setSubmitting(false);
                return;
            }

            // 2. Call Edge Function to create subscription
            const session = await createCheckoutSubscription(selectedCycle);

            if (!session?.subscriptionId || !session?.keyId) {
                toast.error('Could not initialize subscription checkout.');
                setSubmitting(false);
                return;
            }

            // 3. Open Razorpay hosted checkout widget
            const options = {
                key: session.keyId,
                subscription_id: session.subscriptionId,
                name: 'Expense Tracker Pro',
                description: `Pro Plan (${selectedCycle === 'yearly' ? 'Yearly' : 'Monthly'}) — 7-Day Free Trial`,
                image: '/logo-icon.png',
                prefill: {
                    name: user?.user_metadata?.username || user?.email?.split('@')[0] || '',
                    email: user?.email || '',
                },
                theme: {
                    color: '#0d3a35',
                },
                handler: function (response) {
                    // Payment authorized on frontend. Webhook is the actual source of truth for activation.
                    setPaymentStatus({
                        success: true,
                        message: 'Payment authorized! Your Pro membership will activate in a few moments once verified by Razorpay.',
                    });
                    toast.success('Payment submitted! Refreshing your account…');
                    setTimeout(() => {
                        refreshPlan();
                    }, 2500);
                },
                modal: {
                    ondismiss: function () {
                        setSubmitting(false);
                    },
                },
            };

            const rzp = new window.Razorpay(options);
            rzp.on('payment.failed', function (response) {
                console.error('Razorpay payment failed:', response.error);
                toast.error(`Payment failed: ${response.error.description || 'Unknown error'}`);
                setSubmitting(false);
            });
            rzp.open();
        } catch (err) {
            console.error('Checkout error:', err);
            toast.error(err.message || 'An error occurred during checkout setup.');
            setSubmitting(false);
        }
    };

    return (
        <div className="max-w-5xl mx-auto space-y-8 page-enter pb-12">
            {/* Header */}
            <div className="text-center space-y-3 max-w-2xl mx-auto">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold border border-primary/20">
                    <Sparkles size={13} />
                    7-Day Free Trial Included
                </div>
                <h1 className="text-3xl sm:text-4xl font-extrabold font-display text-foreground tracking-tight">
                    Supercharge Your Financial Clarity
                </h1>
                <p className="text-sm sm:text-base text-muted-foreground">
                    Get unlimited history, unlimited categories, full CSV exports, and intelligent insights to stay on top of every rupee.
                </p>

                {/* Billing Cycle Switcher */}
                <div className="pt-2 flex items-center justify-center">
                    <div className="inline-flex items-center p-1 rounded-xl bg-muted border border-border">
                        <button
                            type="button"
                            onClick={() => setBillingCycle('monthly')}
                            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                                billingCycle === 'monthly'
                                    ? 'bg-card text-foreground shadow-xs'
                                    : 'text-muted-foreground hover:text-foreground'
                            }`}
                        >
                            Monthly Billing
                        </button>
                        <button
                            type="button"
                            onClick={() => setBillingCycle('yearly')}
                            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                                billingCycle === 'yearly'
                                    ? 'bg-card text-foreground shadow-xs'
                                    : 'text-muted-foreground hover:text-foreground'
                            }`}
                        >
                            <span>Annual Billing</span>
                            <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold">
                                Save 30%
                            </span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Payment status banner */}
            {paymentStatus && (
                <div className={`p-4 rounded-2xl border ${
                    paymentStatus.success
                        ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-800 dark:text-emerald-300'
                        : 'bg-destructive/10 border-destructive/25 text-destructive'
                } flex items-start gap-3`}>
                    <Sparkles size={18} className="flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-semibold">{paymentStatus.message}</p>
                        <p className="text-xs opacity-80 mt-0.5">
                            Status updates automatically via Razorpay secure webhooks.
                        </p>
                    </div>
                </div>
            )}

            {/* Pricing Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
                {/* Free Plan Card */}
                <div className="rounded-3xl border border-border bg-card p-6 sm:p-8 flex flex-col justify-between shadow-xs">
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-muted text-muted-foreground">
                                Starter
                            </span>
                            {!isPro && (
                                <span className="text-xs font-semibold text-primary">Current Plan</span>
                            )}
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold text-foreground">Free</h2>
                            <p className="text-xs text-muted-foreground mt-1">
                                Essential tracking tools for personal daily use.
                            </p>
                        </div>
                        <div className="flex items-baseline gap-1 py-2">
                            <span className="text-4xl font-extrabold text-foreground font-display">₹0</span>
                            <span className="text-xs text-muted-foreground font-medium">/ forever</span>
                        </div>

                        <div className="space-y-2.5 pt-4 border-t border-border">
                            <p className="text-xs font-semibold text-foreground uppercase tracking-wider">Includes:</p>
                            <ul className="space-y-2 text-xs text-muted-foreground">
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span>Last 3 months of transaction history</span>
                                </li>
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span>Up to 5 custom categories</span>
                                </li>
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span>Core dashboard & budget tracking</span>
                                </li>
                                <li className="flex items-center gap-2 text-muted-foreground/50">
                                    <span className="w-3.5 text-center font-bold">✕</span>
                                    <span>CSV / PDF Data Export</span>
                                </li>
                                <li className="flex items-center gap-2 text-muted-foreground/50">
                                    <span className="w-3.5 text-center font-bold">✕</span>
                                    <span>AI Auto-Categorization & Insights</span>
                                </li>
                            </ul>
                        </div>
                    </div>

                    <div className="pt-8">
                        <button
                            type="button"
                            disabled={true}
                            className="w-full py-2.5 rounded-xl border border-border text-xs font-semibold text-muted-foreground bg-muted/50 cursor-default"
                        >
                            {!isPro ? 'Your Active Plan' : 'Free Tier'}
                        </button>
                    </div>
                </div>

                {/* Pro Plan Card */}
                <div className="relative rounded-3xl border-2 border-primary bg-card p-6 sm:p-8 flex flex-col justify-between shadow-xl overflow-hidden">
                    <div className="absolute top-0 right-0 bg-primary text-primary-foreground text-[10px] font-bold px-4 py-1 rounded-bl-xl uppercase tracking-wider flex items-center gap-1">
                        <Crown size={11} />
                        Recommended
                    </div>

                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                                Pro Member
                            </span>
                            {isPro && (
                                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                                    Active ({isTrialing ? 'Trial' : plan})
                                </span>
                            )}
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold text-foreground">Pro Plan</h2>
                            <p className="text-xs text-muted-foreground mt-1">
                                Complete freedom, advanced analytics & smart AI tools.
                            </p>
                        </div>
                        <div className="flex items-baseline gap-1 py-2">
                            <span className="text-4xl font-extrabold text-foreground font-display">
                                {billingCycle === 'yearly' ? '₹2,499' : '₹299'}
                            </span>
                            <span className="text-xs text-muted-foreground font-medium">
                                {billingCycle === 'yearly' ? '/ year (₹208/mo)' : '/ month'}
                            </span>
                        </div>

                        <div className="p-3 rounded-xl bg-primary/5 border border-primary/15 text-xs text-foreground flex items-center gap-2">
                            <Zap size={15} className="text-primary flex-shrink-0" />
                            <span><strong>7 Days Free Trial</strong> — Cancel anytime with 1 click before day 7 without being charged.</span>
                        </div>

                        <div className="space-y-2.5 pt-2 border-t border-border">
                            <p className="text-xs font-semibold text-foreground uppercase tracking-wider">Everything in Free, plus:</p>
                            <ul className="space-y-2 text-xs text-foreground">
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span><strong>Unlimited</strong> transaction history (all-time)</span>
                                </li>
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span><strong>Unlimited</strong> custom categories</span>
                                </li>
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span>Full <strong>CSV & Financial Data Export</strong></span>
                                </li>
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span><strong>AI Assistant</strong> (Smart Auto-Categorization & Insights)</span>
                                </li>
                                <li className="flex items-center gap-2">
                                    <Check size={14} className="text-primary flex-shrink-0" />
                                    <span>Priority support & early access to new features</span>
                                </li>
                            </ul>
                        </div>
                    </div>

                    <div className="pt-8">
                        <button
                            type="button"
                            onClick={() => handleSubscribe(billingCycle)}
                            disabled={submitting || (isPro && !isTrialing)}
                            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm shadow-md hover:opacity-90 transition active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {submitting ? (
                                <>
                                    <Loader2 size={16} className="animate-spin" />
                                    Setting up checkout…
                                </>
                            ) : isPro ? (
                                'Manage Subscription in Settings'
                            ) : (
                                <>
                                    <span>Start 7-Day Free Trial</span>
                                    <ArrowRight size={16} />
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* Feature Comparison Table */}
            <div className="rounded-3xl border border-border bg-card p-6 sm:p-8 shadow-xs max-w-4xl mx-auto space-y-6">
                <div>
                    <h3 className="text-lg font-bold text-foreground">Compare Plans</h3>
                    <p className="text-xs text-muted-foreground">Detailed breakdown of features across tiers.</p>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs border-collapse">
                        <thead>
                            <tr className="border-b border-border">
                                <th className="py-3 px-4 font-semibold text-foreground">Feature</th>
                                <th className="py-3 px-4 font-semibold text-muted-foreground w-1/3">Free</th>
                                <th className="py-3 px-4 font-semibold text-primary w-1/3">Pro</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {FEATURES.map((feat, idx) => (
                                <tr key={idx} className="hover:bg-muted/30 transition-colors">
                                    <td className="py-3 px-4 font-medium text-foreground">{feat.name}</td>
                                    <td className="py-3 px-4 text-muted-foreground">{feat.free}</td>
                                    <td className="py-3 px-4 font-semibold text-foreground flex items-center gap-1.5">
                                        <Check size={13} className="text-primary" />
                                        <span>{feat.pro}</span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Security & FAQ Footer */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-4xl mx-auto pt-4 text-center">
                <div className="flex flex-col items-center p-4 rounded-2xl border border-border bg-card">
                    <Shield size={20} className="text-primary mb-2" />
                    <h4 className="text-xs font-bold text-foreground">Bank-Grade Security</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        Payments handled directly by Razorpay (PCI-DSS Level 1 compliant).
                    </p>
                </div>
                <div className="flex flex-col items-center p-4 rounded-2xl border border-border bg-card">
                    <Zap size={20} className="text-primary mb-2" />
                    <h4 className="text-xs font-bold text-foreground">7-Day Free Trial</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        Test all Pro features with zero risk. Cancel anytime with 1 click.
                    </p>
                </div>
                <div className="flex flex-col items-center p-4 rounded-2xl border border-border bg-card">
                    <HelpCircle size={20} className="text-primary mb-2" />
                    <h4 className="text-xs font-bold text-foreground">Cancel Anytime</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        Retain access until the end of your billing cycle.
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Upgrade;
