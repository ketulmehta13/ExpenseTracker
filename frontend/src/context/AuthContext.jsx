import React, { createContext, useState, useEffect, useContext } from 'react';
import api from '../services/api';
import { jwtDecode } from 'jwt-decode';

export const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        checkUserStatus();
    }, []);

    const checkUserStatus = () => {
        // CHANGED: Using sessionStorage for auto-logout when tab closes
        const token = sessionStorage.getItem('access_token');
        
        if (token) {
            try {
                const decoded = jwtDecode(token);
                // Check if token expired
                if (decoded.exp * 1000 < Date.now()) {
                    logout();
                } else {
                    setUser({ id: decoded.user_id });
                }
            } catch (error) {
                logout();
            }
        }
        setLoading(false);
    };

    const login = async (username, password) => {
        try {
            const lowerUsername = username.toLowerCase();
            const response = await api.post('/auth/login/', { username: lowerUsername, password });
            
            // CHANGED: Storing in sessionStorage so it clears on exit
            sessionStorage.setItem('access_token', response.data.access);
            sessionStorage.setItem('refresh_token', response.data.refresh);
            
            // Update the user state immediately
            const decoded = jwtDecode(response.data.access);
            setUser({ id: decoded.user_id });
            
            return response.data;
        } catch (error) {
            // Ensure state is clean if login fails
            logout();
            throw error; 
        }
    };

    const register = async (username, email, password) => {
        // 1. Hit the register endpoint
        const lowerUsername = username.toLowerCase();
        const lowerEmail = email.toLowerCase();
        await api.post('/auth/register/', { username: lowerUsername, email: lowerEmail, password });
        
        // 2. Automatically login. 
        // NOTE: If this fails (e.g., password @Fast rejected by login but not register), 
        // the error will bubble up to your Register.js catch block.
        await login(lowerUsername, password);
    };

    const logout = () => {
        // CHANGED: Clear sessionStorage
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, login, register, logout, loading }}>
            {!loading && children}
        </AuthContext.Provider>
    );
};