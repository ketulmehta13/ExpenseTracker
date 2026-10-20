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
// Survives the tab being closed: phones often discard a backgrounded browser tab, and a reopened
// tab restores the session, so the idle clock must not start again from zero
const STORAGE_KEY = 'et-last-activity';

const readStored = () => {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    return value && typeof value.active === 'number' ? value : null;
  } catch {
    return null;
  }
};
const writeStored = (value) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); } catch {/* private mode: memory only */}
};

/**
 * useAutoLogout — Automatically logs the user out after a period of inactivity.
 * Activity in any open tab keeps every tab alive (shared via BroadcastChannel),
 * so an idle background tab never logs out a tab that is in use. When the app is hidden
 * (minimised, another app opened, the phone locked) for hiddenTimeoutMinutes, the user is
 * logged out when they come back, even if the browser closed and reopened the tab meanwhile.
 *
 * @param {Object} options
 * @param {number} options.timeoutMinutes - Idle timeout in minutes (default: 15)
 * @param {number} options.hiddenTimeoutMinutes - Timeout while the app is in the background (default: 5)
 * @param {string} [options.signedInAt] - When this session signed in (ISO); older stored activity is ignored
 * @param {Function} options.onLogout - Callback to execute on logout
 * @param {number} options.warnBeforeMs - Duration in ms to warn before logout (default: 60000 = 60s)
 * @param {Function} [options.onWarn] - Callback to execute to warn user
 */
export function useAutoLogout({
  timeoutMinutes = 15, hiddenTimeoutMinutes = 5, signedInAt, onLogout, warnBeforeMs = 60000, onWarn,
}) {
  // Keep the latest callbacks without re-subscribing every listener on each render
  const onLogoutRef = useRef(onLogout);
  const onWarnRef = useRef(onWarn);
  useEffect(() => {
    onLogoutRef.current = onLogout;
    onWarnRef.current = onWarn;
  });

  useEffect(() => {
    const timeoutMs = timeoutMinutes * 60 * 1000;
    const hiddenTimeoutMs = hiddenTimeoutMinutes * 60 * 1000;
    const signedInMs = signedInAt ? Date.parse(signedInAt) || 0 : 0;
    const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(ACTIVITY_CHANNEL) : null;
    let logoutTimer = null;
    let warnTimer = null;
    let lastActive = Date.now();
    let hiddenAt = null;
    let lastBroadcast = 0;
    let lastStored = 0;
    let loggedOut = false;

    const logout = () => {
      if (loggedOut) return;
      loggedOut = true;
      try { localStorage.removeItem(STORAGE_KEY); } catch {/* ignore */}
      onLogoutRef.current?.();
    };
    const store = (force = false) => {
      const now = Date.now();
      if (!force && now - lastStored < BROADCAST_THROTTLE_MS) return;
      lastStored = now;
      writeStored({ active: lastActive, hidden: hiddenAt });
    };
    const expired = (now = Date.now()) =>
      now - lastActive >= timeoutMs || (hiddenAt !== null && now - hiddenAt >= hiddenTimeoutMs);

    // A reopened tab: carry on from the activity stored by this session before it was closed
    const stored = readStored();
    if (stored && stored.active >= signedInMs) {
      lastActive = stored.active;
      hiddenAt = typeof stored.hidden === 'number' ? stored.hidden : null;
      if (expired()) {
        logout();
        return undefined;
      }
    }
    if (document.visibilityState === 'visible') {
      hiddenAt = null;
      lastActive = Date.now();
    }
    store(true);

    const scheduleTimers = () => {
      clearTimeout(logoutTimer);
      clearTimeout(warnTimer);
      const remaining = Math.max(0, lastActive + timeoutMs - Date.now());
      // Optional: warn the user shortly before auto-logout (e.g. show a toast notification)
      if (warnBeforeMs > 0 && remaining > warnBeforeMs) {
        warnTimer = setTimeout(() => onWarnRef.current?.(), remaining - warnBeforeMs);
      }
      logoutTimer = setTimeout(logout, remaining);
    };

    const handleActivity = () => {
      const now = Date.now();
      if (now - lastActive < RESET_THROTTLE_MS) return;
      lastActive = now;
      scheduleTimers();
      store();
      if (channel && now - lastBroadcast >= BROADCAST_THROTTLE_MS) {
        lastBroadcast = now;
        channel.postMessage(now);
      }
    };

    // Another tab saw activity
    const handleRemoteActivity = (event) => {
      if (typeof event.data === 'number' && event.data > lastActive) {
        lastActive = event.data;
        hiddenAt = null; // the user is using the app in another tab
        scheduleTimers();
      }
    };

    // Background tabs throttle timers (phones stop them), so check the deadlines when the tab comes back
    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') {
        hiddenAt = Date.now();
        store(true);
        return;
      }
      if (expired()) {
        logout();
        return;
      }
      hiddenAt = null;
      lastActive = Date.now();
      store(true);
      scheduleTimers();
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
  }, [timeoutMinutes, hiddenTimeoutMinutes, signedInAt, warnBeforeMs]);
}

export default useAutoLogout;
