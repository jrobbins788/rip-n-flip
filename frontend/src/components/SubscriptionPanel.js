import { useState, useEffect } from 'react';
import axios from 'axios';
import { useSearchParams, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { Crown, Check, Sparkles, Loader2, Lock, Calendar, ExternalLink } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Pro Subscription panel.
 * Mounts inside Profile/Vault page as a tab — also available standalone.
 */
export default function SubscriptionPanel() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/subscription/status`, { withCredentials: true });
      setStatus(r.data);
    } catch (e) {
      toast.error('Failed to load subscription status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (searchParams.get('subscription') === 'success') {
      toast.success('Welcome to Pro! Subscription processing...');
      setTimeout(() => { setSearchParams({}); load(); }, 2000);
    } else if (searchParams.get('subscription') === 'canceled') {
      toast.info('Subscription canceled');
      setSearchParams({});
    }
  }, []);

  const startCheckout = async () => {
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/subscription/checkout`,
        { origin_url: window.location.origin },
        { withCredentials: true }
      );
      if (r.data.url) {
        window.location.href = r.data.url;
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Checkout failed');
    } finally {
      setSubmitting(false);
    }
  };

  const cancelSub = async () => {
    if (!window.confirm('Cancel your subscription? You\'ll keep Pro access until the end of your billing period.')) return;
    try {
      await axios.post(`${API}/subscription/cancel`, {}, { withCredentials: true });
      toast.success('Subscription set to cancel at period end');
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Cancel failed');
    }
  };

  if (loading) return <div className="text-center py-10"><Loader2 className="w-6 h-6 animate-spin text-white/40 mx-auto" /></div>;

  const isProActive = status?.subscription_status === 'active';
  const isInTrial = status?.tier === 'pro' && !isProActive && status?.trial_days_left > 0;
  const isFreeNoTrial = status?.tier === 'free';

  return (
    <div data-testid="subscription-panel" className="space-y-5">
      {/* Current Status Card */}
      <div className="bg-[#0a0a0a] border-2 p-6 relative overflow-hidden"
           style={{ borderColor: isProActive ? '#FF0099' : isInTrial ? '#FACC15' : '#27272a' }}>
        <div className="absolute -top-20 -right-20 w-60 h-60 rounded-full blur-[100px] opacity-25"
             style={{ background: isProActive ? '#FF0099' : isInTrial ? '#FACC15' : '#27272a' }} />

        <div className="relative z-10">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <Crown className="w-5 h-5" style={{ color: isProActive ? '#FF0099' : isInTrial ? '#FACC15' : '#94A3B8' }} />
              <span className="font-heading text-2xl tracking-widest" style={{ color: isProActive ? '#FF0099' : isInTrial ? '#FACC15' : '#94A3B8' }}>
                {isProActive ? 'PRO · ACTIVE' : isInTrial ? `PRO · TRIAL · ${status.trial_days_left}d LEFT` : 'FREE TIER'}
              </span>
            </div>
            {status?.cancel_at_period_end && (
              <span className="text-[10px] font-mono px-2 py-1 bg-red-500/20 text-red-300 border border-red-500/30">CANCELING</span>
            )}
          </div>

          {isProActive && (
            <div className="space-y-1 text-sm text-white/70">
              <div className="flex items-center gap-2"><Calendar className="w-3.5 h-3.5" />Next billing: {status.current_period_end ? new Date(status.current_period_end).toLocaleDateString() : '—'}</div>
              <div className="text-white/50 text-xs font-mono">Subscription ID: {status.stripe_subscription_id?.slice(0, 20)}...</div>
            </div>
          )}
          {isInTrial && (
            <p className="text-white/70 text-sm">You're on the 10-day Pro trial. After {status.trial_days_left} days you'll drop to Free unless you upgrade.</p>
          )}
          {isFreeNoTrial && (
            <p className="text-white/70 text-sm">Trial expired. Upgrade to Pro to unlock unlimited binder slots, 5 predictor rips/day, and marketplace selling.</p>
          )}
        </div>
      </div>

      {/* Plan Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Free */}
        <div className="bg-[#0a0a0a] border border-[#27272a] p-6">
          <div className="text-[10px] font-mono text-white/40 tracking-widest mb-1">RIPPER</div>
          <div className="font-heading text-3xl font-black text-white mb-1">FREE</div>
          <div className="text-white/40 text-xs mb-4">always free</div>
          <ul className="space-y-2 text-sm text-white/70">
            <Bullet>Pack Analyzer (full)</Bullet>
            <Bullet>2 packs / 7 days in Display Case</Bullet>
            <Bullet>2 Predictor rips / 24h</Bullet>
            <Bullet>Browse Marketplace</Bullet>
            <Bullet muted>Cannot sell on Marketplace</Bullet>
          </ul>
        </div>

        {/* Pro */}
        <motion.div
          whileHover={{ y: -3 }}
          className="relative bg-gradient-to-br from-[#FF0099]/10 via-[#0a0a0a] to-[#00F0FF]/10 border-2 border-[#FF0099]/40 p-6"
          data-testid="pro-plan-card"
        >
          <div className="absolute top-3 right-3 text-[9px] font-mono px-2 py-0.5 bg-[#FF0099] text-white tracking-widest">RECOMMENDED</div>
          <div className="text-[10px] font-mono text-[#FF0099] tracking-widest mb-1">RIP N' FLIP PRO</div>
          <div className="flex items-baseline gap-1 mb-1">
            <span className="font-heading text-4xl font-black text-white">$3.99</span>
            <span className="text-white/60 text-sm">/month</span>
          </div>
          <div className="text-white/50 text-xs mb-4">10-day free trial · cancel anytime</div>
          <ul className="space-y-2 text-sm text-white/80 mb-5">
            <Bullet pro>Unlimited Display Case slots</Bullet>
            <Bullet pro>5 Predictor rips / 24h</Bullet>
            <Bullet pro>Sell on Marketplace</Bullet>
            <Bullet pro>List-from-binder one-tap</Bullet>
            <Bullet pro>Bold pro graphics + animations</Bullet>
            <Bullet pro>Priority access to new features</Bullet>
          </ul>
          {isProActive ? (
            <button
              onClick={cancelSub}
              data-testid="cancel-sub-btn"
              disabled={status.cancel_at_period_end}
              className="w-full bg-white/5 border border-white/20 text-white/80 font-heading tracking-widest h-11 hover:border-red-400/40 hover:text-red-400 disabled:opacity-30"
            >
              {status.cancel_at_period_end ? 'CANCELING AT PERIOD END' : 'CANCEL SUBSCRIPTION'}
            </button>
          ) : (
            <button
              onClick={startCheckout}
              disabled={submitting}
              data-testid="upgrade-pro-btn"
              className="w-full bg-[#FF0099] text-white font-heading tracking-widest h-12 hover:bg-[#FF0099]/90 disabled:opacity-30 flex items-center justify-center gap-2"
            >
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> REDIRECTING...</> : <><Sparkles className="w-4 h-4" /> START 10-DAY TRIAL</>}
            </button>
          )}
        </motion.div>
      </div>

      {/* Setup hint */}
      <div className="bg-yellow-500/5 border border-yellow-500/20 p-4 text-xs text-yellow-200/80">
        <Lock className="w-3.5 h-3.5 inline mr-1" />
        <strong>Setup note:</strong> Subscriptions need a real Stripe test API key in <code className="bg-black/40 px-1">backend/.env</code> as <code className="bg-black/40 px-1">STRIPE_API_KEY=sk_test_...</code>. Get yours at <a href="https://dashboard.stripe.com/test/apikeys" target="_blank" rel="noopener noreferrer" className="text-[#00F0FF] underline">dashboard.stripe.com/test/apikeys <ExternalLink className="w-3 h-3 inline" /></a>
      </div>
    </div>
  );
}

function Bullet({ children, pro, muted }) {
  return (
    <li className={`flex items-start gap-2 ${muted ? 'text-white/40 line-through' : ''}`}>
      <Check className={`w-4 h-4 mt-0.5 flex-shrink-0 ${pro ? 'text-[#FF0099]' : 'text-[#39FF14]'}`} />
      <span>{children}</span>
    </li>
  );
}
