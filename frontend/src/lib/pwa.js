/**
 * Rip N' Flip — Service Worker registration + install prompt helper.
 *
 * Exposes:
 *   - registerSW(): registers /sw.js, listens for updates
 *   - getInstallPrompt() → { available, prompt() } reactive helper
 *
 * Notes:
 *   - We register in BOTH dev and prod so the PWA is testable from the
 *     preview URL. Webpack-dev-server uses websockets for HMR which the SW
 *     does not intercept (only GET fetches).
 *   - SW skips /api/ — those always go to network.
 */

let deferredInstallPrompt = null;
const installListeners = new Set();

export function registerSW() {
  if (!('serviceWorker' in navigator)) return;

  // Only register on http(s) origins (skip blob/data/etc.)
  if (!/^https?:/.test(window.location.protocol)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/', updateViaCache: 'none' })
      .then((reg) => {
        // Check for updates every hour while open
        setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);

        if (reg.waiting) {
          notifyUpdate(reg);
        }
        reg.addEventListener('updatefound', () => {
          const installing = reg.installing;
          if (!installing) return;
          installing.addEventListener('statechange', () => {
            if (
              installing.state === 'installed' &&
              navigator.serviceWorker.controller
            ) {
              notifyUpdate(reg);
            }
          });
        });
      })
      .catch(() => {
        // ignore registration errors silently
      });

    // Reload once new SW takes control
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  });
}

function notifyUpdate(reg) {
  // Auto-apply update on next reload (silent). Could swap for a UI toast.
  if (reg.waiting) {
    reg.waiting.postMessage('SKIP_WAITING');
  }
}

// --- Install prompt (Add to Home Screen) ---
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  installListeners.forEach((cb) => cb({ available: true }));
});

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  installListeners.forEach((cb) => cb({ available: false, installed: true }));
});

export function onInstallAvailability(cb) {
  installListeners.add(cb);
  cb({ available: !!deferredInstallPrompt });
  return () => installListeners.delete(cb);
}

export async function promptInstall() {
  if (!deferredInstallPrompt) return { outcome: 'unavailable' };
  deferredInstallPrompt.prompt();
  const result = await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  installListeners.forEach((cb) => cb({ available: false }));
  return result;
}

export function isStandalone() {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
}
