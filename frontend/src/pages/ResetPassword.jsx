import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Loader2, Eye, EyeOff, ArrowLeft, KeyRound, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { authChangePassword } from '../services/api';
import { getAuthErrorMessage } from '../lib/authErrors';
import logoIcon from '../assets/logo-icon.webp';

const MIN_PASSWORD_LENGTH = 6;

// An expired or already-used reset link comes back with error details in the URL
const getLinkError = () => {
    const params = new URLSearchParams(window.location.hash.slice(1) || window.location.search);
    return params.get('error_description');
};

/**
 * ResetPassword — target of the password-reset email link.
 * Opening a valid link signs the user in with a recovery session, so having a
 * session here means the link worked and a new password can be set.
 */
const ResetPassword = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [linkError] = useState(getLinkError);
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [errors, setErrors] = useState({});
    const [isLoading, setIsLoading] = useState(false);

    const canReset = Boolean(user) && !linkError;

    const handleSubmit = async (e) => {
        e.preventDefault();
        const errs = {};
        if (password.length < MIN_PASSWORD_LENGTH) {
            errs.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
        }
        if (password !== confirmPassword) errs.confirmPassword = 'Passwords do not match.';
        if (Object.keys(errs).length) {
            setErrors(errs);
            return;
        }

        setIsLoading(true);
        try {
            await authChangePassword(password);
            toast.success('Password updated. You are now signed in.');
            navigate('/dashboard', { replace: true });
        } catch (err) {
            toast.error(getAuthErrorMessage(err, 'Could not update your password. Please try again.'));
        } finally {
            setIsLoading(false);
        }
    };

    const inputClass = (hasError) =>
        `w-full rounded-xl border bg-card px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 transition ${
            hasError ? 'border-destructive focus:ring-destructive/30' : 'border-border focus:ring-ring/40 focus:border-ring'
        }`;

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            <div className="w-full max-w-sm">
                {/* Logo */}
                <div className="mb-8 flex flex-col items-center">
                    <img src={logoIcon} alt="Expense Tracker" className="h-12 w-12 rounded-xl object-contain mb-3" />
                    <span className="font-display text-lg font-semibold text-foreground">Expense Tracker</span>
                </div>

                {!canReset ? (
                    <div className="text-center space-y-4">
                        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-expense/10 text-expense">
                            <AlertTriangle size={32} />
                        </div>
                        <h2 className="font-display text-2xl font-bold text-foreground">Link expired</h2>
                        <p className="text-sm text-muted-foreground">
                            This password reset link is invalid or has already been used. Request a new one to continue.
                        </p>
                        <div className="flex flex-col items-center gap-3 pt-2">
                            <Link
                                to="/forgot-password"
                                className="w-full flex items-center justify-center rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90"
                            >
                                Request a new link
                            </Link>
                            <Link
                                to="/login"
                                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
                            >
                                <ArrowLeft size={14} />
                                Back to login
                            </Link>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="mb-7">
                            <h2 className="font-display text-3xl font-bold text-foreground">Set a new password</h2>
                            <p className="mt-1 text-sm text-muted-foreground">
                                Choose a new password for <strong className="text-foreground">{user.email}</strong>.
                            </p>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                            <div>
                                <label htmlFor="rp-password" className="block text-sm font-medium text-foreground mb-1.5">
                                    New password
                                </label>
                                <div className="relative">
                                    <input
                                        id="rp-password"
                                        type={showPassword ? 'text' : 'password'}
                                        autoComplete="new-password"
                                        value={password}
                                        onChange={(e) => {
                                            setPassword(e.target.value);
                                            setErrors((prev) => ({ ...prev, password: undefined }));
                                        }}
                                        placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
                                        className={`${inputClass(errors.password)} pr-12`}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword((v) => !v)}
                                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1"
                                    >
                                        {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                                    </button>
                                </div>
                                {errors.password && <p className="mt-1 text-xs text-destructive">{errors.password}</p>}
                            </div>

                            <div>
                                <label htmlFor="rp-confirm" className="block text-sm font-medium text-foreground mb-1.5">
                                    Confirm new password
                                </label>
                                <input
                                    id="rp-confirm"
                                    type={showPassword ? 'text' : 'password'}
                                    autoComplete="new-password"
                                    value={confirmPassword}
                                    onChange={(e) => {
                                        setConfirmPassword(e.target.value);
                                        setErrors((prev) => ({ ...prev, confirmPassword: undefined }));
                                    }}
                                    placeholder="Repeat the new password"
                                    className={inputClass(errors.confirmPassword)}
                                />
                                {errors.confirmPassword && (
                                    <p className="mt-1 text-xs text-destructive">{errors.confirmPassword}</p>
                                )}
                            </div>

                            <button
                                type="submit"
                                disabled={isLoading}
                                className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-60"
                            >
                                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
                                {isLoading ? 'Updating…' : 'Update password'}
                            </button>
                        </form>
                    </>
                )}
            </div>
        </div>
    );
};

export default ResetPassword;
