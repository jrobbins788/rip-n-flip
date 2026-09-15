/**
 * DethroneBanner — global in-app "Heart Attack" banner.
 *
 * Polls /api/notifications every 60s for the logged-in user. When a
 * `dethrone` notification is present and unread, surfaces a red banner with
 * the kingbuilt copy and a CTA to view the new champion's binder.
 *
 * Mounted in App.js so it appears on every authenticated page.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { Crown, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const POLL_MS = 60_000;

export default function DethroneBanner() {
  const { user } = useAuth();
  const [dethrone, setDethrone] = useState(null);

  const fetchUnread = useCallback(async () => {
    if (!user) return;
    try {
      const r = await axios.get(`${API}/notifications`, {
        params: { only_unread: true, limit: 5 },
        withCredentials: true,
      });
      const notifs = r.data?.notifications || [];
      const latestDethrone = notifs.find((n) => n.type === 'dethrone');
      setDethrone(latestDethrone || null);
    } catch {
      // Silent — never break the app over a banner poll
    }
  }, [user]);

  useEffect(() => {
    if (!user) {
      setDethrone(null);
      return undefined;
    }
    fetchUnread();
    const id = setInterval(fetchUnread, POLL_MS);
    return () => clearInterval(id);
  }, [user, fetchUnread]);

  const dismiss = async () => {
    if (!dethrone) return;
    const id = dethrone.notification_id;
    setDethrone(null); // optimistic
    try {
      await axios.post(`${API}/notifications/${id}/read`, {}, { withCredentials: true });
    } catch {
      // ignore — will refetch on next poll
    }
  };

  return (
    <AnimatePresence>
      {dethrone && (
        <motion.div
          data-testid="dethrone-banner"
          initial={{ y: -80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -80, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 240, damping: 24 }}
          className="fixed top-0 left-0 right-0 z-[60] safe-top"
          style={{ pointerEvents: 'auto' }}
        >
          <div
            className="relative px-4 py-3 sm:py-3.5 border-b shadow-2xl"
            style={{
              background:
                'linear-gradient(90deg, rgba(255,57,57,0.95) 0%, rgba(255,0,153,0.95) 60%, rgba(255,107,0,0.95) 100%)',
              borderColor: 'rgba(255,255,255,0.15)',
            }}
          >
            <div className="max-w-7xl mx-auto flex items-center gap-3">
              <Crown className="w-6 h-6 sm:w-7 sm:h-7 text-white flex-shrink-0" strokeWidth={2.5} />
              <div className="flex-1 min-w-0">
                <div
                  className="font-mono text-[10px] sm:text-[11px] uppercase tracking-[0.32em] text-white/85 mb-0.5"
                  data-testid="dethrone-banner-tag"
                >
                  YOU LOST THE CROWN
                </div>
                <p
                  className="text-white font-heading text-sm sm:text-base leading-tight truncate sm:whitespace-normal"
                  data-testid="dethrone-banner-body"
                >
                  {dethrone.body || `You just lost the crown to @${dethrone.payload?.new_holder_username || 'rival'}. Beat them by Sunday or it's their Pro extension! 👑`}
                </p>
              </div>
              <Link
                to={dethrone.url || '/binders'}
                data-testid="dethrone-banner-cta"
                onClick={dismiss}
                className="hidden sm:inline-block bg-black text-white px-4 py-2 font-heading tracking-widest text-xs uppercase hover:opacity-80 no-min-tap"
              >
                STRIKE BACK →
              </Link>
              <button
                type="button"
                onClick={dismiss}
                data-testid="dethrone-banner-dismiss"
                aria-label="Dismiss"
                className="text-white/85 hover:text-white p-1 no-min-tap"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
