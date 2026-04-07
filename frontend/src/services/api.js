import axios from 'axios';

/**
 * Resolves the Backend API URL.
 * 1. Checks for VITE_API_URL (set in Vercel Environment Variables).
 * 2. Falls back to localhost for local development.
 */
const getBaseUrl = () => {
    // 1. If we are on a LAN/Mobile device (not localhost), dynamically construct URL
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;
        if (hostname !== 'localhost' && hostname !== '127.0.0.1' && hostname !== '') {
            return `http://${hostname}:8000/api`;
        }
    }
    // 2. Otherwise use the env variable if provided
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }
    // 3. Fallback
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
// Automatically attaches the JWT 'access_token' to every outgoing request
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
// Handles 401 errors (expired tokens) by attempting to use a 'refresh_token'
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        // If error is 401 and we haven't retried this request yet
        if (error.response && error.response.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                const refreshToken = sessionStorage.getItem('refresh_token');

                if (refreshToken) {
                    // Attempt to get a new access token from Django
                    const response = await axios.post(`${API_URL}/auth/token/refresh/`, {
                        refresh: refreshToken
                    });

                    const newAccessToken = response.data.access;

                    // Store the new token
                    sessionStorage.setItem('access_token', newAccessToken);

                    // Update the header and retry the original request
                    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                    return api(originalRequest);
                }
            } catch (err) {
                // If refresh fails, clear everything and kick user to login
                sessionStorage.removeItem('access_token');
                sessionStorage.removeItem('refresh_token');
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default api;