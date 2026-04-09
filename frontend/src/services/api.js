import axios from 'axios';

/**
 * Resolves the Backend API URL.
 * Priority:
 *   1. VITE_API_URL environment variable (set in Vercel or .env file)
 *   2. Production fallback (when deployed to Vercel)
 *   3. Local development fallback
 */
const getBaseUrl = () => {
    // 1. Environment variable (works locally via .env and on Vercel via dashboard)
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }

    // 2. Local development fallback
    return 'http://127.0.0.1:8000/api';
};

// Ensure the URL ends with a slash because Django requires trailing slashes
const baseUrl = getBaseUrl();
const API_URL = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;

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