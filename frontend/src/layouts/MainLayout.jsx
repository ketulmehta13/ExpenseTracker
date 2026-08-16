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
    Moon,
    Sun,
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
    const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'));

    const handleLogout = async () => {
        try {
            await logout();
        } catch {/* ignore */}
        navigate('/login');
    };

    const toggleDark = () => {
        document.documentElement.classList.toggle('dark');
        setIsDark((v) => !v);
        localStorage.setItem('et-theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
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
        <div className="flex h-screen w-full bg-background overflow-hidden">
            {/* ───── GLOBAL TOAST PROVIDER ───── */}
            <Toaster
                position="top-right"
                richColors
                toastOptions={{
                    classNames: {
                        toast: 'bg-card border border-border text-foreground shadow-xl rounded-xl',
                    },
                }}
            />

            {/* ───── MOBILE OVERLAY ───── */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* ───── SIDEBAR ───── */}
            <aside
                className={cn(
                    'fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-sidebar border-r border-sidebar-border transform transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0',
                    sidebarOpen ? 'translate-x-0' : '-translate-x-full'
                )}
            >
                {/* Logo */}
                <div className="flex h-16 items-center gap-3 px-5 border-b border-sidebar-border flex-shrink-0">
                    <img
                        src={logoIcon}
                        alt="Expense Tracker"
                        className="h-8 w-8 rounded-lg object-contain"
                    />
                    <span className="font-display text-lg font-semibold text-white leading-tight">
                        Expense<br />Tracker
                    </span>
                    <button
                        onClick={() => setSidebarOpen(false)}
                        className="ml-auto lg:hidden text-white/60 hover:text-white transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Quick-add buttons */}
                <div className="px-4 py-3 border-b border-sidebar-border flex gap-2">
                    <button
                        onClick={() => openAddModal('INCOME')}
                        className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-income/20 text-income py-2 text-xs font-semibold hover:bg-income/30 transition-colors"
                    >
                        <Plus size={14} />
                        Income
                    </button>
                    <button
                        onClick={() => openAddModal('EXPENSE')}
                        className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-expense/20 text-expense py-2 text-xs font-semibold hover:bg-expense/30 transition-colors"
                    >
                        <Plus size={14} />
                        Expense
                    </button>
                </div>

                {/* Nav */}
                <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            end={item.end}
                            onClick={() => setSidebarOpen(false)}
                            className={({ isActive }) =>
                                cn(
                                    'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all group',
                                    isActive
                                        ? 'bg-white/10 text-white border-l-2 border-sidebar-active pl-[10px]'
                                        : 'text-white/60 hover:text-white hover:bg-white/5'
                                )
                            }
                        >
                            {({ isActive }) => (
                                <>
                                    <item.icon
                                        size={18}
                                        className={cn(isActive ? 'text-sidebar-active' : '')}
                                    />
                                    <span>{item.name}</span>
                                </>
                            )}
                        </NavLink>
                    ))}
                </nav>

                {/* Footer — user + logout */}
                <div className="border-t border-sidebar-border p-3">
                    <button
                        onClick={handleLogout}
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-white/60 hover:text-white hover:bg-white/5 transition-all"
                    >
                        <LogOut size={18} />
                        Logout
                    </button>
                </div>
            </aside>

            {/* ───── MAIN CONTENT ───── */}
            <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
                {/* Top bar */}
                <header className="flex h-14 lg:h-16 flex-shrink-0 items-center gap-3 px-4 lg:px-6 border-b border-border bg-card/80 backdrop-blur-md">
                    {/* Hamburger — mobile only */}
                    <button
                        className="lg:hidden flex items-center justify-center h-9 w-9 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        onClick={() => setSidebarOpen(true)}
                        aria-label="Open menu"
                    >
                        <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                            <path fillRule="evenodd" d="M3 5h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2z" clipRule="evenodd" />
                        </svg>
                    </button>

                    {/* Mobile logo */}
                    <Link to="/dashboard" className="lg:hidden flex items-center gap-2">
                        <img src={logoIcon} alt="Expense Tracker" className="h-7 w-7 rounded-lg object-contain" />
                        <span className="font-display text-base font-semibold text-foreground">Tracker</span>
                    </Link>

                    <div className="flex-1" />

                    {/* Dark mode toggle */}
                    <button
                        onClick={toggleDark}
                        className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        aria-label="Toggle dark mode"
                    >
                        {isDark ? <Sun size={18} /> : <Moon size={18} />}
                    </button>

                    {/* User menu */}
                    <div className="relative">
                        <button
                            id="user-menu-btn"
                            onClick={() => setUserMenuOpen((v) => !v)}
                            className="flex items-center gap-2 rounded-xl px-2.5 py-1.5 hover:bg-muted transition-colors"
                        >
                            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                                {initials}
                            </div>
                            <span className="hidden sm:block text-sm font-medium text-foreground max-w-[100px] truncate">
                                {displayName}
                            </span>
                            <ChevronDown size={14} className="text-muted-foreground hidden sm:block" />
                        </button>

                        {userMenuOpen && (
                            <>
                                <div
                                    className="fixed inset-0 z-10"
                                    onClick={() => setUserMenuOpen(false)}
                                />
                                <div className="absolute right-0 top-full mt-1.5 z-20 w-48 rounded-xl bg-card border border-border shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                                    <div className="px-3 py-2.5 border-b border-border">
                                        <p className="text-xs text-muted-foreground">Signed in as</p>
                                        <p className="text-sm font-medium text-foreground truncate">{user?.email}</p>
                                    </div>
                                    <div className="py-1">
                                        <Link
                                            to="/dashboard/settings"
                                            onClick={() => setUserMenuOpen(false)}
                                            className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                                        >
                                            <User size={15} />
                                            Profile & Settings
                                        </Link>
                                        <button
                                            onClick={() => { setUserMenuOpen(false); handleLogout(); }}
                                            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors"
                                        >
                                            <LogOut size={15} />
                                            Logout
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </header>

                {/* Page content */}
                <div className="flex-1 overflow-x-hidden overflow-y-auto p-4 md:p-6 pb-24 lg:pb-6">
                    <Outlet />
                </div>

                {/* ───── BOTTOM TAB BAR (mobile only) ───── */}
                <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 flex h-16 items-stretch bg-card/95 backdrop-blur-md border-t border-border">
                    {bottomTabs.map((tab) => (
                        <NavLink
                            key={tab.path}
                            to={tab.path}
                            end={tab.end}
                            className={({ isActive }) =>
                                cn(
                                    'flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors pt-1',
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
                                        <tab.icon size={20} />
                                    </div>
                                    <span>{tab.name}</span>
                                </>
                            )}
                        </NavLink>
                    ))}
                    {/* Center Add button */}
                    <button
                        onClick={() => openAddModal('EXPENSE')}
                        className="flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-expense hover:text-expense/80 transition-colors pt-1"
                    >
                        <div className="flex h-7 w-10 items-center justify-center rounded-xl bg-expense/15">
                            <Plus size={20} />
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
                    // Pages re-fetch on their own via event; dispatch custom event
                    window.dispatchEvent(new CustomEvent('transaction-updated'));
                }}
            />
        </div>
    );
};

export default MainLayout;
