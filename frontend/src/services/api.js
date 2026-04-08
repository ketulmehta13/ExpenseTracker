import axios from 'axios';

/**
 * Resolves the Backend API URL.
 * 1. Checks for VITE_API_URL (set in Vercel/Local Environment Variables).
 * 2. Falls back to your specific Railway production URL.
 * 3. Falls back to localhost for local development.
 */
const getBaseUrl = () => {
    // 1. Check for the Environment Variable (Best practice for Vercel)
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }

    // 2. Hardcoded Production Fallback (Your specific Railway URL)
    // We add /api at the end to match your Django URL patterns
    if (import.meta.env.PROD) {
        return 'https://expensetracker-production-9e2d.up.railway.app/api';
    }

    // 3. Logic for LAN/Mobile device testing locally
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;
        const isIpAddress = /^[0-9.]+$/.test(hostname);
        if (isIpAddress && hostname !== '127.0.0.1') {
            return `http://${hostname}:8000/api`;
        }
    }
    
    // 4. Final Local Fallback
    return 'http://localhost:8000/api';
};

const API_URL = getBaseUrl();

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// --- Request Interceptor ---
api.interceptors.request.use(
    (config) => {
        const token = sessionStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// --- Response Interceptor ---
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response && error.response.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                const refreshToken = sessionStorage.getItem('refresh_token');

                if (refreshToken) {
                    const response = await axios.post(`${API_URL}/auth/token/refresh/`, {
                        refresh: refreshToken
                    });

                    const newAccessToken = response.data.access;
                    sessionStorage.setItem('access_token', newAccessToken);

                    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                    return api(originalRequest);
                }
            } catch (err) {
                sessionStorage.removeItem('access_token');
                sessionStorage.removeItem('refresh_token');
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default api;