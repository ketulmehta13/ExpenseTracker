import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Loader2, MailCheck } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../context/AuthContext';
import { getAuthErrorMessage } from '../../lib/authErrors';

const RESEND_WAIT_SECONDS = 60; // Supabase sends at most one email a minute to an address

/**
 * Confirm an email address with the code Supabase sent to it. A correct code signs the user
 * in, then `onVerified` runs. Used after sign-up, and when someone signs in before confirming.
 */
const EmailCodeForm = ({ email, onVerified, onBack, backLabel = 'Back' }) => {
    const { verifyEmailCode, resendEmailCode } = useAuth();
    const [code, setCode] = useState('');
    const [verifying, setVerifying] = useState(false);
    const [error, setError] = useState('');
    const [wait, setWait] = useState(RESEND_WAIT_SECONDS); // an email was just sent
    const inputRef = useRef(null);

    useEffect(() => { inputRef.current?.focus(); }, []);
    useEffect(() => {
        if (wait <= 0) return undefined;
        const timer = setTimeout(() => setWait((s) => s - 1), 1000);
        return () => clearTimeout(timer);
    }, [wait]);

    const digits = code.replace(/\D/g, '');
    // Supabase sends 6 digits by default; the length can be set up to 10 in the dashboard
    const complete = digits.length >= 6;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!complete) return;
        setVerifying(true);
        setError('');
        try {
            await verifyEmailCode(email, digits);
            onVerified?.();
        } catch (err) {
            setError(getAuthErrorMessage(err, "That code didn't work. Please try again."));
            setVerifying(false);
        }
    };

    const handleResend = async () => {
        setWait(RESEND_WAIT_SECONDS);
        setError('');
        setCode('');
        try {
            await resendEmailCode(email);
            toast.success(`A new code is on its way to ${email}.`);
        } catch (err) {
            toast.error(getAuthErrorMessage(err, "Couldn't send a new code. Please try again in a minute."));
        }
        inputRef.current?.focus();
    };

    return (
        <div className="w-full max-w-sm">
            <div className="mb-6 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-income/10 text-income">
                    <MailCheck size={32} />
                </div>
                <h2 className="font-display text-2xl font-bold text-foreground">Check your email</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                    We sent a code to <strong className="text-foreground break-all">{email}</strong>.
                    Enter it below to confirm your account.
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                <div>
                    <label htmlFor="email-code" className="block text-sm font-medium text-foreground mb-1.5">
                        Confirmation code
                    </label>
                    <input
                        ref={inputRef}
                        id="email-code"
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={10}
                        value={code}
                        onChange={(e) => { setCode(e.target.value.replace(/\D/g, '')); setError(''); }}
                        placeholder="123456"
                        aria-invalid={Boolean(error)}
                        aria-describedby={error ? 'email-code-error' : undefined}
                        className={`w-full rounded-xl border bg-card px-4 py-3 text-center text-2xl font-semibold tracking-[0.4em] text-foreground placeholder:text-muted-foreground/40 outline-none focus:ring-2 transition shadow-sm ${
                            error ? 'border-destructive focus:ring-destructive/30' : 'border-border focus:ring-ring/30 focus:border-ring'
                        }`}
                    />
                    {error && <p id="email-code-error" className="mt-1.5 text-xs text-destructive">{error}</p>}
                </div>

                <button
                    type="submit"
                    disabled={!complete || verifying}
                    className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/25 transition hover:opacity-95 active:scale-[.98] disabled:opacity-60"
                >
                    {verifying && <Loader2 size={16} className="animate-spin" />}
                    {verifying ? 'Checking…' : 'Verify and continue'}
                </button>
            </form>

            <div className="mt-5 text-center text-sm text-muted-foreground space-y-3">
                <p>
                    Didn't get it? Check your spam folder, or{' '}
                    {wait > 0 ? (
                        <span>send a new code in {wait}s.</span>
                    ) : (
                        <button type="button" onClick={handleResend} className="font-semibold text-primary hover:underline">
                            send a new code
                        </button>
                    )}
                </p>
                <button
                    type="button"
                    onClick={onBack}
                    className="inline-flex items-center gap-2 font-medium text-primary hover:text-primary/80 transition-colors"
                >
                    <ArrowLeft size={15} />
                    {backLabel}
                </button>
            </div>
        </div>
    );
};

export default EmailCodeForm;
