import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import {
    Loader2, Save, Mail, Calendar, IndianRupee, Shield, TrendingUp,
    Target, Wallet, Camera, Pencil, X, Check, Phone, User as UserIcon,
    CheckCircle2, AlertCircle
} from 'lucide-react';
import api from '../services/api';

const Profile = () => {
    const { user, logout } = useAuth();
    const fileInputRef = useRef(null);

    // State
    const [profileLoading, setProfileLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [budgetSaving, setBudgetSaving] = useState(false);
    const [editing, setEditing] = useState(false);
    const [toast, setToast] = useState(null); // { type: 'success' | 'error', message: '' }

    const [userData, setUserData] = useState(null);
    const [summary, setSummary] = useState(null);

    // Form state
    const [form, setForm] = useState({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        profile_photo: '',
    });
    const [budget, setBudget] = useState('');
    const [photoPreview, setPhotoPreview] = useState(null);

    // Toast helper
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

    // Handle photo selection
    const handlePhotoChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Validate file size (max 2MB)
        if (file.size > 2 * 1024 * 1024) {
            showToast('error', 'Image must be smaller than 2MB');
            return;
        }

        const reader = new FileReader();
        reader.onloadend = () => {
            const base64 = reader.result;
            setPhotoPreview(base64);
            setForm(prev => ({ ...prev, profile_photo: base64 }));
        };
        reader.readAsDataURL(file);
    };

    // Save profile details
    const handleSaveProfile = async () => {
        setSaving(true);
        try {
            const res = await api.patch('/auth/me/', {
                first_name: form.first_name,
                last_name: form.last_name,
                email: form.email,
                phone: form.phone,
                profile_photo: form.profile_photo,
            });
            setUserData(res.data);
            setEditing(false);
            showToast('success', 'Profile updated successfully!');
        } catch (err) {
            const errorData = err.response?.data;
            if (errorData && typeof errorData === 'object') {
                const messages = Object.entries(errorData).map(([key, value]) => {
                    const detail = Array.isArray(value) ? value.join(', ') : value;
                    return `${key}: ${detail}`;
                });
                showToast('error', messages.join(' | '));
            } else {
                showToast('error', 'Failed to update profile');
            }
        } finally {
            setSaving(false);
        }
    };

    // Cancel editing
    const handleCancelEdit = () => {
        setForm({
            first_name: userData?.first_name || '',
            last_name: userData?.last_name || '',
            email: userData?.email || '',
            phone: userData?.phone || '',
            profile_photo: userData?.profile_photo || '',
        });
        setPhotoPreview(userData?.profile_photo || null);
        setEditing(false);
    };

    // Save budget
    const handleUpdateBudget = async (e) => {
        e.preventDefault();
        setBudgetSaving(true);
        try {
            await api.patch('/auth/me/', { monthly_budget: budget || 0 });
            showToast('success', 'Budget updated successfully!');
        } catch (err) {
            showToast('error', 'Failed to update budget');
        } finally {
            setBudgetSaving(false);
        }
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
        <div className="space-y-6 animate-in fade-in duration-500 max-w-4xl mx-auto pt-2 pb-8">
            {/* Toast Notification */}
            {toast && (
                <div
                    className={`fixed top-6 right-6 z-[100] flex items-center gap-3 px-5 py-3.5 rounded-xl shadow-2xl border backdrop-blur-md animate-in slide-in-from-right duration-300 ${
                        toast.type === 'success'
                            ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-600'
                            : 'bg-destructive/15 border-destructive/30 text-destructive'
                    }`}
                >
                    {toast.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                    <span className="text-sm font-medium">{toast.message}</span>
                    <button onClick={() => setToast(null)} className="ml-2 opacity-60 hover:opacity-100 transition-opacity">
                        <X size={14} />
                    </button>
                </div>
            )}

            {/* Page Header */}
            <div className="flex flex-col gap-1">
                <h1 className="text-3xl font-bold tracking-tight">Profile</h1>
                <p className="text-muted-foreground">Manage your account details and financial preferences.</p>
            </div>

            {/* Profile Header Card */}
            <Card className="overflow-hidden border-border/50 shadow-lg">
                <div className="h-28 sm:h-32 bg-gradient-to-r from-primary via-primary/80 to-secondary relative">
                    <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMjAiIGN5PSIyMCIgcj0iMSIgZmlsbD0icmdiYSgyNTUsMjU1LDI1NSwwLjEpIi8+PC9zdmc+')] opacity-50" />
                </div>
                <CardContent className="relative pb-6">
                    <div className="flex flex-col sm:flex-row items-center sm:items-end gap-4 -mt-14 sm:-mt-16">
                        {/* Avatar with photo upload */}
                        <div className="relative group">
                            <div className="w-24 h-24 sm:w-28 sm:h-28 rounded-2xl bg-card border-4 border-card shadow-xl flex items-center justify-center overflow-hidden">
                                {photoPreview ? (
                                    <img
                                        src={photoPreview}
                                        alt="Profile"
                                        className="w-full h-full object-cover"
                                    />
                                ) : (
                                    <span className="text-4xl font-extrabold text-primary">
                                        {initials}
                                    </span>
                                )}
                            </div>
                            {editing && (
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="absolute inset-0 rounded-2xl bg-black/50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 cursor-pointer"
                                >
                                    <Camera className="text-white" size={24} />
                                </button>
                            )}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/jpeg,image/png,image/webp"
                                className="hidden"
                                onChange={handlePhotoChange}
                            />
                            {editing && (
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="absolute -bottom-1 -right-1 w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center shadow-lg hover:scale-110 transition-transform"
                                >
                                    <Camera size={14} />
                                </button>
                            )}
                        </div>

                        {/* User info */}
                        <div className="flex-1 text-center sm:text-left">
                            <h2 className="text-2xl font-bold">{displayName}</h2>
                            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-x-4 gap-y-1 mt-1.5 text-muted-foreground text-sm">
                                <div className="flex items-center gap-1.5">
                                    <span className="text-primary font-medium">@{userData?.username}</span>
                                </div>
                                {userData?.email && (
                                    <div className="flex items-center gap-1.5">
                                        <Mail size={13} />
                                        <span>{userData.email}</span>
                                    </div>
                                )}
                                {joinDate && (
                                    <div className="flex items-center gap-1.5">
                                        <Calendar size={13} />
                                        <span>Joined {joinDate}</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Edit / Save / Cancel buttons */}
                        <div className="flex items-center gap-2">
                            {editing ? (
                                <>
                                    <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={saving}>
                                        <X className="h-4 w-4 mr-1" /> Cancel
                                    </Button>
                                    <Button size="sm" onClick={handleSaveProfile} disabled={saving}>
                                        {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Check className="h-4 w-4 mr-1" />}
                                        Save
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <div className="px-3 py-1.5 bg-emerald-500/15 text-emerald-600 text-xs font-semibold rounded-full flex items-center gap-1.5">
                                        <Shield size={12} />
                                        Active
                                    </div>
                                    <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                                        <Pencil className="h-4 w-4 mr-1" /> Edit
                                    </Button>
                                </>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Personal Details Card (visible when editing) */}
            {editing && (
                <Card className="border-border/50 shadow-md animate-in slide-in-from-top-2 duration-300">
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
                                <UserIcon className="text-primary" size={20} />
                            </div>
                            <div>
                                <CardTitle>Personal Information</CardTitle>
                                <CardDescription>Update your personal details</CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                            <div className="space-y-2">
                                <Label htmlFor="first_name">First Name</Label>
                                <Input
                                    id="first_name"
                                    placeholder="Enter your first name"
                                    value={form.first_name}
                                    onChange={(e) => setForm(prev => ({ ...prev, first_name: e.target.value }))}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="last_name">Last Name</Label>
                                <Input
                                    id="last_name"
                                    placeholder="Enter your last name"
                                    value={form.last_name}
                                    onChange={(e) => setForm(prev => ({ ...prev, last_name: e.target.value }))}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="edit_email">Email Address</Label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                                    <Input
                                        id="edit_email"
                                        type="email"
                                        placeholder="you@example.com"
                                        className="pl-10"
                                        value={form.email}
                                        onChange={(e) => setForm(prev => ({ ...prev, email: e.target.value }))}
                                    />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="phone">Phone Number</Label>
                                <div className="relative">
                                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                                    <Input
                                        id="phone"
                                        type="tel"
                                        placeholder="+91 98765 43210"
                                        className="pl-10"
                                        value={form.phone}
                                        onChange={(e) => setForm(prev => ({ ...prev, phone: e.target.value }))}
                                    />
                                </div>
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground mt-4">
                            📷 Tip: Click on your profile photo above to upload a new one (max 2MB, JPG/PNG/WebP)
                        </p>
                    </CardContent>
                </Card>
            )}

            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Card className="border-border/50 hover:shadow-md transition-shadow duration-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">This Month Income</p>
                                <p className="text-2xl font-bold text-emerald-500 mt-1">
                                    ₹{currentMonth ? parseFloat(currentMonth.income).toFixed(2) : '0.00'}
                                </p>
                            </div>
                            <div className="w-10 h-10 bg-emerald-500/10 rounded-xl flex items-center justify-center">
                                <TrendingUp className="text-emerald-500" size={20} />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="border-border/50 hover:shadow-md transition-shadow duration-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">This Month Expense</p>
                                <p className="text-2xl font-bold text-destructive mt-1">
                                    ₹{currentMonth ? parseFloat(currentMonth.expense).toFixed(2) : '0.00'}
                                </p>
                            </div>
                            <div className="w-10 h-10 bg-destructive/10 rounded-xl flex items-center justify-center">
                                <Wallet className="text-destructive" size={20} />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="border-border/50 hover:shadow-md transition-shadow duration-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Net Balance</p>
                                <p className="text-2xl font-bold text-primary mt-1">
                                    ₹{currentMonth ? parseFloat(currentMonth.balance).toFixed(2) : '0.00'}
                                </p>
                            </div>
                            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
                                <IndianRupee className="text-primary" size={20} />
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Budget Settings */}
            <Card className="border-border/50 shadow-md">
                <CardHeader>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-blue-500/10 rounded-xl flex items-center justify-center">
                            <Target className="text-blue-500" size={20} />
                        </div>
                        <div>
                            <CardTitle>Monthly Budget</CardTitle>
                            <CardDescription>Set a spending limit to keep your finances on track</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <form onSubmit={handleUpdateBudget}>
                    <CardContent className="space-y-4">
                        {/* Budget Progress */}
                        {budgetData && parseFloat(budgetData.limit) > 0 && (
                            <div className="p-4 rounded-xl bg-muted/50 space-y-3">
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Spent this month</span>
                                    <span className="font-semibold">
                                        ₹{currentMonth ? parseFloat(currentMonth.expense).toFixed(0) : 0} / ₹{parseFloat(budgetData.limit).toFixed(0)}
                                    </span>
                                </div>
                                <div className="w-full bg-background h-3 rounded-full overflow-hidden">
                                    <div
                                        className={`h-full rounded-full transition-all duration-500 ${budgetData.exceeded ? 'bg-destructive' : 'bg-primary'}`}
                                        style={{ width: `${Math.min((currentMonth?.expense / budgetData.limit) * 100, 100)}%` }}
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {budgetData.exceeded
                                        ? '⚠️ You have exceeded your budget this month!'
                                        : `₹${(parseFloat(budgetData.limit) - parseFloat(currentMonth?.expense || 0)).toFixed(0)} remaining`
                                    }
                                </p>
                            </div>
                        )}

                        <div className="space-y-2">
                            <Label htmlFor="budget">Monthly Budget Limit (₹)</Label>
                            <Input
                                id="budget"
                                type="number"
                                step="0.01"
                                placeholder="e.g. 20000.00"
                                value={budget}
                                onChange={(e) => setBudget(e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">
                                You'll see a warning on the dashboard if you exceed this limit. Set to 0 to disable.
                            </p>
                        </div>
                    </CardContent>
                    <CardFooter>
                        <Button type="submit" disabled={budgetSaving} className="w-full sm:w-auto">
                            {budgetSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                            Update Budget
                        </Button>
                    </CardFooter>
                </form>
            </Card>

            {/* Account Info */}
            <Card className="border-border/50">
                <CardContent className="pt-6">
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                        <div className="space-y-1">
                            <h3 className="text-sm font-medium text-muted-foreground">Account Information</h3>
                            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                                <span><strong>Username:</strong> @{userData?.username}</span>
                                {userData?.phone && <span><strong>Phone:</strong> {userData.phone}</span>}
                                {joinDate && <span><strong>Joined:</strong> {joinDate}</span>}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
};

export default Profile;
