import { format, parseISO, subMonths } from 'date-fns';

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
