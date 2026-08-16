import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2, Eye, EyeOff, TrendingUp, PieChart, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import logoIcon from '../assets/logo-icon.png';

const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        try {
            await login(email, password);
            toast.success('Welcome back! 👋');
            navigate('/dashboard');
        } catch (err) {
            toast.error(err.message || 'Invalid email or password');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex bg-background">
            {/* ── LEFT PANEL — branded (desktop) ── */}
            <div className="hidden lg:flex flex-col justify-between w-1/2 bg-sidebar p-12 relative overflow-hidden">
                {/* Decorative circles */}
                <div className="absolute top-[-10%] right-[-10%] w-72 h-72 rounded-full bg-income/10 blur-[80px]" />
                <div className="absolute bottom-[-10%] left-[-10%] w-72 h-72 rounded-full bg-expense/10 blur-[80px]" />

                {/* Logo */}
                <div className="flex items-center gap-3 relative z-10">
                    <img src={logoIcon} alt="Expense Tracker" className="h-10 w-10 rounded-xl object-contain" />
                    <span className="font-display text-xl font-semibold text-white">Expense Tracker</span>
                </div>

                {/* Hero text */}
                <div className="relative z-10 space-y-6">
                    <div>
                        <p className="text-white/50 text-sm font-medium tracking-widest uppercase mb-3">
                            ✦ All-in-one
                        </p>
                        <h1 className="font-display text-5xl font-bold text-white leading-tight">
                            No spreadsheets.<br />
                            <span className="text-expense italic">Just clarity.</span>
                        </h1>
                        <p className="mt-4 text-white/60 text-base leading-relaxed max-w-xs">
                            Track income, manage expenses, and grow your savings — all in one beautiful dashboard.
                        </p>
                    </div>

                    {/* Feature pills */}
                    <div className="space-y-3">
                        {[
                            { icon: TrendingUp, label: 'Track every rupee' },
                            { icon: PieChart, label: 'Visual analytics & reports' },
                            { icon: ShieldCheck, label: 'Secure & private — your data stays yours' },
                        ].map(({ icon: Icon, label }) => (
                            <div key={label} className="flex items-center gap-3 text-white/70">
                                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                                    <Icon size={16} className="text-expense" />
                                </div>
                                <span className="text-sm">{label}</span>
                            </div>
                        ))}
                    </div>
                </div>

                <p className="relative z-10 text-white/30 text-xs">© 2026 Expense Tracker by Ketul Mehta</p>
            </div>

            {/* ── RIGHT PANEL — form ── */}
            <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
                {/* Mobile logo */}
                <div className="mb-8 flex flex-col items-center lg:hidden">
                    <img src={logoIcon} alt="Expense Tracker" className="h-12 w-12 rounded-xl object-contain mb-3" />
                    <h1 className="font-display text-2xl font-bold text-foreground">Expense Tracker</h1>
                </div>

                <div className="w-full max-w-sm">
                    <div className="mb-7">
                        <h2 className="font-display text-3xl font-bold text-foreground">Welcome back</h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Sign in to your account to continue
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                        {/* Email */}
                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-foreground mb-1.5">
                                Email address
                            </label>
                            <input
                                id="email"
                                type="email"
                                required
                                autoComplete="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="you@example.com"
                                className="w-full rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/40 focus:border-ring transition"
                            />
                        </div>

                        {/* Password */}
                        <div>
                            <div className="flex items-center justify-between mb-1.5">
                                <label htmlFor="password" className="block text-sm font-medium text-foreground">
                                    Password
                                </label>
                                <Link
                                    to="/forgot-password"
                                    className="text-xs text-primary hover:text-primary/80 font-medium transition-colors"
                                >
                                    Forgot password?
                                </Link>
                            </div>
                            <div className="relative">
                                <input
                                    id="password"
                                    type={showPassword ? 'text' : 'password'}
                                    required
                                    autoComplete="current-password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="Enter your password"
                                    className="w-full rounded-xl border border-border bg-card px-4 py-3 pr-12 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/40 focus:border-ring transition"
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
                        </div>

                        {/* Submit */}
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="mt-2 w-full flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-60 active:scale-[.98]"
                        >
                            {isLoading && <Loader2 size={16} className="animate-spin" />}
                            {isLoading ? 'Signing in…' : 'Sign in'}
                        </button>
                    </form>

                    <p className="mt-6 text-center text-sm text-muted-foreground">
                        Don't have an account?{' '}
                        <Link to="/register" className="font-semibold text-primary hover:text-primary/80 transition-colors">
                            Create one
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Login;
