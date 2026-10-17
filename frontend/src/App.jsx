import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider, useAuth } from './context/AuthContext';
import { PlanProvider } from './context/PlanContext';
import { ThemeProvider } from './components/ThemeProvider';
import ErrorBoundary from './components/ErrorBoundary';
import MainLayout from './layouts/MainLayout';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Analytics from './pages/Analytics';
import Profile from './pages/Profile';
import Home from './pages/Home';
import Categories from './pages/Categories';
import Upgrade from './pages/Upgrade';
import NotFound from './pages/NotFound';

// AuthProvider shows a splash until the session is restored, so `user` is settled here
const ProtectedRoute = ({ children }) => {
    const { user } = useAuth();
    return user ? children : <Navigate to="/login" replace />;
};

function AppRoutes() {
    return (
        <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />

            <Route
                path="/dashboard"
                element={
                    <ProtectedRoute>
                        <MainLayout />
                    </ProtectedRoute>
                }
            >
                <Route index element={<Dashboard />} />
                <Route path="transactions" element={<Transactions />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="categories" element={<Categories />} />
                <Route path="settings" element={<Profile />} />
                <Route path="upgrade" element={<Upgrade />} />
                <Route path="profile" element={<Navigate to="/dashboard/settings" replace />} />
            </Route>

            {/* 404 */}
            <Route path="*" element={<NotFound />} />
        </Routes>
    );
}

function App() {
    return (
        <ErrorBoundary>
            <ThemeProvider>
                {/* Mounted once at the root so toasts work on every page, including the auth pages */}
                <Toaster
                    position="top-right"
                    richColors
                    toastOptions={{
                        classNames: {
                            toast: 'bg-card border border-border text-foreground shadow-lg rounded-xl',
                        },
                    }}
                />
                <AuthProvider>
                    <PlanProvider>
                        <Router>
                            <AppRoutes />
                        </Router>
                    </PlanProvider>
                </AuthProvider>
            </ThemeProvider>
        </ErrorBoundary>
    );
}

export default App;

