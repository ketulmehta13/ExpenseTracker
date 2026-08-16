import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    LayoutDashboard,
    ReceiptText,
    BarChart3,
    Tag,
    Settings,
    LogOut,
    X,
    Plus,
    ChevronDown,
    User,
    Wallet
} from 'lucide-react';
import logoIcon from '../assets/logo-icon.png';
import { cn } from '../lib/utils';
import { Toaster } from 'sonner';
import TransactionModal from '../components/TransactionModal';

const navItems = [
    { path: '/dashboard', name: 'Dashboard', icon: LayoutDashboard, end: true },
    { path: '/dashboard/transactions', name: 'Transactions', icon: ReceiptText },
    { path: '/dashboard/analytics', name: 'Reports', icon: BarChart3 },
    { path: '/dashboard/categories', name: 'Categories', icon: Tag },
    { path: '/dashboard/settings', name: 'Settings', icon: Settings },
];

const bottomTabs = [
    { path: '/dashboard', name: 'Dashboard', icon: LayoutDashboard, end: true },
    { path: '/dashboard/transactions', name: 'Transactions', icon: ReceiptText },
    { path: '/dashboard/analytics', name: 'Reports', icon: BarChart3 },
    { path: '/dashboard/settings', name: 'Settings', icon: Settings },
];

const MainLayout = () => {
    const { logout, user } = useAuth();
    const navigate = useNavigate();
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [userMenuOpen, setUserMenuOpen] = useState(false);
    const [txModal, setTxModal] = useState({ open: false, type: 'EXPENSE', transaction: null });

    const handleLogout = async () => {
        try {
            await logout();
        } catch {/* ignore */}
        navigate('/login');
    };

    const openAddModal = (type) => {
        setTxModal({ open: true, type, transaction: null });
        setSidebarOpen(false);
    };

    const displayName =
        user?.user_metadata?.first_name ||
        user?.user_metadata?.username ||
        user?.email?.split('@')[0] ||
        'User';

    const initials = displayName.slice(0, 2).toUpperCase();

    return (
        <div className="flex h-screen w-full bg-background overflow-hidden text-foreground">
            {/* ───── GLOBAL TOAST PROVIDER (WHITE & GREEN) ───── */}
            <Toaster
                position="top-right"
                richColors
                toastOptions={{
                    classNames: {
                        toast: 'bg-card border border-border text-foreground shadow-lg rounded-xl',
                    },
                }}
            />

            {/* ───── MOBILE OVERLAY ───── */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-foreground/20 backdrop-blur-sm lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* ───── SIDEBAR (WHITE & GREEN THEME) ───── */}
            <aside
                className={cn(
                    'fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-card border-r border-border transform transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0 shadow-sm lg:shadow-none',
                    sidebarOpen ? 'translate-x-0' : '-translate-x-full'
                )}
            >
                {/* Brand Logo */}
                <div className="flex h-16 items-center gap-3 px-5 border-b border-border flex-shrink-0 bg-surface">
                    <img
                        src={logoIcon}
                        alt="Expense Tracker"
                        className="h-8 w-8 rounded-lg object-contain shadow-sm shadow-primary/20"
                    />
                    <div className="flex flex-col">
                        <span className="font-display text-base font-bold text-foreground leading-tight">
                            Expense Tracker
                        </span>
                        <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">
                            Personal Finance
                        </span>
                    </div>
                    <button
                        onClick={() => setSidebarOpen(false)}
                        className="ml-auto lg:hidden text-muted-foreground hover:text-foreground transition-colors p-1"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Quick-add buttons */}
                <div className="p-3 border-b border-border flex gap-2 bg-surface-muted/50">
                    <button
                        onClick={() => openAddModal('INCOME')}
                        className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-income/10 text-income py-2 text-xs font-semibold hover:bg-income/20 transition-all active:scale-95"
                    >
                        <Plus size={14} />
                        Income
                    </button>
                    <button
                        onClick={() => openAddModal('EXPENSE')}
                        className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-expense/10 text-expense py-2 text-xs font-semibold hover:bg-expense/20 transition-all active:scale-95"
                    >
                        <Plus size={14} />
                        Expense
                    </button>
                </div>

                {/* Navigation Links */}
                <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.end}
                            onClick={() => setSidebarOpen(false)}
                            className={({ isActive }) =>
                                cn(
                                    'flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all group',
                                    isActive
                                        ? 'bg-primary/10 text-primary font-semibold border-l-4 border-primary pl-[10px]'
                                        : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
                                )
                            }
                        >
                            {({ isActive }) => (
                                <>
                                    <item.icon
                                        size={18}
                                        className={cn(isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground')}
                                    />
                                    <span>{item.name}</span>
                                </>
                            )}
                        </NavLink>
                    ))}
                </nav>

                {/* Footer User Info + Logout */}
                <div className="border-t border-border p-3 bg-surface">
                    <button
                        onClick={handleLogout}
                        className="flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                    >
                        <LogOut size={18} />
                        Logout
                    </button>
                </div>
            </aside>

            {/* ───── MAIN CONTENT WRAPPER ───── */}
            <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
                {/* Header Top Bar */}
                <header className="flex h-16 flex-shrink-0 items-center gap-3 px-4 lg:px-8 border-b border-border bg-card/90 backdrop-blur-md">
                    {/* Hamburger Button (mobile only) */}
                    <button
                        className="lg:hidden flex items-center justify-center h-9 w-9 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground transition-colors border border-border"
                        onClick={() => setSidebarOpen(true)}
                        aria-label="Open menu"
                    >
                        <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                            <path fillRule="evenodd" d="M3 5h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2z" clipRule="evenodd" />
                        </svg>
                    </button>

                    {/* Mobile Brand Name */}
                    <Link to="/dashboard" className="lg:hidden flex items-center gap-2">
                        <img src={logoIcon} alt="Expense Tracker" className="h-7 w-7 rounded-lg object-contain shadow-sm" />
                        <span className="font-display text-base font-bold text-foreground">Expense Tracker</span>
                    </Link>

                    <div className="flex-1" />

                    {/* User Profile Dropdown */}
                    <div className="relative">
                        <button
                            id="user-menu-btn"
                            onClick={() => setUserMenuOpen((v) => !v)}
                            className="flex items-center gap-2.5 rounded-xl px-3 py-1.5 hover:bg-muted transition-colors border border-transparent hover:border-border"
                        >
                            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold shadow-sm shadow-primary/30">
                                {initials}
                            </div>
                            <div className="hidden sm:flex flex-col text-left">
                                <span className="text-sm font-semibold text-foreground max-w-[120px] truncate leading-tight">
                                    {displayName}
                                </span>
                                <span className="text-[10px] text-muted-foreground leading-none">
                                    Member
                                </span>
                            </div>
                            <ChevronDown size={14} className="text-muted-foreground hidden sm:block" />
                        </button>

                        {userMenuOpen && (
                            <>
                                <div
                                    className="fixed inset-0 z-10"
                                    onClick={() => setUserMenuOpen(false)}
                                />
                                <div className="absolute right-0 top-full mt-1.5 z-20 w-52 rounded-2xl bg-card border border-border shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                                    <div className="px-4 py-3 border-b border-border bg-surface-muted/50">
                                        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">Signed in as</p>
                                        <p className="text-sm font-semibold text-foreground truncate">{user?.email}</p>
                                    </div>
                                    <div className="p-1.5">
                                        <Link
                                            to="/dashboard/settings"
                                            onClick={() => setUserMenuOpen(false)}
                                            className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
                                        >
                                            <User size={16} className="text-primary" />
                                            Profile & Settings
                                        </Link>
                                        <Link
                                            to="/dashboard/categories"
                                            onClick={() => setUserMenuOpen(false)}
                                            className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
                                        >
                                            <Tag size={16} className="text-primary" />
                                            Manage Categories
                                        </Link>
                                        <div className="my-1 border-t border-border" />
                                        <button
                                            onClick={() => { setUserMenuOpen(false); handleLogout(); }}
                                            className="flex w-full items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors"
                                        >
                                            <LogOut size={16} />
                                            Logout
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </header>

                {/* Page Content Viewport */}
                <div className="flex-1 overflow-x-hidden overflow-y-auto p-4 md:p-6 lg:p-8 pb-24 lg:pb-8">
                    <Outlet />
                </div>

                {/* ───── MOBILE BOTTOM TAB BAR ───── */}
                <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 flex h-16 items-stretch bg-card/95 backdrop-blur-md border-t border-border shadow-lg">
                    {bottomTabs.map((tab) => (
                        <NavLink
                            key={tab.path}
                            to={tab.path}
                            end={tab.end}
                            className={({ isActive }) =>
                                cn(
                                    'flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-colors pt-1',
                                    isActive
                                        ? 'text-primary'
                                        : 'text-muted-foreground hover:text-foreground'
                                )
                            }
                        >
                            {({ isActive }) => (
                                <>
                                    <div className={cn(
                                        'flex h-7 w-10 items-center justify-center rounded-xl transition-all',
                                        isActive ? 'bg-primary/15' : ''
                                    )}>
                                        <tab.icon size={19} />
                                    </div>
                                    <span>{tab.name}</span>
                                </>
                            )}
                        </NavLink>
                    ))}
                    {/* Center Add Action */}
                    <button
                        onClick={() => openAddModal('EXPENSE')}
                        className="flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-semibold text-expense hover:text-expense/80 transition-colors pt-1"
                    >
                        <div className="flex h-7 w-10 items-center justify-center rounded-xl bg-expense/15">
                            <Plus size={19} />
                        </div>
                        <span>Add</span>
                    </button>
                </nav>
            </main>

            {/* ───── TRANSACTION MODAL ───── */}
            <TransactionModal
                isOpen={txModal.open}
                defaultType={txModal.type}
                transaction={txModal.transaction}
                onClose={() => setTxModal({ open: false, type: 'EXPENSE', transaction: null })}
                onSuccess={() => {
                    window.dispatchEvent(new CustomEvent('transaction-updated'));
                }}
            />
        </div>
    );
};

export default MainLayout;
