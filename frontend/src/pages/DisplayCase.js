import { useState, useEffect } from 'react';
import axios from 'axios';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import Navbar from '../components/Navbar';
import { useAuth } from '../context/AuthContext';
import {
  Library, Plus, Trash2, X, Sparkles, Lock, ArrowLeft, Calendar,
  Loader2, Hash, Search, CheckCircle2, DollarSign, Bell, BellOff,
} from 'lucide-react';
import { ensurePushSubscribed, getPushPermission, isPushSupported } from '../lib/push';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const sportColors = {
  NBA: { bg: '#FF3939', glow: '#FF393955' },
  NFL: { bg: '#00A6FF', glow: '#00A6FF55' },
  MLB: { bg: '#FF0099', glow: '#FF009955' },
  NHL: { bg: '#94A3B8', glow: '#94A3B855' },
  Soccer: { bg: '#A855F7', glow: '#A855F755' },
};

export default function DisplayCase() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [packs, setPacks] = useState([]);
  const [stats, setStats] = useState(null);
  const [tier, setTier] = useState('free');
  const [loading, setLoading] = useState(true);
  const [openBinderId, setOpenBinderId] = useState(null);
  const [showAddPack, setShowAddPack] = useState(false);

  const loadAll = async () => {
    try {
      const [pRes, sRes] = await Promise.all([
        axios.get(`${API}/case/packs`, { withCredentials: true }),
        axios.get(`${API}/case/stats`, { withCredentials: true }),
      ]);
      setPacks(pRes.data.packs || []);
      setTier(pRes.data.tier || 'free');
      setStats(sRes.data);
      setLoading(false);
    } catch (e) {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) loadAll();
  }, [user]);

  const toggleVisibility = async (pack) => {
    const next = !pack.is_public;
    // optimistic update
    setPacks((prev) => prev.map((p) => p.case_pack_id === pack.case_pack_id ? { ...p, is_public: next } : p));
    try {
      await axios.patch(
        `${API}/case/packs/${pack.case_pack_id}/visibility`,
        { is_public: next },
        { withCredentials: true }
      );
      toast.success(next ? 'Binder is now public — listed in the gallery' : 'Binder set to private');
    } catch (e) {
      // rollback
      setPacks((prev) => prev.map((p) => p.case_pack_id === pack.case_pack_id ? { ...p, is_public: !next } : p));
      toast.error(e?.response?.data?.detail || 'Could not change visibility');
    }
  };

  if (authLoading) return <div className="min-h-screen bg-[#050505] flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/40" /></div>;
  if (!user) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="max-w-md mx-auto pt-32 px-4 text-center">
          <Lock className="w-12 h-12 text-white/30 mx-auto mb-3" />
          <h1 className="font-heading text-3xl text-white mb-2">DISPLAY CASE</h1>
          <p className="text-white/50 mb-4">Login to track your packs.</p>
          <Link to="/login"><button className="bg-[#FF0099] text-white px-6 py-2 font-heading tracking-widest">LOGIN</button></Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      <main className="pt-24 pb-16 px-4">
        <div className="max-w-7xl mx-auto">
          <Link to="/" className="inline-flex items-center gap-2 text-white/50 hover:text-white text-sm font-mono mb-4">
            <ArrowLeft className="w-4 h-4" /> HOME
          </Link>

          {/* Header */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between mb-8 gap-4">
            <div>
              <div className="inline-flex items-center gap-2 bg-[#39FF14]/10 border border-[#39FF14]/40 px-3 py-1 mb-3">
                <Library className="w-4 h-4 text-[#39FF14]" />
                <span className="text-[#39FF14] font-mono text-xs tracking-widest">DIGITAL BINDER · {tier === 'pro' ? 'PRO' : 'FREE'} TIER</span>
              </div>
              <h1 className="font-heading text-5xl sm:text-7xl font-black text-white uppercase tracking-tight">
                MY <span className="text-[#39FF14]">DISPLAY CASE</span>
              </h1>
              <p className="text-white/60 text-sm mt-2 max-w-xl">
                Every pack you've ripped lives here. Tap a binder to fan out your pulls.
              </p>
            </div>

            <div className="flex items-center gap-2 self-start lg:self-auto">
              <PushOptInButton />
              <button
                onClick={() => setShowAddPack(true)}
                data-testid="add-pack-btn"
                className="bg-[#FF0099] text-white font-heading tracking-widest px-6 py-3 hover:bg-[#FF0099]/90 flex items-center gap-2"
              >
                <Plus className="w-4 h-4" /> ADD A PACK
              </button>
            </div>
          </div>

          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8" data-testid="case-stats">
              <StatCard label="Total Packs" value={stats.total_packs} accent="#00F0FF" />
              <StatCard label="Total Pulls" value={stats.total_pulls} accent="#39FF14" />
              <StatCard label="This Week" value={`${stats.weekly_packs}${stats.weekly_limit ? `/${stats.weekly_limit}` : ''}`} accent="#FF0099" />
              <StatCard label="Sports Covered" value={Object.keys(stats.by_sport || {}).length} accent="#FACC15" />
            </div>
          )}

          {/* Tier banner */}
          {tier === 'free' && (
            <div className="mb-8 bg-gradient-to-r from-[#FF0099]/10 to-[#00F0FF]/10 border border-[#FF0099]/30 px-4 py-3 text-sm flex flex-col sm:flex-row items-center justify-between gap-2" data-testid="tier-banner">
              <span className="text-white/80">
                <Lock className="w-4 h-4 inline mr-1 text-[#FF0099]" />
                Free tier: <strong className="text-[#FF0099]">2 packs / 7 days.</strong> Pro = unlimited slots, 5 predictor rips/day, sell in marketplace.
              </span>
              <Link to="/register" data-testid="tier-upgrade-btn">
                <button className="bg-[#FF0099] text-white px-4 py-1.5 font-heading text-xs tracking-widest hover:bg-[#FF0099]/90">
                  GO PRO — $3.99/mo
                </button>
              </Link>
            </div>
          )}

          {/* Binders Grid */}
          {loading ? (
            <div className="text-center py-20"><Loader2 className="w-8 h-8 text-[#39FF14] animate-spin mx-auto" /></div>
          ) : packs.length === 0 ? (
            <EmptyCase onAdd={() => setShowAddPack(true)} />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5" data-testid="binder-grid">
              {packs.map((p) => (
                <Binder
                  key={p.case_pack_id}
                  pack={p}
                  onClick={() => setOpenBinderId(p.case_pack_id)}
                  onToggleVisibility={toggleVisibility}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Add Pack Modal */}
      <AnimatePresence>
        {showAddPack && (
          <AddPackModal
            onClose={() => setShowAddPack(false)}
            onAdded={() => { setShowAddPack(false); loadAll(); }}
          />
        )}
      </AnimatePresence>

      {/* Open Binder (Solitaire Spread) */}
      <AnimatePresence>
        {openBinderId && (
          <BinderView
            casePackId={openBinderId}
            onClose={() => { setOpenBinderId(null); loadAll(); }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function StatCard({ label, value, accent }) {
  return (
    <div className="bg-[#0a0a0a] border border-[#27272a] px-4 py-3" style={{ borderColor: `${accent}33` }}>
      <div className="text-[10px] text-white/40 font-mono uppercase tracking-widest">{label}</div>
      <div className="font-mono text-2xl font-bold mt-1" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function EmptyCase({ onAdd }) {
  return (
    <div className="bg-[#0a0a0a] border-2 border-dashed border-[#27272a] p-12 text-center" data-testid="empty-case">
      <Library className="w-16 h-16 text-white/20 mx-auto mb-3" />
      <h3 className="font-heading text-2xl text-white mb-2 tracking-wider">YOUR CASE IS EMPTY</h3>
      <p className="text-white/50 text-sm mb-6 max-w-sm mx-auto">
        Log your first pack to start your digital binder. Track every pull, every grail.
      </p>
      <button onClick={onAdd} className="bg-[#39FF14] text-black font-heading tracking-widest px-8 py-3 hover:bg-[#39FF14]/90">
        + LOG YOUR FIRST PACK
      </button>
    </div>
  );
}

/**
 * Binder card — 3D spine + cover treatment.
 * Click → opens solitaire spread modal.
 * Includes a public/private toggle so the binder can opt into the gallery.
 */
function Binder({ pack, onClick, onToggleVisibility }) {
  const sport = sportColors[pack.sport] || sportColors.NBA;
  const date = new Date(pack.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const isPublic = !!pack.is_public;

  return (
    <motion.button
      whileHover={{ y: -6, rotateY: 6, scale: 1.015, transition: { type: 'spring', stiffness: 320, damping: 22 } }}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      data-testid={`binder-${pack.case_pack_id}`}
      className="relative aspect-[3/4] cursor-pointer group focus:outline-none"
      style={{
        perspective: 1200,
        transformStyle: 'preserve-3d',
        willChange: 'transform',
        backfaceVisibility: 'hidden',
      }}
    >
      {/* 3D Spine */}
      <div
        className="absolute left-0 top-0 bottom-0 w-2.5"
        style={{
          background: `linear-gradient(to right, ${sport.bg}cc, ${sport.bg}77, transparent)`,
          transform: 'translateZ(2px)',
          boxShadow: `inset -2px 0 4px rgba(0,0,0,0.5)`,
        }}
      />
      {/* Card body */}
      <div
        className="relative h-full bg-[#0a0a0a] border border-[#27272a] overflow-hidden p-4 flex flex-col justify-between"
        style={{
          boxShadow: `0 12px 30px ${sport.glow}, inset 0 1px 0 rgba(255,255,255,0.04)`,
          background: `linear-gradient(135deg, ${sport.bg}11, #0a0a0a 70%)`,
        }}
      >
        <div className="absolute top-0 right-0 w-32 h-32 rounded-full blur-[40px] opacity-30" style={{ background: sport.bg }} />

        {/* Public/Private toggle (top-right corner) */}
        {onToggleVisibility && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onToggleVisibility(pack); }}
            data-testid={`visibility-toggle-${pack.case_pack_id}`}
            title={isPublic ? 'Public — listed in gallery' : 'Private — only you can see this'}
            className={`absolute top-2 right-2 z-20 text-[9px] font-mono px-1.5 py-0.5 border tracking-widest uppercase transition ${
              isPublic
                ? 'border-[#39FF14] text-[#39FF14] bg-[#39FF14]/10'
                : 'border-white/15 text-white/40 bg-black/40 hover:border-white/40 hover:text-white/70'
            }`}
          >
            {isPublic ? '● PUBLIC' : '○ PRIVATE'}
          </button>
        )}

        <div className="relative z-10">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono px-1.5 py-0.5 border tracking-widest" style={{ color: sport.bg, borderColor: `${sport.bg}66` }}>
              {pack.sport}
            </span>
            <span className="text-[9px] font-mono text-white/40 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> {date}
            </span>
          </div>
          <h3 className="font-heading text-white leading-tight tracking-tight text-sm sm:text-base">{pack.name}</h3>
        </div>

        <div className="relative z-10">
          <div className="text-[9px] text-white/40 font-mono uppercase mb-1">Pulls Logged</div>
          <div className="font-mono text-3xl font-bold" style={{ color: sport.bg }}>{pack.pulls_count}</div>
          <div className="text-[10px] font-mono text-white/40 mt-1 group-hover:text-[#39FF14] transition-colors">
            TAP TO FAN OUT →
          </div>
        </div>
      </div>
    </motion.button>
  );
}

/**
 * Modal: solitaire spread of all pulls in a binder.
 */
function BinderView({ casePackId, onClose }) {
  const [data, setData] = useState(null);
  const [showLogPull, setShowLogPull] = useState(false);
  const [sellPull, setSellPull] = useState(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/case/packs/${casePackId}/pulls`, { withCredentials: true });
      setData(r.data);
    } catch {}
  };
  useEffect(() => { load(); }, [casePackId]);

  const deletePull = async (pullId) => {
    if (!window.confirm('Remove this pull from your binder?')) return;
    await axios.delete(`${API}/case/pulls/${pullId}`, { withCredentials: true });
    toast.success('Pull removed');
    load();
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] bg-black/95 backdrop-blur-sm overflow-y-auto"
      data-testid="binder-view"
    >
      <div className="max-w-7xl mx-auto p-4 sm:p-8 min-h-screen">
        <button
          onClick={onClose}
          data-testid="binder-close"
          className="text-white/60 hover:text-white flex items-center gap-1 font-mono text-sm mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> CLOSE BINDER
        </button>

        {data ? (
          <>
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
              <div>
                <div className="text-[10px] font-mono text-white/40 tracking-widest uppercase">
                  {data.pack.sport} · LOGGED {new Date(data.pack.created_at).toLocaleDateString()}
                </div>
                <h2 className="font-heading text-3xl sm:text-5xl font-black text-white tracking-tight">{data.pack.name}</h2>
                <div className="text-white/50 text-sm mt-1">{data.pulls.length} pulls in this binder</div>
              </div>
              <button
                onClick={() => setShowLogPull(true)}
                data-testid="log-pull-btn"
                className="bg-[#39FF14] text-black font-heading tracking-widest px-5 py-2.5 hover:bg-[#39FF14]/90 flex items-center gap-2 self-start sm:self-auto"
              >
                <Plus className="w-4 h-4" /> LOG A PULL
              </button>
            </div>

            {/* Solitaire spread */}
            {data.pulls.length === 0 ? (
              <div className="bg-[#0a0a0a] border-2 border-dashed border-[#27272a] p-12 text-center">
                <Sparkles className="w-12 h-12 text-white/20 mx-auto mb-3" />
                <p className="text-white/50">No pulls logged yet. Tap "LOG A PULL" to start.</p>
              </div>
            ) : (
              <SolitaireSpread pulls={data.pulls} onDelete={deletePull} onSell={setSellPull} />
            )}
          </>
        ) : (
          <div className="text-center py-20"><Loader2 className="w-8 h-8 text-[#39FF14] animate-spin mx-auto" /></div>
        )}
      </div>

      <AnimatePresence>
        {showLogPull && data && (
          <LogPullModal
            pack={data.pack}
            onClose={() => setShowLogPull(false)}
            onLogged={() => { setShowLogPull(false); load(); }}
          />
        )}
        {sellPull && (
          <SellPullModal
            pull={sellPull}
            onClose={() => setSellPull(null)}
            onListed={() => { setSellPull(null); load(); }}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function SellPullModal({ pull, onClose, onListed }) {
  const navigate = useNavigate();
  const [price, setPrice] = useState('');
  const [description, setDescription] = useState(pull.notes || '');
  const [condition, setCondition] = useState('Near Mint');
  const [submitting, setSubmitting] = useState(false);
  const [proRequired, setProRequired] = useState(false);

  const card = pull.card || {};
  const titlePreview = [
    card.year,
    card.set,
    pull.parallel,
    card.player,
    card.card_number ? `#${card.card_number}` : null,
  ].filter(Boolean).join(' ');

  const submit = async () => {
    const p = parseFloat(price);
    if (!p || p <= 0) { toast.error('Enter a valid price'); return; }
    setSubmitting(true);
    try {
      await axios.post(
        `${API}/listings/from-pull`,
        { pull_id: pull.pull_id, price: p, description: description || undefined, condition },
        { withCredentials: true }
      );
      toast.success('Listed on the marketplace!');
      onListed();
      navigate('/marketplace');
    } catch (err) {
      const status = err?.response?.status;
      if (status === 402) {
        setProRequired(true);
      } else {
        toast.error(err?.response?.data?.detail || 'Listing failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] bg-black/85 flex items-center justify-center p-4 backdrop-blur-sm"
      data-testid="sell-pull-modal"
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        className="bg-[#0a0a0a] border border-[#39FF14]/40 w-full max-w-md p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-heading text-2xl text-white tracking-widest flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-[#39FF14]" /> SELL THIS PULL
          </h3>
          <button onClick={onClose} className="text-white/60 hover:text-white"><X className="w-5 h-5" /></button>
        </div>

        {proRequired ? (
          <div className="bg-[#FF0099]/10 border border-[#FF0099]/40 p-5 text-center">
            <Lock className="w-10 h-10 text-[#FF0099] mx-auto mb-2" />
            <h4 className="font-heading text-xl text-white mb-1">PRO FEATURE</h4>
            <p className="text-white/60 text-sm mb-4">
              Selling on the marketplace is a Pro perk. New users get a 10-day free trial. After that, $3.99/mo.
            </p>
            <Link to="/vault">
              <button className="bg-[#FF0099] text-white font-heading tracking-widest px-6 py-2.5 hover:bg-[#FF0099]/90">
                MANAGE SUBSCRIPTION
              </button>
            </Link>
          </div>
        ) : (
          <>
            <div className="bg-[#121212] border border-white/10 p-3 mb-4 text-sm">
              <div className="text-[10px] font-mono text-white/40 uppercase mb-1">PREVIEW LISTING</div>
              <div className="text-white truncate">{titlePreview || 'Untitled card'}</div>
              <div className="text-[10px] text-white/40 mt-1">2% platform fee will apply on sale</div>
            </div>

            <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">PRICE (USD)</label>
            <div className="flex items-center bg-[#121212] border border-white/10 focus-within:border-[#39FF14] mb-3">
              <span className="px-3 text-white/40 font-mono">$</span>
              <input
                type="number"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="49.99"
                data-testid="sell-pull-price"
                className="flex-1 bg-transparent py-2 pr-3 text-white outline-none"
              />
            </div>

            <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">CONDITION</label>
            <select
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              data-testid="sell-pull-condition"
              className="w-full bg-[#121212] border border-white/10 text-white text-sm px-3 py-2 outline-none mb-3"
            >
              {['Mint', 'Near Mint', 'Excellent', 'Very Good', 'Good', 'Played'].map((c) => <option key={c} value={c}>{c}</option>)}
            </select>

            <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">DESCRIPTION (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="centering 9/10, corners pristine..."
              data-testid="sell-pull-desc"
              className="w-full bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none mb-4 resize-none"
            />

            <button
              onClick={submit}
              disabled={!price || submitting}
              data-testid="sell-pull-submit"
              className="w-full bg-[#39FF14] text-black font-heading tracking-widest h-12 hover:bg-[#39FF14]/90 disabled:opacity-30 flex items-center justify-center gap-2"
            >
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> LISTING...</> : 'LIST ON MARKETPLACE'}
            </button>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}

/**
/**
 * Solitaire spread — cards "deal" from a center stack to a fanned table layout.
 *
 * Animation strategy (60fps target):
 *  • GPU-only transforms (translate3d via x/y, rotate, scale) — no layout properties animated.
 *  • Deterministic stagger ~35ms — cards arrive in dealing rhythm.
 *  • Spring tuned snappy (stiffness 260, damping 26) so motion settles fast.
 *  • Each card stacks at center initially then drifts to its fan position.
 *  • `will-change: transform` + `backfaceVisibility: hidden` keep compositor happy.
 *  • Honors `prefers-reduced-motion` — falls back to a simple fade.
 *  • Hover uses CSS-only de-rotation + lift to avoid extra React renders.
 */
function SolitaireSpread({ pulls, onDelete, onSell }) {
  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  return (
    <div className="relative" style={{ perspective: 1500 }}>
      <div className="flex flex-wrap gap-x-1 gap-y-12 sm:gap-y-16">
        {pulls.map((pull, i) => {
          // Deterministic per-card tilt + small drift so the fan feels organic
          const rotation = ((i % 7) - 3) * 1.8;
          const overlap = i === 0 ? 0 : -58;
          const dealDelay = reduceMotion ? 0 : Math.min(0.035 * i, 0.7);

          const initial = reduceMotion
            ? { opacity: 0 }
            : { opacity: 0, y: -120, x: -overlap * 0.4, rotate: rotation - 18, scale: 0.92 };
          const animate = reduceMotion
            ? { opacity: 1 }
            : { opacity: 1, y: 0, x: 0, rotate: rotation, scale: 1 };

          return (
            <motion.div
              key={pull.pull_id}
              initial={initial}
              animate={animate}
              transition={
                reduceMotion
                  ? { duration: 0.18 }
                  : { delay: dealDelay, type: 'spring', stiffness: 260, damping: 26, mass: 0.7 }
              }
              whileHover={
                reduceMotion
                  ? undefined
                  : {
                      y: -18,
                      rotate: 0,
                      scale: 1.06,
                      transition: { type: 'spring', stiffness: 360, damping: 24 },
                    }
              }
              style={{
                marginLeft: overlap,
                transformOrigin: 'center bottom',
                willChange: 'transform',
                backfaceVisibility: 'hidden',
                WebkitBackfaceVisibility: 'hidden',
              }}
              className="relative"
              data-testid={`pull-${pull.pull_id}`}
            >
              <PullCard pull={pull} onDelete={() => onDelete(pull.pull_id)} onSell={() => onSell(pull)} />
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function PullCard({ pull, onDelete, onSell }) {
  const card = pull.card || {};
  const isChase = pull.parallel || /Refractor|Auto|Numbered|Gold|Silver|\/\d+/i.test(`${pull.parallel || ''} ${card.player || ''} ${pull.notes || ''}`);
  const accent = isChase ? '#FF0099' : pull.source === 'local_db' ? '#39FF14' : pull.source === 'ebay_browse_api' ? '#00F0FF' : '#94A3B8';
  const isListed = pull.status === 'listed';

  return (
    <div
      className="relative w-32 h-48 sm:w-40 sm:h-56 bg-[#0a0a0a] border-2 overflow-hidden group"
      style={{
        borderColor: isListed ? '#FACC15' : accent,
        boxShadow: `0 8px 20px ${accent}55, inset 0 1px 0 rgba(255,255,255,0.05)`,
      }}
    >
      {card.image_url && (
        <img
          src={card.image_url}
          alt={card.player}
          className="absolute inset-0 w-full h-full object-cover opacity-80"
          onError={(e) => { e.target.style.display = 'none'; }}
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/40 to-transparent" />

      {/* Top stripe */}
      <div className="absolute top-0 left-0 right-0 px-2 py-1 text-[8px] font-mono tracking-widest uppercase flex items-center justify-between" style={{ background: `${accent}33` }}>
        <span style={{ color: accent }}>#{card.card_number || pull.card_number || '?'}</span>
        <span className="text-white/60">{card.year || ''}</span>
      </div>

      {/* Body */}
      <div className="absolute inset-x-2 bottom-2 z-10">
        {pull.parallel && (
          <div className="text-[8px] font-mono uppercase tracking-widest mb-0.5" style={{ color: accent }}>
            {pull.parallel}
          </div>
        )}
        <div className="font-heading text-white text-xs sm:text-sm leading-tight mb-1 truncate">{card.player}</div>
        <div className="text-[9px] text-white/60 truncate">{card.set}</div>
        <div className="text-[8px] font-mono text-white/40 mt-1">
          {new Date(pull.timestamp).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })}
        </div>
      </div>

      {/* Source pill */}
      <div className="absolute top-7 right-1.5 text-[7px] font-mono uppercase px-1 py-0.5" style={{ background: `${accent}44`, color: accent }}>
        {pull.source === 'local_db' ? 'DB' : pull.source === 'ebay_browse_api' ? 'eBay' : 'manual'}
      </div>

      {isListed && (
        <div className="absolute bottom-7 left-1.5 right-1.5 bg-yellow-400/90 text-black text-[7px] font-mono font-bold uppercase tracking-widest text-center py-0.5">
          ★ LISTED
        </div>
      )}

      {/* Hover actions */}
      <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!isListed && (
          <button
            onClick={(e) => { e.stopPropagation(); onSell(); }}
            className="w-6 h-6 bg-[#39FF14] text-black hover:bg-[#39FF14]/80 flex items-center justify-center"
            title="Sell on marketplace"
            data-testid="sell-pull-btn"
          >
            <DollarSign className="w-3 h-3" />
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="w-6 h-6 bg-black/60 text-red-400 hover:bg-red-500/30 flex items-center justify-center"
          title="Delete pull"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

/**
 * Modal to add a new pack (binder) to the case.
 */
function AddPackModal({ onClose, onAdded }) {
  const [packTypes, setPackTypes] = useState([]);
  const [picked, setPicked] = useState(null);
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    axios.get(`${API}/analyzer/packs`).then((r) => setPackTypes(r.data.packs || []));
  }, []);

  const submit = async () => {
    if (!picked) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/case/packs`, { pack_type_id: picked, name: name || undefined }, { withCredentials: true });
      toast.success('Pack added to your case!');
      onAdded();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to add');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[90] bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        className="bg-[#0a0a0a] border border-[#27272a] w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto"
        data-testid="add-pack-modal"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-heading text-2xl text-white tracking-widest">ADD A PACK</h3>
          <button onClick={onClose} className="text-white/60 hover:text-white"><X className="w-5 h-5" /></button>
        </div>

        <p className="text-white/50 text-sm mb-4">Pick the pack type you ripped:</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
          {packTypes.map((p) => (
            <button
              key={p.pack_id}
              onClick={() => setPicked(p.pack_id)}
              data-testid={`add-pack-pick-${p.pack_id}`}
              className={`text-left bg-[#121212] border p-3 transition-all ${
                picked === p.pack_id ? 'border-[#39FF14]' : 'border-[#27272a] hover:border-white/40'
              }`}
            >
              <div className="text-[9px] font-mono text-white/40 mb-1">{p.sport}</div>
              <div className="font-heading text-xs text-white tracking-tight">{p.name}</div>
              {picked === p.pack_id && (
                <div className="mt-2 text-[#39FF14]"><CheckCircle2 className="w-4 h-4" /></div>
              )}
            </button>
          ))}
        </div>

        <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">CUSTOM NAME (OPTIONAL)</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Walmart blaster I bought 5/3"
          data-testid="add-pack-name-input"
          className="w-full bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none mb-4"
        />

        <button
          onClick={submit}
          disabled={!picked || submitting}
          data-testid="add-pack-submit"
          className="w-full bg-[#39FF14] text-black font-heading tracking-widest h-12 hover:bg-[#39FF14]/90 disabled:opacity-30 flex items-center justify-center gap-2"
        >
          {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> ADDING...</> : 'ADD TO CASE'}
        </button>
      </motion.div>
    </motion.div>
  );
}

/**
 * Modal to log a pull into a binder.
 * Implements the user's logNewPull logic: type a card # → auto-search local DB → eBay fallback → manual entry.
 */
function LogPullModal({ pack, onClose, onLogged }) {
  const [cardNumber, setCardNumber] = useState('');
  const [parallel, setParallel] = useState('');
  const [year, setYear] = useState(2024);
  const [searchPreview, setSearchPreview] = useState(null);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [manualPlayer, setManualPlayer] = useState('');
  const [showManual, setShowManual] = useState(false);
  const [notes, setNotes] = useState('');

  const previewCard = async () => {
    if (!cardNumber) return;
    setSearching(true);
    setSearchPreview(null);
    try {
      const r = await axios.get(`${API}/cards/search`, {
        params: {
          card_number: cardNumber,
          set_name: pack.set_search || pack.set,
          year,
        },
      });
      if (r.data.results.length > 0) {
        setSearchPreview({ source: r.data.source, card: r.data.results[0] });
      } else {
        setSearchPreview({ source: 'none', card: null });
      }
    } catch {
      setSearchPreview({ source: 'error', card: null });
    } finally {
      setSearching(false);
    }
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      await axios.post(
        `${API}/case/packs/${pack.case_pack_id}/pulls`,
        {
          card_number: cardNumber || undefined,
          set_name: pack.set_search || pack.set,
          year,
          parallel: parallel || undefined,
          player: manualPlayer || undefined,
          notes: notes || undefined,
        },
        { withCredentials: true }
      );
      toast.success('Pull logged to binder!');
      onLogged();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to log');
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = cardNumber || manualPlayer;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] bg-black/85 flex items-center justify-center p-4 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        className="bg-[#0a0a0a] border border-[#39FF14]/30 w-full max-w-md p-6"
        data-testid="log-pull-modal"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-heading text-2xl text-white tracking-widest">LOG A PULL</h3>
          <button onClick={onClose} className="text-white/60 hover:text-white"><X className="w-5 h-5" /></button>
        </div>

        <p className="text-white/50 text-xs mb-4">
          Pack: <span className="text-[#39FF14]">{pack.name}</span>
        </p>

        <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest flex items-center gap-1">
          <Hash className="w-3 h-3" /> CARD NUMBER
        </label>
        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={cardNumber}
            onChange={(e) => { setCardNumber(e.target.value); setSearchPreview(null); }}
            placeholder="245"
            data-testid="pull-card-number"
            className="flex-1 bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none"
          />
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value) || 2024)}
            placeholder="Year"
            data-testid="pull-year"
            className="w-24 bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none"
          />
          <button
            onClick={previewCard}
            disabled={!cardNumber || searching}
            data-testid="pull-search-btn"
            className="bg-[#00F0FF] text-black px-3 disabled:opacity-30 flex items-center justify-center"
          >
            {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          </button>
        </div>

        {searchPreview && (
          <div className="mb-3 bg-[#121212] border border-white/10 p-3 text-sm" data-testid="pull-search-preview">
            {searchPreview.card ? (
              <>
                <div className="text-[9px] font-mono uppercase mb-1 text-[#39FF14]">
                  ✓ Match found · {searchPreview.source}
                </div>
                <div className="font-heading text-white">{searchPreview.card.player || searchPreview.card.title}</div>
                <div className="text-white/50 text-xs">
                  {searchPreview.card.set} · #{searchPreview.card.card_number || cardNumber}
                </div>
              </>
            ) : (
              <>
                <div className="text-yellow-300 text-xs mb-1">No match in DB or eBay.</div>
                <button
                  onClick={() => setShowManual(true)}
                  data-testid="enable-manual-entry"
                  className="text-[#FF0099] text-xs underline"
                >
                  Add manually →
                </button>
              </>
            )}
          </div>
        )}

        <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">PARALLEL (optional)</label>
        <input
          type="text"
          value={parallel}
          onChange={(e) => setParallel(e.target.value)}
          placeholder="Silver, Gold /10, Refractor..."
          data-testid="pull-parallel"
          className="w-full bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none mb-3"
        />

        {(showManual || !cardNumber) && (
          <>
            <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">PLAYER NAME (manual fallback)</label>
            <input
              type="text"
              value={manualPlayer}
              onChange={(e) => setManualPlayer(e.target.value)}
              placeholder="Wembanyama"
              data-testid="pull-manual-player"
              className="w-full bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none mb-3"
            />
          </>
        )}

        <label className="block text-xs font-mono text-white/50 mb-1 tracking-widest">NOTES (optional)</label>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="centering 9/10, corners pristine..."
          data-testid="pull-notes"
          className="w-full bg-[#121212] border border-white/10 focus:border-[#39FF14] text-white text-sm px-3 py-2 outline-none mb-4"
        />

        <button
          onClick={submit}
          disabled={!canSubmit || submitting}
          data-testid="pull-submit-btn"
          className="w-full bg-[#39FF14] text-black font-heading tracking-widest h-12 hover:bg-[#39FF14]/90 disabled:opacity-30 flex items-center justify-center gap-2"
        >
          {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> LOGGING...</> : 'LOG TO BINDER'}
        </button>
      </motion.div>
    </motion.div>
  );
}


/**
 * PushOptInButton — small inline button that prompts for notification
 * permission + registers a PushSubscription with the backend. Drives the
 * Dethrone "Heart Attack" nudge opt-in.
 */
function PushOptInButton() {
  const [permission, setPermission] = useState('default');
  const [busy, setBusy] = useState(false);
  const supported = isPushSupported();

  useEffect(() => {
    let cancel = false;
    (async () => {
      const p = await getPushPermission();
      if (!cancel) setPermission(p);
    })();
    return () => { cancel = true; };
  }, []);

  if (!supported) return null;

  if (permission === 'granted') {
    return (
      <div
        data-testid="push-status-granted"
        title="Notifications enabled — you'll get alerts the moment your crown is taken"
        className="flex items-center gap-2 px-3 py-3 border border-[#39FF14]/40 bg-[#39FF14]/10 text-[#39FF14] font-mono text-xs tracking-widest"
      >
        <Bell className="w-4 h-4" /> ALERTS ON
      </div>
    );
  }

  return (
    <button
      type="button"
      data-testid="push-opt-in-btn"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        const ok = await ensurePushSubscribed();
        setBusy(false);
        const p = await getPushPermission();
        setPermission(p);
        if (ok) toast.success("You'll get an alert the second someone takes your crown 👑");
        else if (p === 'denied') toast.error('Notifications blocked. Enable in browser settings.');
      }}
      className="flex items-center gap-2 px-4 py-3 border border-[#00F0FF]/40 hover:border-[#00F0FF] bg-[#00F0FF]/10 text-[#00F0FF] font-heading tracking-widest text-xs uppercase transition disabled:opacity-50"
    >
      {permission === 'denied' ? <BellOff className="w-4 h-4" /> : <Bell className="w-4 h-4" />}
      {busy ? 'ENABLING…' : permission === 'denied' ? 'ALERTS BLOCKED' : 'ENABLE ALERTS'}
    </button>
  );
}
