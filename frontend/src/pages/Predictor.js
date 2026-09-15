import { useState, useEffect } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Navbar from '../components/Navbar';
import { Dice5, ArrowLeft, Sparkles, TrendingUp, RefreshCw, Lock, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const sportColors = {
  NBA: 'border-red-500/40 bg-red-600/10 text-red-300',
  NFL: 'border-blue-500/40 bg-blue-600/10 text-blue-300',
  MLB: 'border-indigo-500/40 bg-indigo-600/10 text-indigo-300',
  NHL: 'border-gray-500/40 bg-gray-600/10 text-gray-200',
  Soccer: 'border-purple-500/40 bg-purple-600/10 text-purple-300',
};

export default function Predictor() {
  const [searchParams] = useSearchParams();
  const [packs, setPacks] = useState([]);
  const [selectedId, setSelectedId] = useState(searchParams.get('pack') || null);
  const [result, setResult] = useState(null);
  const [paywall, setPaywall] = useState(null);
  const [ripping, setRipping] = useState(false);
  const [revealedCount, setRevealedCount] = useState(0);
  const [usesLeft, setUsesLeft] = useState(2); // Free tier default

  useEffect(() => {
    axios.get(`${API}/analyzer/packs`).then((r) => setPacks(r.data.packs || []));
  }, []);

  // Reveal cards one by one for drama
  useEffect(() => {
    if (!result || !ripping) return;
    const total = result.cards?.length || 0;
    if (revealedCount >= total) {
      setRipping(false);
      return;
    }
    // Slow down right before the hit climax for tension
    const nextIsHit = result.cards[revealedCount]?.is_hit;
    const delay = nextIsHit ? 600 : 280;
    const t = setTimeout(() => setRevealedCount((c) => c + 1), delay);
    return () => clearTimeout(t);
  }, [result, revealedCount, ripping]);

  const rip = async () => {
    if (!selectedId || ripping) return;
    setRipping(true);
    setResult(null);
    setRevealedCount(0);
    setPaywall(null);
    try {
      const res = await axios.post(
        `${API}/predictor/rip`,
        { pack_id: selectedId, num_cards: 8 },
        { withCredentials: true }
      );
      // Pause briefly so the "ripping" animation lands first
      setTimeout(() => {
        setResult(res.data);
        if (res.data?.usage) {
          const left = Math.max(0, (res.data.usage.limit || 0) - (res.data.usage.used || 0));
          setUsesLeft(left);
        } else {
          setUsesLeft((u) => Math.max(0, u - 1));
        }
      }, 1100);
    } catch (e) {
      setRipping(false);
      if (e?.response?.status === 429) {
        const d = e.response.data?.detail || {};
        setPaywall({
          message: d.message || "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB.",
          cta_url: d.cta_url || '/vault',
          used: d.used,
          limit: d.limit,
        });
        setUsesLeft(0);
      }
    }
  };

  const selectedPack = packs.find((p) => p.pack_id === selectedId);

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      <main className="pt-24 pb-16 px-4">
        <div className="max-w-6xl mx-auto">
          <Link to="/" className="inline-flex items-center gap-2 text-white/50 hover:text-white text-sm font-mono mb-4" data-testid="predictor-back">
            <ArrowLeft className="w-4 h-4" /> HOME
          </Link>

          <div className="mb-8">
            <div className="inline-flex items-center gap-2 bg-[#FF0099]/10 border border-[#FF0099]/40 px-3 py-1 mb-3">
              <Dice5 className="w-4 h-4 text-[#FF0099]" />
              <span className="text-[#FF0099] font-mono text-xs tracking-widest">PROBABILISTIC SIMULATOR</span>
            </div>
            <h1 className="font-heading text-5xl sm:text-7xl font-black text-white uppercase tracking-tight">
              PACK <span className="text-[#FF0099]">PREDICTOR</span>
            </h1>
            <p className="text-white/60 mt-2 max-w-2xl">
              Pick a pack, smash <span className="text-[#FF0099] font-bold">RIP</span>, and watch what you might pull. For fun — not a cheat code (it lies a little on purpose).
            </p>
          </div>

          {/* Tier limit indicator */}
          <div className="mb-6 inline-flex items-center gap-2 bg-yellow-500/10 border border-yellow-500/30 px-3 py-2 text-yellow-300 text-xs font-mono" data-testid="usage-counter">
            <Lock className="w-3 h-3" />
            FREE TIER: {usesLeft}/2 RIPS LEFT TODAY · <Link to="/vault" className="underline hover:text-yellow-200">UPGRADE TO PRO ($3.99/mo) for 5/day</Link>
          </div>

          {/* Pack picker */}
          <section className="mb-8">
            <h2 className="font-heading text-lg tracking-widest text-white/70 mb-4">
              SELECT A PACK
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {packs.map((p) => {
                const sportClass = sportColors[p.sport] || 'border-white/20 bg-white/5 text-white/80';
                const isActive = selectedId === p.pack_id;
                return (
                  <button
                    key={p.pack_id}
                    onClick={() => { setSelectedId(p.pack_id); setResult(null); setRevealedCount(0); }}
                    disabled={ripping}
                    data-testid={`predictor-pick-${p.pack_id}`}
                    className={`text-left bg-[#0a0a0a] border p-3 transition-all ${
                      isActive ? 'border-[#FF0099]' : 'border-[#27272a] hover:border-white/40'
                    } ${ripping ? 'opacity-50 cursor-wait' : ''}`}
                  >
                    <div className={`inline-flex text-[10px] font-mono px-1.5 py-0.5 border ${sportClass} mb-1`}>
                      {p.sport}
                    </div>
                    <div className="font-heading text-xs text-white tracking-tight leading-tight">{p.name}</div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Big RIP button */}
          {selectedPack && !ripping && !result && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center mb-10"
            >
              <button
                onClick={rip}
                disabled={usesLeft <= 0}
                data-testid="rip-button"
                className="relative bg-[#FF0099] text-white font-heading text-3xl sm:text-5xl font-black tracking-widest px-12 py-6 sm:py-8 hover:bg-[#FF0099]/90 transition-all hover:scale-105 disabled:opacity-30 disabled:cursor-not-allowed"
                style={{ boxShadow: '0 0 60px #FF0099aa' }}
              >
                🃏 RIP THE PACK 🃏
              </button>
              <div className="mt-3 text-white/60 text-sm">{selectedPack.name}</div>
            </motion.div>
          )}

          {/* Ripping animation */}
          <AnimatePresence>
            {ripping && !result && (
              <motion.div
                key="ripping"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-center py-12"
                data-testid="ripping-animation"
              >
                <motion.div
                  animate={{ rotate: [0, -8, 8, -4, 4, 0], scale: [1, 1.1, 1.1, 1, 1] }}
                  transition={{ duration: 0.8, repeat: Infinity }}
                  className="inline-block text-8xl mb-4"
                >
                  📦
                </motion.div>
                <div className="font-heading text-2xl text-white tracking-widest">RIPPING...</div>
                <div className="text-white/40 font-mono text-xs mt-1">computing your pulls</div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Cards reveal */}
          {result && (
            <motion.section
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mb-8"
              data-testid="rip-result"
            >
              <h2 className="font-heading text-2xl text-white tracking-widest mb-4 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-[#FF0099]" /> YOUR SIMULATED PULLS
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-6">
                {result.cards.map((c, i) => (
                  <CardReveal key={i} card={c} index={i} visible={i < revealedCount} totalCount={result.cards.length} />
                ))}
              </div>

              {revealedCount >= result.cards.length && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-[#0a0a0a] border border-[#27272a] p-5 mb-4"
                  data-testid="rip-summary"
                >
                  <h3 className="font-heading text-sm text-white/60 tracking-widest mb-3 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-[#39FF14]" /> RIP RECAP
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                    <Stat label="Hit" value={result.summary.hit_count > 0 ? 'YES 🔥' : '—'} accent={result.summary.hit_count > 0 ? '#FF0099' : '#27272a'} />
                    <Stat label="Mystery Cards" value={result.summary.mystery_count} accent="#94A3B8" />
                    <Stat label="Est. Value" value={`$${result.summary.estimated_value_low}-${result.summary.estimated_value_high}`} accent="#39FF14" />
                    <Stat
                      label="vs MSRP"
                      value={`${result.summary.vs_retail_low >= 0 ? '+' : ''}$${result.summary.vs_retail_low}`}
                      accent={result.summary.vs_retail_low >= 0 ? '#39FF14' : '#FF3939'}
                    />
                  </div>
                  <div className="text-[10px] text-white/30 italic mt-3 text-center">
                    Simulated probabilistically · Hit chance for this pack: {(result.hit_probability * 100).toFixed(1)}%
                  </div>
                </motion.div>
              )}

              {revealedCount >= result.cards.length && (
                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    onClick={() => { setResult(null); setRevealedCount(0); }}
                    disabled={usesLeft <= 0}
                    data-testid="rip-again-btn"
                    className="flex-1 bg-[#FF0099] text-white font-heading tracking-widest h-12 hover:bg-[#FF0099]/90 disabled:opacity-30 flex items-center justify-center gap-2"
                  >
                    <RefreshCw className="w-4 h-4" /> RIP AGAIN ({usesLeft} LEFT)
                  </button>
                  <Link to={`/analyzer?pack=${selectedId}`} className="flex-1" data-testid="see-analyzer">
                    <button className="w-full bg-white/5 border border-white/20 text-white font-heading tracking-widest h-12 hover:border-[#00F0FF] hover:text-[#00F0FF]">
                      🧠 SEE FULL ANALYSIS →
                    </button>
                  </Link>
                </div>
              )}
            </motion.section>
          )}

          {usesLeft === 0 && (
            <div className="bg-gradient-to-br from-[#FF0099]/10 to-[#00F0FF]/10 border border-[#FF0099]/40 p-6 text-center" data-testid="upgrade-paywall">
              <Lock className="w-8 h-8 text-[#FF0099] mx-auto mb-2" />
              <div className="font-heading text-xl text-white tracking-widest">DAILY LIMIT HIT</div>
              <p className="text-white/80 text-sm mt-2 mb-4 max-w-md mx-auto italic">
                {paywall?.message || "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB."}
              </p>
              {paywall?.used !== undefined && (
                <p className="text-white/40 font-mono text-[10px] mb-3">{paywall.used} / {paywall.limit} used today</p>
              )}
              <Link to={paywall?.cta_url || '/vault'} data-testid="paywall-upgrade-btn">
                <button className="bg-[#FF0099] text-white font-heading tracking-widest px-8 py-3 hover:bg-[#FF0099]/90">
                  GO PRO — $3.99/mo
                </button>
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div>
      <div className="text-[9px] text-white/40 font-mono uppercase">{label}</div>
      <div className="font-mono font-bold text-base sm:text-lg" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function CardReveal({ card, index, visible, totalCount }) {
  const isHit = card.is_hit;
  const isMystery = card.is_mystery;
  const isLast = index === totalCount - 1;
  // Hit card always lights up neon pink; mystery cards stay muted slate;
  // base cards get a soft cyan accent.
  const accent = isHit ? '#FF0099' : isMystery ? '#475569' : '#00F0FF';

  return (
    <motion.div
      initial={{ rotateY: 180, scale: 0.7, opacity: 0 }}
      animate={visible ? { rotateY: 0, scale: 1, opacity: 1 } : { rotateY: 180, scale: 0.7, opacity: 0 }}
      transition={{ duration: 0.55, delay: index * 0.06, type: 'spring', stiffness: 110, damping: 18 }}
      style={{
        perspective: 1000,
        transformStyle: 'preserve-3d',
        willChange: 'transform',
        backfaceVisibility: 'hidden',
        boxShadow: isHit && visible ? `0 0 40px ${accent}66, inset 0 0 20px ${accent}22` : undefined,
      }}
      className={`relative aspect-[3/4] bg-[#0a0a0a] border-2 p-3 overflow-hidden ${isLast && isHit ? 'col-span-2 sm:col-span-1' : ''}`}
      data-testid={`pull-card-${index}`}
    >
      <div
        className="absolute inset-0 opacity-30"
        style={{ background: `radial-gradient(circle at 50% 0%, ${accent}, transparent 70%)`, borderColor: accent }}
      />
      <div className="absolute inset-0 border-2 pointer-events-none" style={{ borderColor: accent }} />
      <div className="relative z-10 flex flex-col h-full justify-between">
        <div>
          <div className="text-[8px] font-mono uppercase tracking-widest mb-1" style={{ color: accent }}>
            {card.tier}
          </div>
          {isHit && (
            <div className="inline-block bg-[#FF0099] text-white text-[8px] font-bold px-1.5 py-0.5 mb-1 tracking-widest animate-pulse">
              🔥 HIT!
            </div>
          )}
          {isMystery && !isHit && (
            <div className="inline-block bg-white/5 border border-white/15 text-white/40 text-[8px] font-mono px-1.5 py-0.5 mb-1 tracking-widest">
              ? MYSTERY
            </div>
          )}
          <div className={`font-heading leading-tight ${isHit ? 'text-white text-sm sm:text-base' : isMystery ? 'text-white/55 text-xs' : 'text-white text-xs sm:text-sm'}`}>
            {card.name}
          </div>
          {card.rarity && card.rarity !== card.tier && (
            <div className="text-[9px] text-white/50 italic mt-1">{card.rarity}</div>
          )}
        </div>
        <div className="font-mono text-base font-bold" style={{ color: isHit ? accent : (isMystery ? '#475569' : '#39FF14') }}>
          {card.value_estimate}
        </div>
      </div>
    </motion.div>
  );
}
