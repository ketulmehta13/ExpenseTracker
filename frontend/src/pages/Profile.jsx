import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import {
    Loader2, Save, Camera, Eye, EyeOff, Download,
    Shield, User, Palette, Database, AlertTriangle,
    Mail, Phone, BadgeCheck
} from 'lucide-react';
import { getProfile, updateProfile, getTransactions, computeSummary, authChangePassword, exportTransactionsCSV } from '../services/api';
import { formatCurrency } from '../lib/formatters';
import { Skeleton } from '../components/ui/Skeleton';
import ConfirmModal from '../components/ConfirmModal';

/* ── Section wrapper ── */
const Section = ({ title, icon: Icon, children }) => (
    <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-2.5 border-b border-border px-5 py-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
                <Icon size={16} className="text-muted-foreground" />
            </div>
            <h2 className="font-semibold text-foreground">{title}</h2>
        </div>
        <div className="p-5">{children}</div>
    </div>
);

/* ── Input field ── */
const Field = ({ label, id, error, children }) => (
    <div>
        <label htmlFor={id} className="block text-sm font-medium text-foreground mb-1.5">{label}</label>
        {children}
        {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
);

const inputCls = (err) =>
    `w-full rounded-xl border px-3.5 py-2.5 text-sm bg-background text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 transition ${
        err ? 'border-destructive focus:ring-destructive/30' : 'border-border focus:ring-ring/30 focus:border-ring'
    }`;

const CURRENCY_OPTIONS = [
    { code: 'INR', label: '₹ Indian Rupee' },
    { code: 'USD', label: '$ US Dollar' },
    { code: 'EUR', label: '€ Euro' },
    { code: 'GBP', label: '£ British Pound' },
    { code: 'JPY', label: '¥ Japanese Yen' },
    { code: 'CAD', label: 'C$ Canadian Dollar' },
    { code: 'AUD', label: 'A$ Australian Dollar' },
];

const Profile = () => {
    const { user, logout } = useAuth();
    const fileInputRef = useRef(null);

    const [loading, setLoading] = useState(true);
    const [userData, setUserData] = useState(null);
    const [summary, setSummary] = useState(null);

    /* Profile form */
    const [form, setForm] = useState({ first_name: '', last_name: '', phone: '' });
    const [saving, setSaving] = useState(false);
    const [photoPreview, setPhotoPreview] = useState(null);

    /* Password form */
    const [pwForm, setPwForm] = useState({ new_password: '', confirm_password: '' });
    const [pwSaving, setPwSaving] = useState(false);
    const [showPw, setShowPw] = useState(false);
    const [pwErrors, setPwErrors] = useState({});

    /* Budget */
    const [budget, setBudget] = useState('');
    const [budgetSaving, setBudgetSaving] = useState(false);

    /* Preferences */
    const [currency, setCurrency] = useState(() => localStorage.getItem('et-currency') || 'INR');
    const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'));

    /* Danger zone */
    const [deleteModal, setDeleteModal] = useState(false);
    const [deleteInput, setDeleteInput] = useState('');
    const [deleteLoading, setDeleteLoading] = useState(false);

    /* ── Fetch data ── */
    useEffect(() => {
        (async () => {
            try {
                const [profileData, transactions] = await Promise.all([
                    getProfile(user.id),
                    getTransactions(),
                ]);
                setUserData(profileData);
                setSummary(computeSummary(transactions, profileData.monthly_budget));
                setForm({
                    first_name: profileData.first_name || '',
                    last_name: profileData.last_name || '',
                    phone: profileData.phone || '',
                });
                setBudget(profileData.monthly_budget ?? '');
                if (profileData.profile_photo) setPhotoPreview(profileData.profile_photo);
            } catch {
                toast.error('Failed to load profile.');
            } finally {
                setLoading(false);
            }
        })();
    }, [user]);

    const handlePhotoChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onloadend = () => setPhotoPreview(reader.result);
        reader.readAsDataURL(file);
    };

    /* ── Save profile ── */
    const handleSaveProfile = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await updateProfile(user.id, {
                first_name: form.first_name.trim(),
                last_name: form.last_name.trim(),
                phone: form.phone.trim(),
                profile_photo: photoPreview || null,
            });
            toast.success('Profile updated!');
        } catch (err) {
            toast.error(err.message || 'Failed to update profile.');
        } finally {
            setSaving(false);
        }
    };

    /* ── Save budget ── */
    const handleSaveBudget = async (e) => {
        e.preventDefault();
        setBudgetSaving(true);
        try {
            await updateProfile(user.id, { monthly_budget: parseFloat(budget) || 0 });
            toast.success('Budget updated!');
        } catch (err) {
            toast.error(err.message || 'Failed to update budget.');
        } finally {
            setBudgetSaving(false);
        }
    };

    /* ── Change password ── */
    const handleChangePassword = async (e) => {
        e.preventDefault();
        const errs = {};
        if (pwForm.new_password.length < 6) errs.new_password = 'Password must be at least 6 characters.';
        if (pwForm.new_password !== pwForm.confirm_password) errs.confirm_password = 'Passwords do not match.';
        if (Object.keys(errs).length) { setPwErrors(errs); return; }
        setPwSaving(true);
        try {
            await authChangePassword(pwForm.new_password);
            toast.success('Password changed!');
            setPwForm({ new_password: '', confirm_password: '' });
            setPwErrors({});
        } catch (err) {
            toast.error(err.message || 'Failed to change password.');
        } finally {
            setPwSaving(false);
        }
    };

    /* ── Preferences ── */
    const handleCurrencyChange = (code) => {
        setCurrency(code);
        localStorage.setItem('et-currency', code);
        toast.success(`Currency set to ${code}`);
    };

    const handleThemeToggle = () => {
        document.documentElement.classList.toggle('dark');
        const newDark = document.documentElement.classList.contains('dark');
        setIsDark(newDark);
        localStorage.setItem('et-theme', newDark ? 'dark' : 'light');
        toast.success(`${newDark ? 'Dark' : 'Light'} mode enabled`);
    };

    /* ── Export ── */
    const handleExportCSV = async () => {
        try {
            const txs = await getTransactions();
            exportTransactionsCSV(txs);
            toast.success('CSV exported!');
        } catch {
            toast.error('Failed to export.');
        }
    };

    /* ── Delete account ── */
    const handleDeleteAccount = async () => {
        if (deleteInput !== 'DELETE') {
            toast.error('Please type DELETE to confirm.');
            return;
        }
        setDeleteLoading(true);
        try {
            // TODO: Supabase does not expose a client-side deleteUser() for security reasons.
            // Add a server-side Supabase Edge Function or service role call to delete the user.
            toast.error('Account deletion requires a server-side function. Please contact support.');
        } finally {
            setDeleteLoading(false);
            setDeleteModal(false);
            setDeleteInput('');
        }
    };

    const displayName = form.first_name
        ? `${form.first_name} ${form.last_name}`.trim()
        : user?.user_metadata?.username || user?.email?.split('@')[0] || 'User';

    const initials = displayName.slice(0, 2).toUpperCase();

    if (loading) {
        return (
            <div className="space-y-5 max-w-2xl mx-auto page-enter">
                <Skeleton className="h-9 w-48" />
                {[1, 2, 3].map((i) => (
                    <div key={i} className="rounded-2xl border border-border bg-card p-5 space-y-3">
                        <Skeleton className="h-5 w-32" />
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-10 w-full" />
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5 max-w-2xl mx-auto page-enter">
            <div>
                <h1 className="font-display text-3xl font-bold text-foreground">Settings</h1>
                <p className="mt-0.5 text-sm text-muted-foreground">Manage your profile, preferences, and account.</p>
            </div>

            {/* Stats ribbon */}
            {summary && (
                <div className="grid grid-cols-3 gap-3">
                    {[
                        { label: 'Income this month', value: formatCurrency(summary.current_month.income), color: 'text-income' },
                        { label: 'Expenses this month', value: formatCurrency(summary.current_month.expense), color: 'text-expense' },
                        { label: 'Net balance', value: formatCurrency(Math.abs(summary.current_month.balance)), color: summary.current_month.balance >= 0 ? 'text-income' : 'text-expense' },
                    ].map((s) => (
                        <div key={s.label} className="rounded-xl border border-border bg-card px-3 py-3 text-center">
                            <p className="text-[10px] text-muted-foreground mb-0.5 leading-tight">{s.label}</p>
                            <p className={`text-base font-bold ${s.color}`}>{s.value}</p>
                        </div>
                    ))}
                </div>
            )}

            {/* 1. Profile */}
            <Section title="Profile" icon={User}>
                <form onSubmit={handleSaveProfile} className="space-y-4">
                    {/* Avatar */}
                    <div className="flex items-center gap-4">
                        <div className="relative">
                            {photoPreview ? (
                                <img
                                    src={photoPreview}
                                    alt="Avatar"
                                    className="h-16 w-16 rounded-2xl object-cover border-2 border-border"
                                />
                            ) : (
                                <div className="h-16 w-16 rounded-2xl bg-primary flex items-center justify-center text-primary-foreground text-xl font-bold border-2 border-border">
                                    {initials}
                                </div>
                            )}
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-card border border-border shadow-sm text-muted-foreground hover:text-foreground transition-colors"
                            >
                                <Camera size={12} />
                            </button>
                        </div>
                        <div>
                            <p className="font-semibold text-foreground">{displayName}</p>
                            <p className="text-sm text-muted-foreground">{user?.email}</p>
                        </div>
                        <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange} />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <Field label="First name" id="first_name">
                            <input
                                id="first_name"
                                type="text"
                                value={form.first_name}
                                onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
                                placeholder="First name"
                                className={inputCls(false)}
                            />
                        </Field>
                        <Field label="Last name" id="last_name">
                            <input
                                id="last_name"
                                type="text"
                                value={form.last_name}
                                onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
                                placeholder="Last name"
                                className={inputCls(false)}
                            />
                        </Field>
                    </div>

                    <Field label="Email" id="email">
                        <div className="relative">
                            <Mail size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <input
                                id="email"
                                type="email"
                                value={user?.email || ''}
                                disabled
                                className="w-full rounded-xl border border-border bg-muted/40 pl-9 pr-4 py-2.5 text-sm text-muted-foreground cursor-not-allowed"
                            />
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">Email cannot be changed here.</p>
                    </Field>

                    <Field label="Phone" id="phone">
                        <div className="relative">
                            <Phone size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <input
                                id="phone"
                                type="tel"
                                value={form.phone}
                                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                                placeholder="+91 9876543210"
                                className={inputCls(false) + ' pl-9'}
                            />
                        </div>
                    </Field>

                    <button
                        type="submit"
                        disabled={saving}
                        className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition disabled:opacity-60"
                    >
                        {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                        {saving ? 'Saving…' : 'Save Profile'}
                    </button>
                </form>
            </Section>

            {/* 2. Security */}
            <Section title="Security" icon={Shield}>
                <form onSubmit={handleChangePassword} className="space-y-4">
                    <Field label="New password" id="new_pw" error={pwErrors.new_password}>
                        <div className="relative">
                            <input
                                id="new_pw"
                                type={showPw ? 'text' : 'password'}
                                value={pwForm.new_password}
                                onChange={(e) => { setPwForm((f) => ({ ...f, new_password: e.target.value })); setPwErrors((p) => ({ ...p, new_password: undefined })); }}
                                placeholder="New password (min. 6 chars)"
                                className={inputCls(pwErrors.new_password) + ' pr-10'}
                            />
                            <button type="button" tabIndex={-1} onClick={() => setShowPw((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                            </button>
                        </div>
                    </Field>
                    <Field label="Confirm new password" id="confirm_pw" error={pwErrors.confirm_password}>
                        <input
                            id="confirm_pw"
                            type={showPw ? 'text' : 'password'}
                            value={pwForm.confirm_password}
                            onChange={(e) => { setPwForm((f) => ({ ...f, confirm_password: e.target.value })); setPwErrors((p) => ({ ...p, confirm_password: undefined })); }}
                            placeholder="Confirm password"
                            className={inputCls(pwErrors.confirm_password)}
                        />
                    </Field>
                    <button
                        type="submit"
                        disabled={pwSaving}
                        className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition disabled:opacity-60"
                    >
                        {pwSaving ? <Loader2 size={15} className="animate-spin" /> : <Shield size={15} />}
                        {pwSaving ? 'Updating…' : 'Update Password'}
                    </button>
                </form>
            </Section>

            {/* 3. Preferences */}
            <Section title="Preferences" icon={Palette}>
                <div className="space-y-5">
                    {/* Monthly budget */}
                    <form onSubmit={handleSaveBudget} className="space-y-3">
                        <label className="block text-sm font-medium text-foreground">Monthly budget</label>
                        <div className="flex gap-2">
                            <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={budget}
                                onChange={(e) => setBudget(e.target.value)}
                                placeholder="0.00"
                                className={inputCls(false) + ' max-w-xs'}
                            />
                            <button
                                type="submit"
                                disabled={budgetSaving}
                                className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition disabled:opacity-60 whitespace-nowrap"
                            >
                                {budgetSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                                Save
                            </button>
                        </div>
                    </form>

                    {/* Currency */}
                    <div>
                        <label className="block text-sm font-medium text-foreground mb-2">Currency</label>
                        <div className="flex flex-wrap gap-2">
                            {CURRENCY_OPTIONS.map((opt) => (
                                <button
                                    key={opt.code}
                                    type="button"
                                    onClick={() => handleCurrencyChange(opt.code)}
                                    className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition-all border ${
                                        currency === opt.code
                                            ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                                            : 'border-border text-muted-foreground hover:text-foreground hover:border-foreground/20'
                                    }`}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Theme */}
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-medium text-foreground">Dark mode</p>
                            <p className="text-xs text-muted-foreground">Persisted in your browser</p>
                        </div>
                        <button
                            type="button"
                            onClick={handleThemeToggle}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${isDark ? 'bg-primary' : 'bg-muted'}`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${isDark ? 'translate-x-6' : 'translate-x-1'}`} />
                        </button>
                    </div>
                </div>
            </Section>

            {/* 4. Data */}
            <Section title="Data" icon={Database}>
                <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Export all your transactions as a CSV file.</p>
                    <button
                        onClick={handleExportCSV}
                        className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition-colors"
                    >
                        <Download size={15} />
                        Export as CSV
                    </button>
                </div>
            </Section>

            {/* 5. Danger zone */}
            <Section title="Danger Zone" icon={AlertTriangle}>
                <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                        Permanently delete your account and all associated data. This action is irreversible.
                    </p>
                    <button
                        onClick={() => setDeleteModal(true)}
                        className="flex items-center gap-2 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive px-4 py-2.5 text-sm font-semibold hover:bg-destructive/20 transition-colors"
                    >
                        <AlertTriangle size={15} />
                        Delete my account
                    </button>
                </div>
            </Section>

            {/* Delete account confirmation modal */}
            {deleteModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4" aria-modal="true">
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => { setDeleteModal(false); setDeleteInput(''); }} />
                    <div className="relative z-10 w-full max-w-sm rounded-2xl bg-card border border-border shadow-2xl p-5 space-y-4 animate-in fade-in zoom-in-95 duration-200">
                        <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                                <AlertTriangle size={20} />
                            </div>
                            <h3 className="font-semibold text-foreground">Delete account?</h3>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            This will permanently erase your account and all data. Type{' '}
                            <strong className="text-foreground font-mono">DELETE</strong> to confirm.
                        </p>
                        <input
                            type="text"
                            value={deleteInput}
                            onChange={(e) => setDeleteInput(e.target.value)}
                            placeholder="Type DELETE here"
                            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-destructive/30 focus:border-destructive"
                        />
                        <div className="flex gap-2">
                            <button onClick={() => { setDeleteModal(false); setDeleteInput(''); }} className="flex-1 rounded-xl border border-border py-2.5 text-sm font-semibold text-foreground hover:bg-muted transition">
                                Cancel
                            </button>
                            <button
                                onClick={handleDeleteAccount}
                                disabled={deleteInput !== 'DELETE' || deleteLoading}
                                className="flex-1 rounded-xl bg-destructive py-2.5 text-sm font-semibold text-destructive-foreground hover:opacity-90 transition disabled:opacity-40"
                            >
                                {deleteLoading ? 'Deleting…' : 'Delete forever'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Profile;
