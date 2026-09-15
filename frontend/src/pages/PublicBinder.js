import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import Navbar from '../components/Navbar';
import { useAuth } from '../context/AuthContext';
import { ThumbsUp, ThumbsDown, Layers, ArrowLeft, Calendar, Loader2, Lock, Crown, Flame } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Public binder view — solitaire-style spread of a user's pulls.
 * Privacy: pulls arrive from the backend with `source_pack: "—"` (pack
 * mapping stripped). We never display which pack a card came from here.
 */
export default function PublicBinder() {
  const { userId } = useParams();
  const { user: me } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [myVotes, setMyVotes] = useState({}); // {pull_id: 'up'|'down'}
  const [battleCta, setBattleCta] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/binders/public/${userId}`);
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  // Fetch "Battle a Champion" data — drives the top-of-binder CTA when
  // viewing one of this week's top 3 thumbs-up earners.
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/binders/public/${userId}/battle-cta`);
        if (!cancel) setBattleCta(r.data);
      } catch {
        if (!cancel) setBattleCta(null);
      }
    })();
    return () => { cancel = true; };
  }, [userId]);

  const vote = async (pullId, direction) => {
    if (!me) {
      toast.error('Login to vote on pulls');
      return;
    }
    try {
      const r = await axios.post(
        `${API}/case/pulls/${pullId}/thumbs`,
        { vote: direction },
        { withCredentials: true }
      );
      setMyVotes((prev) => ({ ...prev, [pullId]: r.data.your_vote }));
      // Update the count locally — only thumbs_up is publicly tracked
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          pulls: prev.pulls.map((p) => (p.pull_id === pullId ? { ...p, thumbs_up_count: r.data.thumbs_up_count } : p)),
        };
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Vote failed');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="pt-32 flex items-center justify-center gap-2 text-white/50">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading binder...
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="pt-32 text-center text-white/60">
          <p>Binder not found or owner has no public pulls.</p>
          <Link to="/binders" className="text-[#00F0FF] mt-3 inline-block hover:underline">← Back to gallery</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      <div className="pt-20 px-4 max-w-7xl mx-auto pb-20">
        {/* Header */}
        <Link to="/binders" className="inline-flex items-center gap-1 text-white/40 hover:text-white text-sm mb-5 font-mono uppercase tracking-widest" data-testid="binder-back">
          <ArrowLeft className="w-4 h-4" /> GALLERY
        </Link>

        {battleCta?.is_champion && (
          <BattleChampionBanner cta={battleCta} username={data.user.username} />
        )}

        <header className="bg-[#0a0a0a] border border-[#27272a] p-6 mb-6 relative overflow-hidden">
          <div className="absolute -top-20 -right-20 w-60 h-60 bg-[#00F0FF] rounded-full blur-[120px] opacity-15" />
          <div className="relative flex items-start gap-4 flex-wrap">
            <div className="w-16 h-16 rounded-full bg-[#00F0FF]/10 border border-[#00F0FF]/40 flex items-center justify-center overflow-hidden flex-shrink-0">
              {data.user.picture ? (
                <img src={data.user.picture} alt={data.user.username} className="w-full h-full object-cover" />
              ) : (
                <span className="font-heading text-[#00F0FF] text-2xl">{(data.user.username || '?').slice(0,1).toUpperCase()}</span>
              )}
            </div>
            <div className="flex-1 min-w-[200px]">
              <h1 className="font-heading text-3xl sm:text-4xl text-white font-black uppercase tracking-tight" data-testid="public-binder-username">
                {data.user.username}
              </h1>
              <div className="flex gap-4 mt-2 flex-wrap text-xs font-mono uppercase tracking-widest text-white/50">
                <span><Layers className="w-3 h-3 inline mr-1" /> {data.stats.public_binders} binders</span>
                <span>·</span>
                <span>{data.stats.pulls_total} pulls visible</span>
                {data.stats.sports.length > 0 && (
                  <>
                    <span>·</span>
                    <span>{data.stats.sports.join(' · ')}</span>
                  </>
                )}
              </div>
              <div className="inline-flex items-center gap-1 text-[10px] font-mono text-[#FF0099] uppercase tracking-widest mt-3 px-2 py-1 bg-[#FF0099]/10 border border-[#FF0099]/30">
                <Lock className="w-3 h-3" /> SOURCE PACKS HIDDEN — only the owner sees the card↔pack mapping
              </div>
            </div>
          </div>
        </header>

        {/* Solitaire-style pulls spread */}
        {data.pulls.length === 0 ? (
          <div className="text-center py-16 text-white/50 text-sm">No public pulls yet.</div>
        ) : (
          <SolitaireSpread pulls={data.pulls} onSelect={setSelected} myVotes={myVotes} onVote={vote} />
        )}

        {/* Card detail modal */}
        <AnimatePresence>
          {selected && (
            <CardDetailModal
              pull={selected}
              myVote={myVotes[selected.pull_id]}
              onVote={vote}
              onClose={() => setSelected(null)}
            />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/**
 * Solitaire spread — cards fan out with overlap & subtle rotation.
 * GPU-only properties (transform, opacity) keep this butter smooth.
 */
function SolitaireSpread({ pulls, onSelect, myVotes, onVote }) {
  return (
    <div className="relative" data-testid="solitaire-spread">
      <div
        className="grid gap-3"
        style={{
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
        }}
      >
        {pulls.map((p, i) => (
          <PullCard
            key={p.pull_id}
            pull={p}
            index={i}
            onSelect={() => onSelect(p)}
            myVote={myVotes[p.pull_id]}
            onVote={onVote}
          />
        ))}
      </div>
    </div>
  );
}

function PullCard({ pull, index, onSelect, myVote, onVote }) {
  // Tilt cards subtly using deterministic offsets — looks "dealt"
  const tilt = ((pull.pull_id?.charCodeAt(5) || 0) % 7) - 3; // -3..+3 deg
  return (
    <motion.div
      data-testid={`pull-card-${pull.pull_id}`}
      initial={{ opacity: 0, y: 24, rotate: tilt - 8 }}
      animate={{ opacity: 1, y: 0, rotate: tilt }}
      transition={{
        delay: Math.min(0.04 * index, 0.6),
        type: 'spring',
        stiffness: 220,
        damping: 22,
      }}
      whileHover={{
        rotate: 0,
        y: -8,
        scale: 1.03,
        transition: { type: 'spring', stiffness: 320, damping: 20 },
      }}
      style={{
        willChange: 'transform',
        backfaceVisibility: 'hidden',
        transformStyle: 'preserve-3d',
      }}
      className="bg-[#0a0a0a] border border-white/10 hover:border-[#00F0FF]/50 aspect-[3/4] p-3 flex flex-col cursor-pointer relative overflow-hidden card-shine"
      onClick={onSelect}
    >
      {/* Rarity tag */}
      {pull.rarity_tier && pull.rarity_tier !== 'common' && (
        <span
          className="absolute top-2 left-2 text-[8px] font-mono px-1.5 py-0.5 tracking-widest uppercase border"
          style={{
            color: rarityColor(pull.rarity_tier),
            borderColor: `${rarityColor(pull.rarity_tier)}66`,
            background: `${rarityColor(pull.rarity_tier)}11`,
          }}
        >
          {pull.rarity_tier.replace('_', ' ')}
        </span>
      )}

      {/* Card body */}
      <div className="flex-1 flex items-center justify-center text-center">
        {pull.card?.image_url ? (
          <img
            src={pull.card.image_url}
            alt={pull.card?.player || 'pull'}
            className="max-h-full max-w-full object-contain"
            loading="lazy"
            style={{ filter: 'drop-shadow(0 10px 20px rgba(0,0,0,0.6))' }}
          />
        ) : (
          <div className="text-white/70">
            <div className="font-heading text-base leading-tight">{pull.card?.player || 'Unknown'}</div>
            {pull.card_number && (
              <div className="font-mono text-[10px] text-white/40 mt-1">#{pull.card_number}</div>
            )}
            {pull.parallel && (
              <div className="text-[10px] text-[#FF0099] mt-1 italic">{pull.parallel}</div>
            )}
          </div>
        )}
      </div>

      {/* Footer with thumbs */}
      <div className="flex items-center justify-between pt-2 border-t border-white/5 mt-2">
        <div className="text-[9px] font-mono text-white/30 uppercase tracking-widest">SOURCE: —</div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid={`thumb-up-${pull.pull_id}`}
            onClick={(e) => { e.stopPropagation(); onVote(pull.pull_id, 'up'); }}
            className={`flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 border transition no-min-tap ${
              myVote === 'up'
                ? 'border-[#39FF14] text-[#39FF14] bg-[#39FF14]/10'
                : 'border-white/10 text-white/50 hover:border-[#39FF14]/40 hover:text-[#39FF14]'
            }`}
            aria-label="Thumbs up"
          >
            <ThumbsUp className="w-3 h-3" /> {pull.thumbs_up_count || 0}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function rarityColor(tier) {
  return {
    auto: '#FF0099',
    chase: '#FF0099',
    super_rare: '#FACC15',
    rare: '#00F0FF',
    common: '#94A3B8',
  }[tier] || '#94A3B8';
}

/**
 * "Battle a Champion" CTA — appears on top-3 weekly DUB STREAK winners' binders.
 * Drives competitive engagement by surfacing the king's thumb count for the week
 * and challenging visitors to beat it.
 */
function BattleChampionBanner({ cta, username }) {
  const rank = cta?.rank;
  const thumbs = cta?.thumbs_week ?? 0;
  const rankLabel = rank === 1 ? 'THIS WEEK\'S CROWN HOLDER' : `RANK #${rank} THIS WEEK`;
  const rankAccent = rank === 1 ? '#39FF14' : rank === 2 ? '#00F0FF' : '#FF0099';
  const Icon = rank === 1 ? Crown : Flame;

  return (
    <motion.section
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 220, damping: 24 }}
      data-testid="battle-champion-banner"
      className="relative overflow-hidden border mb-4 p-5 sm:p-6"
      style={{
        borderColor: `${rankAccent}55`,
        background: `linear-gradient(135deg, ${rankAccent}10 0%, rgba(10,10,10,0.95) 60%, ${rankAccent}15 100%)`,
        boxShadow: `0 0 50px ${rankAccent}25`,
      }}
    >
      <div
        className="absolute -top-16 -right-12 w-44 h-44 rounded-full pointer-events-none"
        style={{ background: rankAccent, filter: 'blur(120px)', opacity: 0.18 }}
      />
      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className="w-11 h-11 flex items-center justify-center border"
            style={{ borderColor: rankAccent, background: `${rankAccent}10` }}
          >
            <Icon className="w-5 h-5" style={{ color: rankAccent }} strokeWidth={2.3} />
          </div>
          <div>
            <div
              className="font-mono text-[10px] uppercase tracking-[0.32em] mb-0.5"
              style={{ color: rankAccent }}
              data-testid="battle-champion-rank"
            >
              {rankLabel}
            </div>
            <h2 className="font-heading text-xl sm:text-2xl text-white font-black uppercase tracking-tight leading-none">
              {rank === 1 ? (
                <>BATTLE THE <span style={{ color: rankAccent }}>CHAMPION</span></>
              ) : (
                <>BATTLE A <span style={{ color: rankAccent }}>TOP RIPPER</span></>
              )}
            </h2>
          </div>
        </div>

        <div className="flex-1 min-w-[220px] sm:flex-initial">
          <p
            className="text-sm sm:text-base text-white/85 font-mono leading-snug"
            data-testid="battle-champion-copy"
          >
            Beat their <span className="font-black text-white" style={{ color: rankAccent }}>{thumbs}</span>{' '}
            <span className="lowercase">thumbs this week to take the crown</span>{rank === 1 ? ' 👑' : ''}
          </p>
          <p className="text-[10px] font-mono uppercase tracking-[0.28em] text-white/40 mt-1">
            {username} · DUB STREAK leaderboard
          </p>
        </div>

        <Link
          to="/case"
          data-testid="battle-champion-cta-btn"
          className="px-5 py-2.5 font-heading tracking-widest text-sm transition no-min-tap hover:opacity-90"
          style={{ background: rankAccent, color: '#000' }}
        >
          OPEN MY BINDER →
        </Link>
      </div>
    </motion.section>
  );
}

function CardDetailModal({ pull, myVote, onVote, onClose }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-md flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="pull-detail-modal"
    >
      <motion.div
        initial={{ scale: 0.92, y: 20, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        exit={{ scale: 0.95, y: 20, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 280, damping: 24 }}
        className="bg-[#0a0a0a] border border-[#00F0FF]/30 max-w-md w-full p-6 relative"
        style={{ boxShadow: '0 0 60px rgba(0,240,255,0.18)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          data-testid="pull-detail-close"
          className="absolute top-2 right-3 text-white/40 hover:text-white text-2xl leading-none"
        >×</button>
        <div className="aspect-[3/4] bg-black/40 border border-white/10 flex items-center justify-center mb-4 p-6">
          {pull.card?.image_url ? (
            <img src={pull.card.image_url} alt={pull.card?.player} className="max-h-full max-w-full object-contain" />
          ) : (
            <div className="text-center">
              <div className="font-heading text-3xl text-white">{pull.card?.player || 'Unknown'}</div>
              {pull.card_number && <div className="font-mono text-white/40 mt-2">#{pull.card_number}</div>}
            </div>
          )}
        </div>
        <h3 className="font-heading text-xl text-white tracking-tight mb-1">{pull.card?.player || 'Unknown'}</h3>
        {pull.parallel && <p className="text-[#FF0099] text-sm italic mb-2">{pull.parallel}</p>}
        {pull.rarity_tier && pull.rarity_tier !== 'common' && (
          <span className="inline-block text-[10px] font-mono uppercase tracking-widest mb-3 px-2 py-0.5 border"
                style={{ color: rarityColor(pull.rarity_tier), borderColor: `${rarityColor(pull.rarity_tier)}66`, background: `${rarityColor(pull.rarity_tier)}11` }}>
            {pull.rarity_tier.replace('_', ' ')}
          </span>
        )}
        <div className="flex items-center gap-3 text-xs font-mono text-white/40 mb-4">
          <span><Calendar className="w-3 h-3 inline mr-1" /> {pull.timestamp ? new Date(pull.timestamp).toLocaleDateString() : '—'}</span>
          <span>·</span>
          <span className="inline-flex items-center gap-1"><Lock className="w-3 h-3" /> SOURCE PACK HIDDEN</span>
        </div>
        <div className="flex items-center gap-2 pt-2 border-t border-white/10">
          <button
            type="button"
            data-testid={`modal-thumb-up-${pull.pull_id}`}
            onClick={() => onVote(pull.pull_id, 'up')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 font-heading tracking-widest text-sm transition ${
              myVote === 'up'
                ? 'bg-[#39FF14] text-black'
                : 'bg-white/5 border border-white/10 text-white/70 hover:border-[#39FF14] hover:text-[#39FF14]'
            }`}
          >
            <ThumbsUp className="w-4 h-4" /> {pull.thumbs_up_count || 0}
          </button>
          <button
            type="button"
            data-testid={`modal-thumb-down-${pull.pull_id}`}
            onClick={() => onVote(pull.pull_id, 'down')}
            className={`px-4 py-3 border transition ${
              myVote === 'down'
                ? 'border-[#FF3939] text-[#FF3939] bg-[#FF3939]/10'
                : 'border-white/10 text-white/40 hover:border-[#FF3939]/40 hover:text-[#FF3939]'
            }`}
            aria-label="Thumbs down (private)"
          >
            <ThumbsDown className="w-4 h-4" />
          </button>
        </div>
        <p className="text-[10px] font-mono text-white/30 mt-2 text-center tracking-widest">
          Only thumbs-up count is public · Thumbs-down stays private signal
        </p>
      </motion.div>
    </motion.div>
  );
}
