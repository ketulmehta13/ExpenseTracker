import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Mail, ArrowLeft, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '../services/supabaseClient';
import logoIcon from '../assets/logo-icon.png';

// TODO: Ensure Supabase email templates are configured in the Supabase dashboard
// (Authentication → Email Templates → Reset Password) for this flow to deliver emails.

const ForgotPassword = () => {
    const [email, setEmail] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sent, setSent] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        try {
            const { error } = await supabase.auth.resetPasswordForEmail(email.toLowerCase(), {
                redirectTo: `${window.location.origin}/reset-password`,
            });
            if (error) throw error;
            setSent(true);
            toast.success('Reset email sent! Check your inbox.');
        } catch (err) {
            toast.error(err.message || 'Failed to send reset email. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            <div className="w-full max-w-sm">
                {/* Logo */}
                <div className="mb-8 flex flex-col items-center">
                    <img src={logoIcon} alt="Expense Tracker" className="h-12 w-12 rounded-xl object-contain mb-3" />
                    <span className="font-display text-lg font-semibold text-foreground">Expense Tracker</span>
                </div>

                {sent ? (
                    <div className="text-center space-y-4">
                        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-income/10 text-income">
                            <CheckCircle2 size={32} />
                        </div>
                        <h2 className="font-display text-2xl font-bold text-foreground">Check your email</h2>
                        <p className="text-sm text-muted-foreground">
                            We sent a password reset link to <strong className="text-foreground">{email}</strong>.
                            It may take a minute to arrive.
                        </p>
                        <Link
                            to="/login"
                            className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary/80 transition-colors mt-2"
                        >
                            <ArrowLeft size={15} />
                            Back to login
                        </Link>
                    </div>
                ) : (
                    <>
                        <div className="mb-7">
                            <h2 className="font-display text-3xl font-bold text-foreground">Forgot password?</h2>
                            <p className="mt-1 text-sm text-muted-foreground">
                                Enter your email and we'll send you a reset link.
                            </p>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                            <div>
                                <label htmlFor="fp-email" className="block text-sm font-medium text-foreground mb-1.5">
                                    Email address
                                </label>
                                <div className="relative">
                                    <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                                    <input
                                        id="fp-email"
                                        type="email"
                                        required
                                        autoComplete="email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        placeholder="you@example.com"
                                        className="w-full rounded-xl border border-border bg-card pl-10 pr-4 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/40 focus:border-ring transition"
                                    />
                                </div>
                            </div>

                            <button
                                type="submit"
                                disabled={isLoading || !email}
                                className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-60"
                            >
                                {isLoading && <Loader2 size={16} className="animate-spin" />}
                                {isLoading ? 'Sending…' : 'Send reset link'}
                            </button>
                        </form>

                        <div className="mt-6 text-center">
                            <Link
                                to="/login"
                                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
                            >
                                <ArrowLeft size={14} />
                                Back to login
                            </Link>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};

export default ForgotPassword;
