/**
 * Formatting utilities — used across the entire app.
 * All currency/date display should go through these functions.
 */

/**
 * Format a number as currency using Intl.NumberFormat.
 * Currency defaults to the value stored in localStorage (set via Settings page),
 * falling back to INR.
 */
export const formatCurrency = (amount, currencyOverride) => {
    const currency =
        currencyOverride ||
        localStorage.getItem('et-currency') ||
        'INR';

    const num = parseFloat(amount);
    if (isNaN(num)) return '—';

    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(num);
};

/**
 * Format a date string for consistent display across the app.
 * @param {string|Date} dateStr
 * @param {'short'|'medium'|'long'|'relative'} [style='medium']
 */
export const formatDate = (dateStr, style = 'medium') => {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return '—';

    if (style === 'short') {
        return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    }
    if (style === 'long') {
        return date.toLocaleDateString('en-IN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        });
    }
    if (style === 'relative') {
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / 86400000);
        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;
        return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    }
    // medium (default)
    return date.toLocaleDateString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
};

/**
 * Returns a time-aware greeting string.
 */
export const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
};

/**
 * Format a percentage with sign and fixed decimals.
 */
export const formatPercent = (value, decimals = 1) => {
    const num = parseFloat(value);
    if (isNaN(num)) return '—';
    const sign = num > 0 ? '+' : '';
    return `${sign}${num.toFixed(decimals)}%`;
};
