import axios from 'axios';

/**
 * Resolves the Backend API URL.
 */
const getBaseUrl = () => {
    // 1. Check for Environment Variable (Priority for Vercel)
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }

    // 2. Hardcoded Production Fallback
    // This is used for easy testing of specific environments
    if (import.meta.env.PROD || (typeof window !== 'undefined' && window.location.hostname.includes('vercel.app'))) {
        // Updated to the most likely recent URL found in .env.local
        return 'https://expensetracker-production-de67.up.railway.app/api';
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
    return 'http://127.0.0.1:8000/api';
};

// Ensure the URL ends with a slash because Django is picky about trailing slashes
const API_URL = getBaseUrl().endsWith('/') ? getBaseUrl() : `${getBaseUrl()}/`;

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

        // If error is 401 and we haven't retried yet
        if (error.response && error.response.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                const refreshToken = sessionStorage.getItem('refresh_token');

                if (refreshToken) {
                    // We use axios (not api) here to avoid the interceptor loop
                    const response = await axios.post(`${API_URL}auth/token/refresh/`, {
                        refresh: refreshToken
                    });

                    const newAccessToken = response.data.access;
                    sessionStorage.setItem('access_token', newAccessToken);

                    // Update headers and retry original request
                    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                    return api(originalRequest);
                }
            } catch (err) {
                // If refresh fails, log out the user
                sessionStorage.removeItem('access_token');
                sessionStorage.removeItem('refresh_token');
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default api;