import { useEffect, useRef, useCallback } from 'react';

const ACTIVITY_EVENTS = [
  'mousedown',
  'mousemove',
  'keydown',
  'scroll',
  'touchstart',
  'click',
];

/**
 * useAutoLogout — Automatically logs the user out after a period of inactivity,
 * and when the tab has been hidden/minimized for longer than the timeout.
 *
 * @param {Object} options
 * @param {number} options.timeoutMinutes - Idle timeout in minutes (default: 15)
 * @param {Function} options.onLogout - Callback to execute on logout
 * @param {number} options.warnBeforeMs - Duration in ms to warn before logout (default: 60000 = 60s)
 * @param {Function} [options.onWarn] - Callback to execute to warn user
 */
export function useAutoLogout({ timeoutMinutes = 15, onLogout, warnBeforeMs = 60000, onWarn }) {
  const timeoutRef = useRef(null);
  const warnRef = useRef(null);
  const lastActiveRef = useRef(Date.now());

  const clearTimers = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (warnRef.current) clearTimeout(warnRef.current);
  }, []);

  const resetTimer = useCallback(() => {
    lastActiveRef.current = Date.now();
    clearTimers();

    const timeoutMs = timeoutMinutes * 60 * 1000;

    // Optional: warn the user shortly before auto-logout (e.g. show a toast notification)
    if (onWarn && warnBeforeMs > 0 && warnBeforeMs < timeoutMs) {
      warnRef.current = setTimeout(() => {
        onWarn();
      }, timeoutMs - warnBeforeMs);
    }

    timeoutRef.current = setTimeout(() => {
      onLogout();
    }, timeoutMs);
  }, [timeoutMinutes, onLogout, onWarn, warnBeforeMs, clearTimers]);

  useEffect(() => {
    // Start the timer immediately on mount.
    resetTimer();

    // Reset on any user activity.
    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, resetTimer, { passive: true })
    );

    // Handle visibility change (tab minimized or switched away)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const elapsed = Date.now() - lastActiveRef.current;
        const timeoutMs = timeoutMinutes * 60 * 1000;
        if (elapsed >= timeoutMs) {
          onLogout();
        } else {
          resetTimer();
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearTimers();
      ACTIVITY_EVENTS.forEach((event) =>
        window.removeEventListener(event, resetTimer)
      );
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [resetTimer, onLogout, timeoutMinutes, clearTimers]);
}

export default useAutoLogout;
