/**
 * Supabase Auth's public settings: which sign-in providers are switched on in the dashboard.
 * The Google button shows only when Google is enabled there, so the app never offers a
 * sign-in method that would end on an error page. Fetched once per page load.
 */
let settingsPromise = null;

export function getAuthSettings() {
    if (!settingsPromise) {
        const url = (import.meta.env.VITE_SUPABASE_URL || '').replace(/\/+$/, '');
        settingsPromise = fetch(`${url}/auth/v1/settings`, {
            headers: { apikey: import.meta.env.VITE_SUPABASE_ANON_KEY || '' },
        })
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null)
            .then((settings) => ({ google: Boolean(settings?.external?.google) }));
    }
    return settingsPromise;
}
