import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2, Eye, EyeOff, TrendingUp, PieChart, ShieldCheck, Check } from 'lucide-react';
import { toast } from 'sonner';
import logoIcon from '../assets/logo-icon.png';

const passwordStrength = (pwd) => {
    if (pwd.length < 6) return { score: 0, label: 'Too short', color: 'bg-destructive' };
    if (pwd.length < 8) return { score: 1, label: 'Weak', color: 'bg-expense' };
    const hasUpper = /[A-Z]/.test(pwd);
    const hasNumber = /[0-9]/.test(pwd);
    const hasSpecial = /[^A-Za-z0-9]/.test(pwd);
    const score = 1 + (hasUpper ? 1 : 0) + (hasNumber ? 1 : 0) + (hasSpecial ? 1 : 0);
    if (score >= 4) return { score: 3, label: 'Strong', color: 'bg-income' };
    if (score >= 3) return { score: 2, label: 'Fair', color: 'bg-expense' };
    return { score: 1, label: 'Weak', color: 'bg-destructive' };
};

const Register = () => {
    const [username, setUsername] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [fieldErrors, setFieldErrors] = useState({});
    const { register } = useAuth();
    const navigate = useNavigate();

    const strength = passwordStrength(password);

    const validate = () => {
        const errs = {};
        if (!/^[\w.@+-]{3,20}$/.test(username))
            errs.username = 'Username must be 3-20 chars (letters, numbers, @.+_-)';
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
            errs.email = 'Enter a valid email address';
        if (password.length < 6)
            errs.password = 'Password must be at least 6 characters';
        return errs;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        const errs = validate();
        if (Object.keys(errs).length) {
            setFieldErrors(errs);
            return;
        }
        setIsLoading(true);
        try {
            await register(username, email, password);
            toast.success('Account created! Welcome aboard 🎉');
            navigate('/dashboard');
        } catch (err) {
            toast.error(err.message || 'Registration failed. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const field = (key) => ({
        onChange: (e) => {
            setFieldErrors((prev) => ({ ...prev, [key]: undefined }));
            if (key === 'username') setUsername(e.target.value);
            if (key === 'email') setEmail(e.target.value);
            if (key === 'password') setPassword(e.target.value);
        },
        className: `w-full rounded-xl border px-4 py-3 text-sm bg-card text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 transition ${
            fieldErrors[key]
                ? 'border-destructive focus:ring-destructive/30'
                : 'border-border focus:ring-ring/40 focus:border-ring'
        }`,
    });

    return (
        <div className="min-h-screen flex bg-background">
            {/* ── LEFT PANEL ── */}
            <div className="hidden lg:flex flex-col justify-between w-1/2 bg-sidebar p-12 relative overflow-hidden">
                <div className="absolute top-[-10%] right-[-10%] w-72 h-72 rounded-full bg-income/10 blur-[80px]" />
                <div className="absolute bottom-[-10%] left-[-10%] w-72 h-72 rounded-full bg-expense/10 blur-[80px]" />

                <div className="flex items-center gap-3 relative z-10">
                    <img src={logoIcon} alt="Expense Tracker" className="h-10 w-10 rounded-xl object-contain" />
                    <span className="font-display text-xl font-semibold text-white">Expense Tracker</span>
                </div>

                <div className="relative z-10 space-y-6">
                    <div>
                        <p className="text-white/50 text-sm font-medium tracking-widest uppercase mb-3">
                            ✦ Join today
                        </p>
                        <h1 className="font-display text-5xl font-bold text-white leading-tight">
                            Start tracking.<br />
                            <span className="text-income italic">Start growing.</span>
                        </h1>
                        <p className="mt-4 text-white/60 text-base leading-relaxed max-w-xs">
                            Create a free account and take control of your finances in minutes.
                        </p>
                    </div>
                    <div className="space-y-3">
                        {[
                            'Free forever — no subscriptions',
                            'Beautiful analytics at a glance',
                            'Your data, encrypted and private',
                        ].map((feat) => (
                            <div key={feat} className="flex items-center gap-3 text-white/70">
                                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-income/20">
                                    <Check size={13} className="text-income" />
                                </div>
                                <span className="text-sm">{feat}</span>
                            </div>
                        ))}
                    </div>
                </div>

                <p className="relative z-10 text-white/30 text-xs">© 2026 Expense Tracker by Ketul Mehta</p>
            </div>

            {/* ── RIGHT PANEL ── */}
            <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
                <div className="mb-8 flex flex-col items-center lg:hidden">
                    <img src={logoIcon} alt="Expense Tracker" className="h-12 w-12 rounded-xl object-contain mb-3" />
                    <h1 className="font-display text-2xl font-bold text-foreground">Expense Tracker</h1>
                </div>

                <div className="w-full max-w-sm">
                    <div className="mb-7">
                        <h2 className="font-display text-3xl font-bold text-foreground">Create account</h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Start tracking your expenses today — it's free.
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                        {/* Username */}
                        <div>
                            <label htmlFor="username" className="block text-sm font-medium text-foreground mb-1.5">
                                Username
                            </label>
                            <input
                                id="username"
                                type="text"
                                required
                                autoComplete="username"
                                value={username}
                                placeholder="Choose a username"
                                {...field('username')}
                            />
                            {fieldErrors.username && (
                                <p className="mt-1 text-xs text-destructive">{fieldErrors.username}</p>
                            )}
                        </div>

                        {/* Email */}
                        <div>
                            <label htmlFor="reg-email" className="block text-sm font-medium text-foreground mb-1.5">
                                Email address
                            </label>
                            <input
                                id="reg-email"
                                type="email"
                                required
                                autoComplete="email"
                                value={email}
                                placeholder="you@example.com"
                                {...field('email')}
                            />
                            {fieldErrors.email && (
                                <p className="mt-1 text-xs text-destructive">{fieldErrors.email}</p>
                            )}
                        </div>

                        {/* Password */}
                        <div>
                            <label htmlFor="reg-password" className="block text-sm font-medium text-foreground mb-1.5">
                                Password
                            </label>
                            <div className="relative">
                                <input
                                    id="reg-password"
                                    type={showPassword ? 'text' : 'password'}
                                    required
                                    autoComplete="new-password"
                                    value={password}
                                    placeholder="Create a password (min. 6 chars)"
                                    {...field('password')}
                                    className={field('password').className + ' pr-12'}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword((v) => !v)}
                                    tabIndex={-1}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1"
                                >
                                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                                </button>
                            </div>
                            {/* Strength bar */}
                            {password.length > 0 && (
                                <div className="mt-2">
                                    <div className="flex gap-1 h-1.5 mb-1">
                                        {[1, 2, 3].map((i) => (
                                            <div
                                                key={i}
                                                className={`flex-1 rounded-full transition-all ${i <= strength.score ? strength.color : 'bg-muted'}`}
                                            />
                                        ))}
                                    </div>
                                    <p className="text-xs text-muted-foreground">{strength.label}</p>
                                </div>
                            )}
                            {fieldErrors.password && (
                                <p className="mt-1 text-xs text-destructive">{fieldErrors.password}</p>
                            )}
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading}
                            className="mt-2 w-full flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-60 active:scale-[.98]"
                        >
                            {isLoading && <Loader2 size={16} className="animate-spin" />}
                            {isLoading ? 'Creating account…' : 'Create account'}
                        </button>
                    </form>

                    <p className="mt-6 text-center text-sm text-muted-foreground">
                        Already have an account?{' '}
                        <Link to="/login" className="font-semibold text-primary hover:text-primary/80 transition-colors">
                            Sign in
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Register;