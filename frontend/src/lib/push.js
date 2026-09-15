/**
 * Web Push subscribe helper — opt-in flow for the Dethrone "Heart Attack" nudge.
 *
 * Usage:
 *   import { ensurePushSubscribed, isPushSupported } from '../lib/push';
 *   await ensurePushSubscribed();  // prompts permission + registers w/ backend
 */
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export function isPushSupported() {
  return (
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export async function getPushPermission() {
  if (!isPushSupported()) return 'unsupported';
  return Notification.permission; // 'default' | 'granted' | 'denied'
}

/**
 * Idempotent: checks current state, prompts user if needed, subscribes, and
 * posts the subscription to /api/push/subscribe. Returns true on success.
 */
export async function ensurePushSubscribed() {
  if (!isPushSupported()) return false;
  try {
    if (Notification.permission === 'denied') return false;
    if (Notification.permission === 'default') {
      const result = await Notification.requestPermission();
      if (result !== 'granted') return false;
    }
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      const keyRes = await axios.get(`${API}/push/vapid-public-key`);
      if (!keyRes.data?.enabled) return false;
      const applicationServerKey = urlBase64ToUint8Array(keyRes.data.vapid_public_key);
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });
    }
    const json = sub.toJSON();
    await axios.post(
      `${API}/push/subscribe`,
      {
        endpoint: json.endpoint,
        keys: json.keys,
        user_agent: navigator.userAgent,
      },
      { withCredentials: true }
    );
    return true;
  } catch (e) {
    // Don't surface a hard error — push is best-effort
    // eslint-disable-next-line no-console
    console.warn('[push] subscribe failed:', e);
    return false;
  }
}

export async function unsubscribePush() {
  if (!isPushSupported()) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (!sub) return true;
    const json = sub.toJSON();
    await axios.post(
      `${API}/push/unsubscribe`,
      { endpoint: json.endpoint },
      { withCredentials: true }
    );
    await sub.unsubscribe();
    return true;
  } catch (e) {
    return false;
  }
}
