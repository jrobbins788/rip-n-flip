import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import Navbar from '../components/Navbar';
import { Layers, ArrowRight, Eye, TrendingUp, Loader2, Flame, ThumbsUp, Trophy } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PublicGallery() {
  const [binders, setBinders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sport, setSport] = useState('');
  const [leaderboard, setLeaderboard] = useState({ entries: [], period: 'week' });
  const [leaderPeriod, setLeaderPeriod] = useState('week');
  const [leaderLoading, setLeaderLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    (async () => {
      try {
        const r = await axios.get(`${API}/binders/public`, { params: sport ? { sport } : {} });
        if (cancel) return;
        setBinders(r.data?.binders || []);
      } catch {
        if (!cancel) setBinders([]);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [sport]);

  useEffect(() => {
    let cancel = false;
    setLeaderLoading(true);
    (async () => {
      try {
        const r = await axios.get(`${API}/leaderboard/dub-streak`, { params: { period: leaderPeriod, limit: 10 } });
        if (cancel) return;
        setLeaderboard(r.data || { entries: [], period: leaderPeriod });
      } catch {
        if (!cancel) setLeaderboard({ entries: [], period: leaderPeriod });
      } finally {
        if (!cancel) setLeaderLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [leaderPeriod]);

  const sports = ['', 'NBA', 'NFL', 'MLB', 'NHL', 'Soccer'];

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      <div className="pt-20 px-4 max-w-7xl mx-auto pb-16">
        <header className="mb-8">
          <div className="inline-flex items-center gap-2 text-[#00F0FF] font-mono text-xs tracking-widest mb-3" data-testid="gallery-tag">
            <Eye className="w-4 h-4" />
            // PUBLIC BINDERS
          </div>
          <h1 className="font-heading text-4xl sm:text-6xl font-black text-white uppercase tracking-tight leading-none mb-3" data-testid="gallery-title">
            THE <span className="text-[#00F0FF]">COMMUNITY</span> BINDER
          </h1>
          <p className="text-white/60 max-w-2xl text-sm sm:text-base">
            Real collectors. Real pulls. <span className="text-white/40">Source packs hidden by design — tap a binder to see the cards, not the pack.</span>
          </p>
        </header>

        {/* DUB STREAK LEADERBOARD */}
        <DubStreakLeaderboard
          leaderboard={leaderboard}
          period={leaderPeriod}
          onPeriodChange={setLeaderPeriod}
          loading={leaderLoading}
        />

        {/* Sport filter */}
        <div className="flex items-center justify-between flex-wrap gap-3 mt-10 mb-5">
          <h2 className="font-heading text-xl sm:text-2xl text-white uppercase tracking-tight">All Binders</h2>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {sports.map((s) => (
              <button
                key={s || 'all'}
                onClick={() => setSport(s)}
                data-testid={`filter-${s || 'all'}`}
                className={`px-3 py-1.5 text-[11px] font-mono uppercase tracking-widest border whitespace-nowrap transition ${
                  sport === s
                    ? 'border-[#00F0FF] text-[#00F0FF] bg-[#00F0FF]/10'
                    : 'border-white/10 text-white/50 hover:border-white/30 hover:text-white/80'
                }`}
              >
                {s || 'ALL'}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-white/40 py-20 justify-center">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading binders...
          </div>
        ) : binders.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="gallery-grid">
            {binders.map((b) => (
              <Link
                key={b.user_id}
                to={`/binders/${b.user_id}`}
                data-testid={`binder-card-${b.user_id}`}
                className="group bg-[#0a0a0a] border border-[#27272a] hover:border-[#00F0FF]/50 p-5 transition-all"
                style={{ willChange: 'transform' }}
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-12 h-12 rounded-full bg-[#00F0FF]/10 border border-[#00F0FF]/30 flex items-center justify-center overflow-hidden">
                    {b.picture ? (
                      <img src={b.picture} alt={b.username} className="w-full h-full object-cover" loading="lazy" />
                    ) : (
                      <span className="font-heading text-[#00F0FF] text-lg">{(b.username || '?').slice(0,1).toUpperCase()}</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-heading text-white text-lg truncate" data-testid={`binder-username-${b.user_id}`}>
                      {b.username}
                    </div>
                    <div className="text-[10px] font-mono text-white/40 uppercase tracking-widest">
                      Collector
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <Stat icon={<Layers className="w-3 h-3" />} label="Binders" value={b.binder_count} />
                  <Stat icon={<TrendingUp className="w-3 h-3" />} label="Pulls" value={b.pulls_total} />
                </div>
                {b.sports?.length > 0 && (
                  <div className="flex gap-1 mb-3 flex-wrap">
                    {b.sports.slice(0, 4).map((s) => (
                      <span key={s} className="text-[9px] font-mono px-1.5 py-0.5 bg-white/5 border border-white/10 text-white/60 tracking-widest">{s}</span>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-end text-[10px] font-mono uppercase tracking-widest text-[#00F0FF]/0 group-hover:text-[#00F0FF] transition-colors">
                  VIEW BINDER <ArrowRight className="w-3 h-3 ml-1" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DubStreakLeaderboard({ leaderboard, period, onPeriodChange, loading }) {
  const entries = leaderboard?.entries || [];
  const podium = entries.slice(0, 3);
  const rest = entries.slice(3, 10);

  return (
    <section
      data-testid="dub-streak-leaderboard"
      className="relative overflow-hidden bg-gradient-to-br from-[#39FF14]/8 via-[#0a0a0a] to-[#FF0099]/8 border border-[#39FF14]/25 p-5 sm:p-7"
    >
      <div className="absolute -top-24 -right-24 w-72 h-72 bg-[#39FF14] rounded-full blur-[140px] opacity-15 pointer-events-none" />
      <div className="absolute -bottom-32 -left-24 w-72 h-72 bg-[#FF0099] rounded-full blur-[140px] opacity-10 pointer-events-none" />

      <div className="relative">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
          <div>
            <div className="inline-flex items-center gap-2 text-[#39FF14] font-mono text-[10px] tracking-[0.3em] uppercase mb-2" data-testid="leaderboard-tag">
              <Trophy className="w-4 h-4" />
              // DUB STREAK
            </div>
            <h2 className="font-heading text-2xl sm:text-3xl text-white font-black uppercase tracking-tight leading-none">
              TOP <span className="text-[#39FF14]">RIPPERS</span>
              <span className="ml-3 text-white/40 text-sm font-mono">/ ranked by community thumbs-up</span>
            </h2>
          </div>
          <div className="flex gap-1 border border-white/10 p-0.5">
            {[
              { key: 'week', label: 'THIS WEEK' },
              { key: 'all', label: 'ALL-TIME' },
            ].map((opt) => (
              <button
                key={opt.key}
                onClick={() => onPeriodChange(opt.key)}
                data-testid={`leader-period-${opt.key}`}
                className={`px-3 py-1.5 text-[10px] font-mono uppercase tracking-widest transition ${
                  period === opt.key
                    ? 'bg-[#39FF14] text-black'
                    : 'text-white/50 hover:text-white'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="text-center py-8 text-white/40 text-xs font-mono uppercase tracking-widest">Loading ranks...</div>
        ) : entries.length === 0 ? (
          <div className="text-center py-8" data-testid="leaderboard-empty">
            <p className="text-white/50 text-sm">No thumbs-up cast yet. Be the first to flex.</p>
            <Link to="/case" className="inline-block mt-3 text-[#39FF14] text-xs font-mono uppercase tracking-widest hover:underline">
              LOG A RIP → MAKE IT PUBLIC → EARN DUBS
            </Link>
          </div>
        ) : (
          <>
            {/* Podium row — top 3 with flame on #1 */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              {podium.map((e) => (
                <Link
                  key={e.user_id}
                  to={`/binders/${e.user_id}`}
                  data-testid={`leader-podium-${e.rank}`}
                  className={`relative bg-[#0a0a0a] border p-4 flex items-center gap-3 transition hover:scale-[1.02] ${
                    e.rank === 1
                      ? 'border-[#39FF14] shadow-[0_0_40px_rgba(57,255,20,0.25)]'
                      : e.rank === 2
                      ? 'border-[#00F0FF]/50'
                      : 'border-[#FF0099]/40'
                  }`}
                  style={{ willChange: 'transform' }}
                >
                  {e.is_flame && (
                    <Flame
                      data-testid="leader-flame-icon"
                      className="absolute -top-2.5 -right-2.5 w-7 h-7 text-[#FF6B00] fill-[#FFB800] animate-pulse"
                      strokeWidth={2}
                    />
                  )}
                  <div
                    className={`flex items-center justify-center w-10 h-10 font-heading font-black text-xl ${
                      e.rank === 1 ? 'text-[#39FF14]' : e.rank === 2 ? 'text-[#00F0FF]' : 'text-[#FF0099]'
                    }`}
                  >
                    #{e.rank}
                  </div>
                  <div className="w-10 h-10 rounded-full bg-white/5 border border-white/10 overflow-hidden flex items-center justify-center">
                    {e.picture ? (
                      <img src={e.picture} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <span className="font-heading text-white text-sm">{e.username.slice(0, 1).toUpperCase()}</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-heading text-white truncate text-sm">{e.username}</div>
                    <div className="flex items-center gap-1 text-[#39FF14] text-[11px] font-mono">
                      <ThumbsUp className="w-3 h-3" />
                      {e.thumbs_total} {period === 'week' ? 'this week' : 'all-time'}
                    </div>
                  </div>
                </Link>
              ))}
            </div>

            {/* Rest row — compact 4-10 */}
            {rest.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                {rest.map((e) => (
                  <Link
                    key={e.user_id}
                    to={`/binders/${e.user_id}`}
                    data-testid={`leader-row-${e.rank}`}
                    className="flex items-center gap-3 px-3 py-2 bg-[#0a0a0a]/50 border border-white/5 hover:border-white/20 transition text-sm"
                  >
                    <span className="font-mono text-white/40 w-6">#{e.rank}</span>
                    <span className="text-white truncate flex-1">{e.username}</span>
                    <span className="flex items-center gap-1 text-[#39FF14] text-xs font-mono">
                      <ThumbsUp className="w-3 h-3" /> {e.thumbs_total}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div className="bg-black/30 px-3 py-2">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-widest text-white/40 font-mono mb-0.5">
        {icon} {label}
      </div>
      <div className="font-mono font-bold text-white">{value}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-20 max-w-md mx-auto" data-testid="gallery-empty">
      <div className="w-16 h-16 mx-auto mb-4 bg-[#00F0FF]/10 border border-[#00F0FF]/30 flex items-center justify-center">
        <Eye className="w-7 h-7 text-[#00F0FF]" />
      </div>
      <h3 className="font-heading text-2xl text-white tracking-tight mb-2">NO PUBLIC BINDERS YET</h3>
      <p className="text-white/60 text-sm mb-6">
        Be the first to flex your collection. Log some rips in your Display Case, then toggle a binder to public.
      </p>
      <Link to="/case" data-testid="gallery-empty-cta" className="inline-block bg-[#39FF14] text-black font-heading tracking-widest px-6 py-3 hover:opacity-90 transition">
        OPEN MY BINDER →
      </Link>
    </div>
  );
}
