import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    LayoutDashboard,
    ReceiptText,
    BarChart3,
    UserCircle,
    LogOut,
    Menu,
    X,
    Wallet
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';

const MainLayout = () => {
    const { logout, user } = useAuth();
    const navigate = useNavigate();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const navItems = [
        { path: '/dashboard', name: 'Dashboard', icon: <LayoutDashboard className="h-5 w-5" /> },
        { path: '/dashboard/transactions', name: 'Transactions', icon: <ReceiptText className="h-5 w-5" /> },
        { path: '/dashboard/analytics', name: 'Analytics', icon: <BarChart3 className="h-5 w-5" /> },
        { path: '/dashboard/profile', name: 'Profile', icon: <UserCircle className="h-5 w-5" /> },
    ];

    return (
        <div className="flex h-screen w-full bg-background overflow-hidden relative">
            {/* Mobile Sidebar Overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/80 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                ></div>
            )}

            {/* Sidebar */}
            <aside className={cn(
                "fixed inset-y-0 left-0 z-50 w-64 bg-card border-r flex flex-col transform transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0",
                sidebarOpen ? 'translate-x-0' : '-translate-x-full'
            )}>
                <div className="flex h-16 items-center flex-shrink-0 px-6 border-b">
                    <Wallet className="h-8 w-8 text-primary mr-3" />
                    <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-blue-400">
                        Expensify
                    </h2>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="ml-auto lg:hidden"
                        onClick={() => setSidebarOpen(false)}
                    >
                        <X className="h-5 w-5" />
                    </Button>
                </div>

                <div className="flex-1 overflow-y-auto py-4 flex flex-col">
                    <nav className="flex-1 px-4 space-y-1.5">
                        {navItems.map((item) => (
                            <NavLink
                                key={item.name}
                                to={item.path}
                                end={item.path === '/dashboard'}
                                onClick={() => setSidebarOpen(false)}
                                className={({ isActive }) =>
                                    cn(
                                        "flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                                        isActive
                                            ? "bg-primary/10 text-primary"
                                            : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                                    )
                                }
                            >
                                {item.icon}
                                <span>{item.name}</span>
                            </NavLink>
                        ))}
                    </nav>

                    <div className="p-4 border-t space-y-4">

                        <Button
                            variant="destructive"
                            className="w-full justify-start mt-2"
                            onClick={handleLogout}
                        >
                            <LogOut className="h-4 w-4 mr-2" />
                            Logout
                        </Button>
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-background/95">
                {/* Header (Mobile Only Toggle) */}
                <header className="lg:hidden flex h-16 flex-shrink-0 items-center justify-between px-4 border-b bg-card">
                    <div className="flex items-center">
                        <Wallet className="h-6 w-6 text-primary mr-2" />
                        <h1 className="text-lg font-bold">Expensify</h1>
                    </div>
                    <div className="flex items-center space-x-2">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setSidebarOpen(true)}
                        >
                            <Menu className="h-6 w-6" />
                        </Button>
                    </div>
                </header>

                <div className="flex-1 overflow-x-hidden overflow-y-auto p-4 md:p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    );
};

export default MainLayout;
