import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import {
    Loader2, Save, Mail, Calendar, IndianRupee, TrendingUp,
    Target, Wallet, Camera, Pencil, X, Check, Phone, User as UserIcon,
    CheckCircle2, AlertCircle, Lock, Eye, EyeOff, KeyRound
} from 'lucide-react';
import api from '../services/api';

const Profile = () => {
    const { user, logout } = useAuth();
    const fileInputRef = useRef(null);

    const [profileLoading, setProfileLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [budgetSaving, setBudgetSaving] = useState(false);
    const [passwordSaving, setPasswordSaving] = useState(false);
    const [editing, setEditing] = useState(false);
    const [toast, setToast] = useState(null);

    const [userData, setUserData] = useState(null);
    const [summary, setSummary] = useState(null);

    const [form, setForm] = useState({
        first_name: '', last_name: '', email: '', phone: '', profile_photo: '',
    });
    const [budget, setBudget] = useState('');
    const [photoPreview, setPhotoPreview] = useState(null);

    const [passwordForm, setPasswordForm] = useState({
        current_password: '', new_password: '', confirm_password: '',
    });
    const [showCurrentPw, setShowCurrentPw] = useState(false);
    const [showNewPw, setShowNewPw] = useState(false);
    const [showConfirmPw, setShowConfirmPw] = useState(false);

    const showToast = (type, message) => {
        setToast({ type, message });
        setTimeout(() => setToast(null), 3500);
    };

    useEffect(() => {
        const fetchAll = async () => {
            try {
                const [userRes, summaryRes] = await Promise.all([
                    api.get('/auth/me/'),
                    api.get('/transactions/summary/'),
                ]);
                setUserData(userRes.data);
                setSummary(summaryRes.data);
                setForm({
                    first_name: userRes.data.first_name || '',
                    last_name: userRes.data.last_name || '',
                    email: userRes.data.email || '',
                    phone: userRes.data.phone || '',
                    profile_photo: userRes.data.profile_photo || '',
                });
                if (userRes.data.monthly_budget !== null && userRes.data.monthly_budget !== undefined) {
                    setBudget(userRes.data.monthly_budget);
                }
                if (userRes.data.profile_photo) {
                    setPhotoPreview(userRes.data.profile_photo);
                }
            } catch (err) {
                console.error('Failed to fetch user data', err);
            } finally {
                setProfileLoading(false);
            }
        };
        fetchAll();
    }, []);

    const handlePhotoChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) { showToast('error', 'Image must be smaller than 2MB'); return; }
        const reader = new FileReader();
        reader.onloadend = () => {
            setPhotoPreview(reader.result);
            setForm(prev => ({ ...prev, profile_photo: reader.result }));
        };
        reader.readAsDataURL(file);
    };

    const handleSaveProfile = async () => {
        setSaving(true);
        try {
            const res = await api.patch('/auth/me/', {
                first_name: form.first_name, last_name: form.last_name,
                email: form.email, phone: form.phone, profile_photo: form.profile_photo,
            });
            setUserData(res.data);
            setEditing(false);
            showToast('success', 'Profile updated successfully!');
        } catch (err) {
            const ed = err.response?.data;
            if (ed && typeof ed === 'object') {
                showToast('error', Object.entries(ed).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' | '));
            } else { showToast('error', 'Failed to update profile'); }
        } finally { setSaving(false); }
    };

    const handleCancelEdit = () => {
        setForm({
            first_name: userData?.first_name || '', last_name: userData?.last_name || '',
            email: userData?.email || '', phone: userData?.phone || '',
            profile_photo: userData?.profile_photo || '',
        });
        setPhotoPreview(userData?.profile_photo || null);
        setEditing(false);
    };

    const handleUpdateBudget = async (e) => {
        e.preventDefault();
        setBudgetSaving(true);
        try { await api.patch('/auth/me/', { monthly_budget: budget || 0 }); showToast('success', 'Budget updated!'); }
        catch { showToast('error', 'Failed to update budget'); }
        finally { setBudgetSaving(false); }
    };

    const handleChangePassword = async (e) => {
        e.preventDefault();
        if (passwordForm.new_password !== passwordForm.confirm_password) { showToast('error', 'Passwords do not match'); return; }
        if (passwordForm.new_password.length < 6) { showToast('error', 'Password must be at least 6 characters'); return; }
        setPasswordSaving(true);
        try {
            await api.post('/auth/change-password/', passwordForm);
            showToast('success', 'Password changed successfully!');
            setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
        } catch (err) { showToast('error', err.response?.data?.detail || 'Failed to change password'); }
        finally { setPasswordSaving(false); }
    };

    if (profileLoading) {
        return (
            <div className="flex justify-center items-center h-[calc(100vh-100px)]">
                <Loader2 className="animate-spin text-primary h-12 w-12" />
            </div>
        );
    }

    const currentMonth = summary?.current_month;
    const budgetData = summary?.budget;
    const displayName = userData?.first_name
        ? `${userData.first_name} ${userData.last_name || ''}`.trim()
        : userData?.username || 'User';
    const initials = userData?.first_name
        ? `${userData.first_name.charAt(0)}${(userData.last_name || '').charAt(0)}`.toUpperCase()
        : (userData?.username?.charAt(0)?.toUpperCase() || 'U');
    const joinDate = userData?.date_joined
        ? new Date(userData.date_joined).toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: 'numeric' })
        : '';

    // Info fields for read-only display
    const infoFields = [
        { label: 'First Name', value: userData?.first_name || '—' },
        { label: 'Last Name', value: userData?.last_name || '—' },
        { label: 'Email Address', value: userData?.email || '—' },
        { label: 'Phone Number', value: userData?.phone || '—' },
        { label: 'Username', value: `@${userData?.username}` || '—' },
        { label: 'Member Since', value: joinDate || '—' },
    ];

    return (
        <div className="animate-in fade-in duration-500 -m-4 md:-m-8 min-h-[calc(100vh-64px)] bg-[#f0f4f8]">
            {/* Toast */}
            {toast && (
                <div className={`fixed top-6 right-6 z-[100] flex items-center gap-3 px-5 py-3.5 rounded-xl shadow-2xl border animate-in slide-in-from-right duration-300 ${
                    toast.type === 'success'
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        : 'bg-red-50 border-red-200 text-red-700'
                }`}>
                    {toast.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                    <span className="text-sm font-medium">{toast.message}</span>
                    <button onClick={() => setToast(null)} className="ml-2 opacity-60 hover:opacity-100"><X size={14} /></button>
                </div>
            )}

            {/* Page Header */}
            <div className="bg-white border-b border-gray-200 px-6 md:px-10 py-5">
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">My Profile</h1>
                <p className="text-gray-500 mt-0.5 text-sm">Manage your account, preferences, and security settings.</p>
            </div>

            <div className="px-4 sm:px-6 md:px-10 py-6 space-y-5 max-w-[1400px] mx-auto">

                {/* Profile Card */}
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                    {/* Teal accent bar */}
                    <div className="h-20 sm:h-24 bg-gradient-to-r from-[#0c4a4a] via-[#0e6b5e] to-[#1a8a70]" />
                    <div className="px-5 sm:px-8 pb-6 -mt-10 sm:-mt-12">
                        <div className="flex flex-col sm:flex-row items-center sm:items-end gap-4">
                            {/* Avatar */}
                            <div className="relative group flex-shrink-0">
                                <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-full bg-white border-4 border-white shadow-lg flex items-center justify-center overflow-hidden">
                                    {photoPreview ? (
                                        <img src={photoPreview} alt="Profile" className="w-full h-full object-cover" />
                                    ) : (
                                        <span className="text-2xl sm:text-3xl font-black text-[#0c4a4a]">{initials}</span>
                                    )}
                                </div>
                                {editing && (
                                    <button onClick={() => fileInputRef.current?.click()}
                                        className="absolute bottom-0 right-0 w-8 h-8 bg-[#0c4a4a] text-white rounded-full flex items-center justify-center shadow-md hover:scale-110 transition-transform border-2 border-white">
                                        <Camera size={14} />
                                    </button>
                                )}
                                <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handlePhotoChange} />
                            </div>
                            {/* Name */}
                            <div className="text-center sm:text-left flex-1 sm:pb-0.5">
                                <h2 className="text-xl sm:text-2xl font-bold text-gray-900">{displayName}</h2>
                                <p className="text-gray-500 text-sm">@{userData?.username} • {userData?.email}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Personal Information */}
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
                    <div className="flex items-center justify-between px-5 sm:px-8 py-4 border-b border-gray-100">
                        <div className="flex items-center gap-3">
                            <div className="w-9 h-9 bg-[#e8f5f0] rounded-lg flex items-center justify-center">
                                <UserIcon size={18} className="text-[#0c4a4a]" />
                            </div>
                            <h3 className="text-base sm:text-lg font-semibold text-gray-900">Personal Information</h3>
                        </div>
                        {editing ? (
                            <div className="flex items-center gap-2">
                                <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={saving}
                                    className="h-8 text-xs border-gray-300">
                                    Cancel
                                </Button>
                                <Button size="sm" onClick={handleSaveProfile} disabled={saving}
                                    className="h-8 text-xs bg-[#0c4a4a] hover:bg-[#0a3e3e] text-white">
                                    {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Check className="h-3.5 w-3.5 mr-1" />}
                                    Save
                                </Button>
                            </div>
                        ) : (
                            <Button size="sm" onClick={() => setEditing(true)}
                                className="h-8 text-xs bg-[#0c4a4a] hover:bg-[#0a3e3e] text-white">
                                <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                            </Button>
                        )}
                    </div>

                    {editing ? (
                        /* Edit Mode */
                        <div className="px-5 sm:px-8 py-5">
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-4">
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">First Name</Label>
                                    <Input placeholder="Enter first name" value={form.first_name}
                                        className="h-10 bg-gray-50 border-gray-200 focus:border-[#0c4a4a] focus:ring-[#0c4a4a]/10"
                                        onChange={(e) => setForm(prev => ({ ...prev, first_name: e.target.value }))} />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Last Name</Label>
                                    <Input placeholder="Enter last name" value={form.last_name}
                                        className="h-10 bg-gray-50 border-gray-200 focus:border-[#0c4a4a] focus:ring-[#0c4a4a]/10"
                                        onChange={(e) => setForm(prev => ({ ...prev, last_name: e.target.value }))} />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Email Address</Label>
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
                                        <Input type="email" placeholder="you@example.com" className="h-10 pl-9 bg-gray-50 border-gray-200"
                                            value={form.email} onChange={(e) => setForm(prev => ({ ...prev, email: e.target.value }))} />
                                    </div>
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Phone Number</Label>
                                    <div className="relative">
                                        <Phone className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
                                        <Input type="tel" placeholder="+91 98765 43210" className="h-10 pl-9 bg-gray-50 border-gray-200"
                                            value={form.phone} onChange={(e) => setForm(prev => ({ ...prev, phone: e.target.value }))} />
                                    </div>
                                </div>
                            </div>
                            <p className="text-xs text-gray-400 mt-4">📷 Click on your profile photo to upload a new one (max 2MB, JPG/PNG/WebP)</p>
                        </div>
                    ) : (
                        /* Read-only Mode */
                        <div className="px-5 sm:px-8 py-5">
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-8 gap-y-5">
                                {infoFields.map((field, i) => (
                                    <div key={i}>
                                        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{field.label}</p>
                                        <p className="text-sm font-medium text-gray-800">{field.value}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Financial Summary */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {[
                        { label: 'This Month Income', value: currentMonth?.income, color: '#059669', bg: '#ecfdf5', icon: TrendingUp },
                        { label: 'This Month Expense', value: currentMonth?.expense, color: '#dc2626', bg: '#fef2f2', icon: Wallet },
                        { label: 'Net Balance', value: currentMonth?.balance, color: '#2563eb', bg: '#eff6ff', icon: IndianRupee },
                    ].map((stat, i) => (
                        <div key={i} className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 hover:shadow-md transition-shadow">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{stat.label}</p>
                                    <p className="text-2xl font-bold mt-1.5" style={{ color: stat.color }}>
                                        ₹{stat.value ? parseFloat(stat.value).toFixed(2) : '0.00'}
                                    </p>
                                </div>
                                <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: stat.bg }}>
                                    <stat.icon size={20} style={{ color: stat.color }} />
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* Budget & Password — 2 column */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {/* Monthly Budget */}
                    <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
                        <div className="flex items-center gap-3 px-5 sm:px-6 py-4 border-b border-gray-100">
                            <div className="w-9 h-9 bg-blue-50 rounded-lg flex items-center justify-center">
                                <Target size={18} className="text-blue-600" />
                            </div>
                            <div>
                                <h3 className="text-base font-semibold text-gray-900">Monthly Budget</h3>
                                <p className="text-xs text-gray-400">Set a spending limit</p>
                            </div>
                        </div>
                        <form onSubmit={handleUpdateBudget}>
                            <div className="px-5 sm:px-6 py-5 space-y-4">
                                {budgetData && parseFloat(budgetData.limit) > 0 && (
                                    <div className="p-3.5 rounded-lg bg-gray-50 space-y-2.5">
                                        <div className="flex justify-between text-xs font-medium">
                                            <span className="text-gray-500">Spent this month</span>
                                            <span className="text-gray-700">
                                                ₹{currentMonth ? parseFloat(currentMonth.expense).toFixed(0) : 0} / ₹{parseFloat(budgetData.limit).toFixed(0)}
                                            </span>
                                        </div>
                                        <div className="w-full bg-gray-200 h-2.5 rounded-full overflow-hidden">
                                            <div className={`h-full rounded-full transition-all duration-500 ${budgetData.exceeded ? 'bg-red-500' : 'bg-[#0c4a4a]'}`}
                                                style={{ width: `${Math.min((currentMonth?.expense / budgetData.limit) * 100, 100)}%` }} />
                                        </div>
                                        <p className="text-xs text-gray-500">
                                            {budgetData.exceeded ? '⚠️ Budget exceeded!' : `₹${(parseFloat(budgetData.limit) - parseFloat(currentMonth?.expense || 0)).toFixed(0)} remaining`}
                                        </p>
                                    </div>
                                )}
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Budget Limit (₹)</Label>
                                    <Input type="number" step="0.01" placeholder="e.g. 20000" className="h-10 bg-gray-50 border-gray-200"
                                        value={budget} onChange={(e) => setBudget(e.target.value)} />
                                    <p className="text-xs text-gray-400">Set to 0 to disable.</p>
                                </div>
                            </div>
                            <div className="px-5 sm:px-6 pb-5">
                                <Button type="submit" disabled={budgetSaving} className="w-full h-10 bg-[#0c4a4a] hover:bg-[#0a3e3e] text-white">
                                    {budgetSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                                    Update Budget
                                </Button>
                            </div>
                        </form>
                    </div>

                    {/* Change Password */}
                    <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
                        <div className="flex items-center gap-3 px-5 sm:px-6 py-4 border-b border-gray-100">
                            <div className="w-9 h-9 bg-amber-50 rounded-lg flex items-center justify-center">
                                <KeyRound size={18} className="text-amber-600" />
                            </div>
                            <div>
                                <h3 className="text-base font-semibold text-gray-900">Change Password</h3>
                                <p className="text-xs text-gray-400">Keep your account secure</p>
                            </div>
                        </div>
                        <form onSubmit={handleChangePassword}>
                            <div className="px-5 sm:px-6 py-5 space-y-4">
                                {[
                                    { id: 'current_password', label: 'Current Password', placeholder: 'Enter current password', show: showCurrentPw, toggle: setShowCurrentPw, key: 'current_password' },
                                    { id: 'new_password', label: 'New Password', placeholder: 'Min 6 characters', show: showNewPw, toggle: setShowNewPw, key: 'new_password' },
                                    { id: 'confirm_password', label: 'Confirm Password', placeholder: 'Confirm new password', show: showConfirmPw, toggle: setShowConfirmPw, key: 'confirm_password' },
                                ].map((field) => (
                                    <div key={field.id} className="space-y-1.5">
                                        <Label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{field.label}</Label>
                                        <div className="relative">
                                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
                                            <Input id={field.id} type={field.show ? 'text' : 'password'}
                                                placeholder={field.placeholder} className="h-10 pl-9 pr-10 bg-gray-50 border-gray-200"
                                                value={passwordForm[field.key]}
                                                onChange={(e) => setPasswordForm(prev => ({ ...prev, [field.key]: e.target.value }))} />
                                            <button type="button" tabIndex={-1}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                                                onClick={() => field.toggle(v => !v)}>
                                                {field.show ? <EyeOff size={15} /> : <Eye size={15} />}
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <div className="px-5 sm:px-6 pb-5">
                                <Button type="submit" disabled={passwordSaving} variant="outline"
                                    className="w-full h-10 border-gray-300 text-gray-700 hover:bg-gray-50">
                                    {passwordSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <KeyRound className="mr-2 h-4 w-4" />}
                                    Change Password
                                </Button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Profile;
