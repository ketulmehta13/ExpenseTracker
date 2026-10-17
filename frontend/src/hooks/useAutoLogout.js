import { useEffect, useRef } from 'react';

const ACTIVITY_EVENTS = [
  'mousedown',
  'mousemove',
  'keydown',
  'scroll',
  'touchstart',
  'click',
];

// Activity events (mousemove especially) fire constantly; reset timers at most this often
const RESET_THROTTLE_MS = 1000;
// How often a tab tells the other open tabs that the user is active
const BROADCAST_THROTTLE_MS = 5000;
const ACTIVITY_CHANNEL = 'et-user-activity';

/**
 * useAutoLogout — Automatically logs the user out after a period of inactivity.
 * Activity in any open tab keeps every tab alive (shared via BroadcastChannel),
 * so an idle background tab never logs out a tab that is in use.
 *
 * @param {Object} options
 * @param {number} options.timeoutMinutes - Idle timeout in minutes (default: 15)
 * @param {Function} options.onLogout - Callback to execute on logout
 * @param {number} options.warnBeforeMs - Duration in ms to warn before logout (default: 60000 = 60s)
 * @param {Function} [options.onWarn] - Callback to execute to warn user
 */
export function useAutoLogout({ timeoutMinutes = 15, onLogout, warnBeforeMs = 60000, onWarn }) {
  // Keep the latest callbacks without re-subscribing every listener on each render
  const onLogoutRef = useRef(onLogout);
  const onWarnRef = useRef(onWarn);
  useEffect(() => {
    onLogoutRef.current = onLogout;
    onWarnRef.current = onWarn;
  });

  useEffect(() => {
    const timeoutMs = timeoutMinutes * 60 * 1000;
    const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(ACTIVITY_CHANNEL) : null;
    let logoutTimer = null;
    let warnTimer = null;
    let lastActive = Date.now();
    let lastBroadcast = 0;

    const scheduleTimers = () => {
      clearTimeout(logoutTimer);
      clearTimeout(warnTimer);
      const remaining = Math.max(0, lastActive + timeoutMs - Date.now());
      // Optional: warn the user shortly before auto-logout (e.g. show a toast notification)
      if (warnBeforeMs > 0 && remaining > warnBeforeMs) {
        warnTimer = setTimeout(() => onWarnRef.current?.(), remaining - warnBeforeMs);
      }
      logoutTimer = setTimeout(() => onLogoutRef.current?.(), remaining);
    };

    const handleActivity = () => {
      const now = Date.now();
      if (now - lastActive < RESET_THROTTLE_MS) return;
      lastActive = now;
      scheduleTimers();
      if (channel && now - lastBroadcast >= BROADCAST_THROTTLE_MS) {
        lastBroadcast = now;
        channel.postMessage(now);
      }
    };

    // Another tab saw activity
    const handleRemoteActivity = (event) => {
      if (typeof event.data === 'number' && event.data > lastActive) {
        lastActive = event.data;
        scheduleTimers();
      }
    };

    // Background tabs throttle timers, so re-check the deadline when the tab comes back
    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return;
      if (Date.now() - lastActive >= timeoutMs) {
        onLogoutRef.current?.();
      } else {
        scheduleTimers();
      }
    };

    scheduleTimers();
    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, handleActivity, { passive: true })
    );
    channel?.addEventListener('message', handleRemoteActivity);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearTimeout(logoutTimer);
      clearTimeout(warnTimer);
      ACTIVITY_EVENTS.forEach((event) =>
        window.removeEventListener(event, handleActivity)
      );
      channel?.close();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [timeoutMinutes, warnBeforeMs]);
}

export default useAutoLogout;
