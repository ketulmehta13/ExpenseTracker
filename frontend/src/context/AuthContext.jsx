import React, { createContext, useState, useEffect, useContext, useCallback, useMemo } from 'react';
import { supabase } from '../services/supabaseClient';

export const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

const AuthSplash = () => (
    <div className="h-dvh w-full flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
            <svg className="animate-spin h-10 w-10 text-primary" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            <p className="text-sm text-muted-foreground font-medium">Loading your account…</p>
        </div>
    </div>
);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Check the current session on mount
        supabase.auth.getSession()
            .then(({ data: { session } }) => setUser(session?.user ?? null))
            .catch((err) => console.error('Failed to restore session:', err))
            .finally(() => setLoading(false));

        // Listen for auth state changes (login, logout, token refresh — all automatic)
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
            // Supabase falls back to the Site URL when /reset-password isn't on the
            // redirect allow-list; send password-recovery sessions to the reset form.
            if (event === 'PASSWORD_RECOVERY' && window.location.pathname !== '/reset-password') {
                window.location.replace('/reset-password');
                return;
            }

            const nextUser = session?.user ?? null;
            // Token refreshes and tab refocus re-emit the same user as a new object.
            // Keep the existing one so effects that depend on the user don't refetch.
            setUser((prev) => (event !== 'USER_UPDATED' && prev?.id === nextUser?.id ? prev : nextUser));
        });

        return () => subscription.unsubscribe();
    }, []);

    const login = useCallback(async (email, password) => {
        const { data, error } = await supabase.auth.signInWithPassword({
            email: email.toLowerCase(),
            password,
        });
        if (error) throw error;
        return data;
    }, []);

    const register = useCallback(async (username, email, password) => {
        const { data, error } = await supabase.auth.signUp({
            email: email.toLowerCase(),
            password,
            options: {
                data: { username: username.toLowerCase() },
            },
        });
        if (error) throw error;
        return data;
    }, []);

    // The code from the "confirm your sign-up" email. A correct code confirms the address and
    // signs the user in, and onAuthStateChange then sets `user`.
    const verifyEmailCode = useCallback(async (email, code) => {
        const { data, error } = await supabase.auth.verifyOtp({
            email: email.toLowerCase(),
            token: code.replace(/\s/g, ''),
            type: 'email',
        });
        if (error) throw error;
        return data;
    }, []);

    const resendEmailCode = useCallback(async (email) => {
        const { error } = await supabase.auth.resend({ type: 'signup', email: email.toLowerCase() });
        if (error) throw error;
    }, []);

    // Leaves the app for Google's sign-in page. Supabase sends the user back to /login, which
    // moves on to the dashboard once the session is in place (or shows the error, if any).
    const loginWithGoogle = useCallback(async () => {
        const { error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: { redirectTo: `${window.location.origin}/login` },
        });
        if (error) throw error;
    }, []);

    // scope 'local' ends only this browser's session; the default ('global') signs out every device
    const logout = useCallback(async ({ scope } = {}) => {
        const { error } = await supabase.auth.signOut(scope ? { scope } : undefined);
        if (error) throw error;
        setUser(null);
    }, []);

    const value = useMemo(
        () => ({ user, login, register, logout, verifyEmailCode, resendEmailCode, loginWithGoogle, loading }),
        [user, login, register, logout, verifyEmailCode, resendEmailCode, loginWithGoogle, loading]
    );

    return (
        <AuthContext.Provider value={value}>
            {loading ? <AuthSplash /> : children}
        </AuthContext.Provider>
    );
};
