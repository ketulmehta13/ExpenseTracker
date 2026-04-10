import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import {
    Loader2, Save, Mail, Calendar, IndianRupee, Shield, TrendingUp,
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
            showToast('success', 'Password changed!');
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

    return (
        <div className="animate-in fade-in duration-500 -m-4 md:-m-8 min-h-[calc(100vh-64px)] relative overflow-hidden"
             style={{ background: 'linear-gradient(160deg, #0d4f4f 0%, #0f6b5e 18%, #1a8a6e 35%, #4db89a 50%, #a8dbc5 65%, #d4efe0 78%, #eef8f3 88%, #f8fcfa 100%)' }}
        >
            {/* Decorative Background Elements */}
            <div className="absolute top-0 right-0 w-96 h-96 bg-white/5 rounded-full blur-3xl" />
            <div className="absolute bottom-0 left-0 w-80 h-80 bg-emerald-900/10 rounded-full blur-3xl" />
            <div className="absolute top-1/3 left-1/4 w-64 h-64 bg-white/5 rounded-full blur-2xl" />

            {/* Toast */}
            {toast && (
                <div className={`fixed top-6 right-6 z-[100] flex items-center gap-3 px-5 py-3.5 rounded-xl shadow-2xl border backdrop-blur-md animate-in slide-in-from-right duration-300 ${
                    toast.type === 'success' ? 'bg-emerald-500/20 border-emerald-400/40 text-emerald-100' : 'bg-red-500/20 border-red-400/40 text-red-100'
                }`}>
                    {toast.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                    <span className="text-sm font-medium">{toast.message}</span>
                    <button onClick={() => setToast(null)} className="ml-2 opacity-60 hover:opacity-100"><X size={14} /></button>
                </div>
            )}

            {/* Header Section */}
            <div className="px-6 md:px-10 pt-8 pb-6">
                <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight drop-shadow-lg">
                    Profile Details
                </h1>
                <p className="text-white/70 mt-1 text-sm sm:text-base">Manage your account, preferences, and security.</p>
            </div>

            {/* Profile Card */}
            <div className="px-6 md:px-10 pb-6">
                <div className="bg-white/15 backdrop-blur-xl rounded-2xl border border-white/20 shadow-2xl p-6 sm:p-8">
                    <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6">
                        {/* Avatar */}
                        <div className="relative group flex-shrink-0">
                            <div className="w-28 h-28 sm:w-32 sm:h-32 rounded-2xl bg-white/90 shadow-2xl flex items-center justify-center overflow-hidden ring-4 ring-white/30">
                                {photoPreview ? (
                                    <img src={photoPreview} alt="Profile" className="w-full h-full object-cover" />
                                ) : (
                                    <span className="text-5xl font-black text-emerald-700">{initials}</span>
                                )}
                            </div>
                            {editing && (
                                <>
                                    <button onClick={() => fileInputRef.current?.click()}
                                        className="absolute inset-0 rounded-2xl bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
                                        <Camera className="text-white" size={28} />
                                    </button>
                                    <button onClick={() => fileInputRef.current?.click()}
                                        className="absolute -bottom-2 -right-2 w-10 h-10 bg-emerald-500 text-white rounded-full flex items-center justify-center shadow-lg hover:scale-110 transition-transform ring-2 ring-white/50">
                                        <Camera size={16} />
                                    </button>
                                </>
                            )}
                            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handlePhotoChange} />
                        </div>

                        {/* Info */}
                        <div className="flex-1 text-center sm:text-left">
                            <h2 className="text-2xl sm:text-3xl font-bold text-white drop-shadow">{displayName}</h2>
                            <p className="text-emerald-100/80 font-semibold mt-0.5">@{userData?.username}</p>
                            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-x-5 gap-y-1.5 mt-3 text-white/70 text-sm">
                                {userData?.email && (
                                    <span className="flex items-center gap-1.5"><Mail size={14} className="text-emerald-200/80" />{userData.email}</span>
                                )}
                                {userData?.phone && (
                                    <span className="flex items-center gap-1.5"><Phone size={14} className="text-emerald-200/80" />{userData.phone}</span>
                                )}
                                {joinDate && (
                                    <span className="flex items-center gap-1.5"><Calendar size={14} className="text-emerald-200/80" />Joined {joinDate}</span>
                                )}
                            </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-2 flex-shrink-0">
                            {editing ? (
                                <>
                                    <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={saving}
                                        className="bg-white/10 border-white/30 text-white hover:bg-white/20 hover:text-white">
                                        <X className="h-4 w-4 mr-1" /> Cancel
                                    </Button>
                                    <Button size="sm" onClick={handleSaveProfile} disabled={saving}
                                        className="bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg">
                                        {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Check className="h-4 w-4 mr-1" />}
                                        Save
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <div className="px-3 py-1.5 bg-emerald-400/20 text-emerald-100 text-xs font-semibold rounded-full flex items-center gap-1.5 border border-emerald-400/30">
                                        <Shield size={12} /> Active
                                    </div>
                                    <Button size="sm" onClick={() => setEditing(true)}
                                        className="bg-white/15 border border-white/30 text-white hover:bg-white/25 backdrop-blur-sm">
                                        <Pencil className="h-4 w-4 mr-1" /> Edit Profile
                                    </Button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Edit Form */}
            {editing && (
                <div className="px-6 md:px-10 pb-6 animate-in slide-in-from-top-2 duration-300">
                    <div className="bg-white/90 backdrop-blur-xl rounded-2xl border border-white/50 shadow-xl p-6 sm:p-8">
                        <div className="flex items-center gap-3 mb-6">
                            <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center">
                                <UserIcon className="text-emerald-700" size={20} />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-gray-800">Personal Information</h3>
                                <p className="text-sm text-gray-500">Update your personal details</p>
                            </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                            <div className="space-y-2">
                                <Label htmlFor="first_name" className="text-gray-700">First Name</Label>
                                <Input id="first_name" placeholder="Enter your first name" value={form.first_name}
                                    className="bg-white border-gray-200 focus:border-emerald-500 focus:ring-emerald-500/20"
                                    onChange={(e) => setForm(prev => ({ ...prev, first_name: e.target.value }))} />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="last_name" className="text-gray-700">Last Name</Label>
                                <Input id="last_name" placeholder="Enter your last name" value={form.last_name}
                                    className="bg-white border-gray-200 focus:border-emerald-500 focus:ring-emerald-500/20"
                                    onChange={(e) => setForm(prev => ({ ...prev, last_name: e.target.value }))} />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="edit_email" className="text-gray-700">Email Address</Label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                                    <Input id="edit_email" type="email" placeholder="you@example.com" className="pl-10 bg-white border-gray-200"
                                        value={form.email} onChange={(e) => setForm(prev => ({ ...prev, email: e.target.value }))} />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="phone" className="text-gray-700">Phone Number</Label>
                                <div className="relative">
                                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                                    <Input id="phone" type="tel" placeholder="+91 98765 43210" className="pl-10 bg-white border-gray-200"
                                        value={form.phone} onChange={(e) => setForm(prev => ({ ...prev, phone: e.target.value }))} />
                                </div>
                            </div>
                        </div>
                        <p className="text-xs text-gray-500 mt-4">📷 Click on your profile photo above to upload a new one (max 2MB)</p>
                    </div>
                </div>
            )}

            {/* Stats Grid */}
            <div className="px-6 md:px-10 pb-6">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {[
                        { label: 'This Month Income', value: currentMonth?.income, color: 'emerald', icon: TrendingUp },
                        { label: 'This Month Expense', value: currentMonth?.expense, color: 'red', icon: Wallet },
                        { label: 'Net Balance', value: currentMonth?.balance, color: 'blue', icon: IndianRupee },
                    ].map((stat, i) => (
                        <div key={i} className="bg-white/85 backdrop-blur-lg rounded-2xl border border-white/50 shadow-lg p-5 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-200">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-sm text-gray-500 font-medium">{stat.label}</p>
                                    <p className={`text-2xl font-bold mt-1 ${
                                        stat.color === 'emerald' ? 'text-emerald-600' :
                                        stat.color === 'red' ? 'text-red-500' : 'text-blue-600'
                                    }`}>
                                        ₹{stat.value ? parseFloat(stat.value).toFixed(2) : '0.00'}
                                    </p>
                                </div>
                                <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${
                                    stat.color === 'emerald' ? 'bg-emerald-100' :
                                    stat.color === 'red' ? 'bg-red-100' : 'bg-blue-100'
                                }`}>
                                    <stat.icon className={
                                        stat.color === 'emerald' ? 'text-emerald-600' :
                                        stat.color === 'red' ? 'text-red-500' : 'text-blue-600'
                                    } size={22} />
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Budget + Password */}
            <div className="px-6 md:px-10 pb-10">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Budget */}
                    <div className="bg-white/85 backdrop-blur-lg rounded-2xl border border-white/50 shadow-lg overflow-hidden">
                        <div className="p-6 border-b border-gray-100">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">
                                    <Target className="text-blue-600" size={20} />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-gray-800">Monthly Budget</h3>
                                    <p className="text-sm text-gray-500">Set a spending limit to stay on track</p>
                                </div>
                            </div>
                        </div>
                        <form onSubmit={handleUpdateBudget}>
                            <div className="p-6 space-y-4">
                                {budgetData && parseFloat(budgetData.limit) > 0 && (
                                    <div className="p-4 rounded-xl bg-gray-50 space-y-3">
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-500">Spent this month</span>
                                            <span className="font-semibold text-gray-700">
                                                ₹{currentMonth ? parseFloat(currentMonth.expense).toFixed(0) : 0} / ₹{parseFloat(budgetData.limit).toFixed(0)}
                                            </span>
                                        </div>
                                        <div className="w-full bg-gray-200 h-3 rounded-full overflow-hidden">
                                            <div className={`h-full rounded-full transition-all duration-500 ${budgetData.exceeded ? 'bg-red-500' : 'bg-emerald-500'}`}
                                                style={{ width: `${Math.min((currentMonth?.expense / budgetData.limit) * 100, 100)}%` }} />
                                        </div>
                                        <p className="text-xs text-gray-500">
                                            {budgetData.exceeded ? '⚠️ Budget exceeded!' : `₹${(parseFloat(budgetData.limit) - parseFloat(currentMonth?.expense || 0)).toFixed(0)} remaining`}
                                        </p>
                                    </div>
                                )}
                                <div className="space-y-2">
                                    <Label htmlFor="budget" className="text-gray-700">Budget Limit (₹)</Label>
                                    <Input id="budget" type="number" step="0.01" placeholder="e.g. 20000.00"
                                        className="bg-white border-gray-200" value={budget} onChange={(e) => setBudget(e.target.value)} />
                                    <p className="text-xs text-gray-400">Set to 0 to disable budget tracking.</p>
                                </div>
                            </div>
                            <div className="px-6 pb-6">
                                <Button type="submit" disabled={budgetSaving} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white shadow-md">
                                    {budgetSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                                    Update Budget
                                </Button>
                            </div>
                        </form>
                    </div>

                    {/* Change Password */}
                    <div className="bg-white/85 backdrop-blur-lg rounded-2xl border border-white/50 shadow-lg overflow-hidden">
                        <div className="p-6 border-b border-gray-100">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center">
                                    <KeyRound className="text-orange-600" size={20} />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-gray-800">Change Password</h3>
                                    <p className="text-sm text-gray-500">Keep your account secure</p>
                                </div>
                            </div>
                        </div>
                        <form onSubmit={handleChangePassword}>
                            <div className="p-6 space-y-4">
                                {[
                                    { id: 'current_password', label: 'Current Password', placeholder: 'Enter current password', show: showCurrentPw, toggle: setShowCurrentPw, key: 'current_password' },
                                    { id: 'new_password', label: 'New Password', placeholder: 'Min 6 characters', show: showNewPw, toggle: setShowNewPw, key: 'new_password' },
                                    { id: 'confirm_password', label: 'Confirm Password', placeholder: 'Confirm new password', show: showConfirmPw, toggle: setShowConfirmPw, key: 'confirm_password' },
                                ].map((field) => (
                                    <div key={field.id} className="space-y-2">
                                        <Label htmlFor={field.id} className="text-gray-700">{field.label}</Label>
                                        <div className="relative">
                                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                                            <Input id={field.id} type={field.show ? 'text' : 'password'}
                                                placeholder={field.placeholder} className="pl-10 pr-10 bg-white border-gray-200"
                                                value={passwordForm[field.key]}
                                                onChange={(e) => setPasswordForm(prev => ({ ...prev, [field.key]: e.target.value }))} />
                                            <button type="button" tabIndex={-1}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                                                onClick={() => field.toggle(v => !v)}>
                                                {field.show ? <EyeOff size={16} /> : <Eye size={16} />}
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <div className="px-6 pb-6">
                                <Button type="submit" disabled={passwordSaving} variant="outline"
                                    className="w-full border-gray-300 hover:bg-gray-50 text-gray-700 shadow-sm">
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
