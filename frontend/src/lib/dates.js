import {
    endOfMonth, endOfWeek, endOfYear, format, parseISO, startOfMonth, startOfWeek, startOfYear,
    subDays, subMonths, subWeeks,
} from 'date-fns';

/**
 * Date helpers. Transaction dates are calendar dates (YYYY-MM-DD) in the user's
 * local timezone, so never derive them with toISOString() or parse them with
 * new Date('YYYY-MM-DD') — both use UTC and shift the day around midnight.
 */

/** Format a Date as YYYY-MM-DD in local time. */
export const toISODate = (date) => format(date, 'yyyy-MM-dd');

/** Today's date as YYYY-MM-DD in local time. */
export const todayISODate = () => toISODate(new Date());

/** Parse a YYYY-MM-DD or ISO timestamp string; date-only strings become local midnight. */
export const parseDate = (value) => (value instanceof Date ? value : parseISO(value));

/** Earliest date (YYYY-MM-DD) visible on a plan limited to `months` of history. */
export const historyCutoffISODate = (months) => toISODate(subMonths(new Date(), months));

/**
 * Named periods for filters. Weeks start on Monday. `to` is null for rolling periods
 * ("last 30 days"), so transactions dated later are still included, as before.
 */
export const PERIODS = [
    { id: 'this_week', label: 'This week' },
    { id: 'last_week', label: 'Last week' },
    { id: 'this_month', label: 'This month' },
    { id: 'last_month', label: 'Last month' },
    { id: 'last_30', label: 'Last 30 days' },
    { id: 'last_3m', label: 'Last 3 months' },
    { id: 'this_year', label: 'This year' },
    { id: 'all', label: 'All time' },
];

/** The date range { from, to } (YYYY-MM-DD, or null for open-ended) of a period id. */
export const periodRange = (id, now = new Date()) => {
    const week = { weekStartsOn: 1 };
    const range = (from, to) => ({ from: from ? toISODate(from) : null, to: to ? toISODate(to) : null });
    switch (id) {
        case 'this_week': return range(startOfWeek(now, week), endOfWeek(now, week));
        case 'last_week': return range(startOfWeek(subWeeks(now, 1), week), endOfWeek(subWeeks(now, 1), week));
        case 'this_month': return range(startOfMonth(now), endOfMonth(now));
        case 'last_month': return range(startOfMonth(subMonths(now, 1)), endOfMonth(subMonths(now, 1)));
        case 'last_30': return range(subDays(now, 29), null);
        case 'last_3m': return range(subDays(now, 89), null);
        case 'this_year': return range(startOfYear(now), endOfYear(now));
        default: return range(null, null);
    }
};

/** Whether a transaction date (YYYY-MM-DD or ISO timestamp) falls in a { from, to } range. */
export const inRange = (date, { from, to }) => {
    const day = String(date).slice(0, 10);
    return (!from || day >= from) && (!to || day <= to);
};
