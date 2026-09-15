import { useState, useEffect } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import Navbar from '../components/Navbar';
import ShareVerdictButton from '../components/ShareVerdictButton';
import { Brain, ArrowLeft, TrendingUp, Trophy, Skull, Sparkles, Loader2, Flame, ExternalLink } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const sportColors = {
  NBA: 'border-red-500/40 bg-red-600/10 text-red-300',
  NFL: 'border-blue-500/40 bg-blue-600/10 text-blue-300',
  MLB: 'border-indigo-500/40 bg-indigo-600/10 text-indigo-300',
  NHL: 'border-gray-500/40 bg-gray-600/10 text-gray-200',
  Soccer: 'border-purple-500/40 bg-purple-600/10 text-purple-300',
};

const verdictStyle = {
  DUB:   { color: '#39FF14', icon: <Trophy className="w-12 h-12" />, sub: 'BUY THE WAX' },
  MID:   { color: '#FACC15', icon: <Sparkles className="w-12 h-12" />, sub: 'RIP FOR FUN' },
  TRASH: { color: '#FF3939', icon: <Skull className="w-12 h-12" />, sub: 'SAVE YOUR CASH' },
};

export default function Analyzer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [packs, setPacks] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedId, setSelectedId] = useState(searchParams.get('pack') || null);

  useEffect(() => {
    axios.get(`${API}/analyzer/packs`).then((r) => {
      setPacks(r.data.packs || []);
      setLoadingList(false);
    }).catch(() => setLoadingList(false));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setAnalyzing(true);
    setAnalysis(null);
    axios.get(`${API}/analyzer/${selectedId}`, { withCredentials: true })
      .then((r) => setAnalysis(r.data))
      .catch((err) => {
        if (err?.response?.status === 403) {
          const d = err.response.data?.detail || {};
          setAnalysis({ paywall: true, message: d.message, cta_url: d.cta_url || '/vault', used: d.used, limit: d.limit });
        } else {
          setAnalysis({ error: true });
        }
      })
      .finally(() => setAnalyzing(false));
  }, [selectedId]);

  const pickPack = (id) => {
    setSelectedId(id);
    setSearchParams({ pack: id });
  };

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      <main className="pt-24 pb-16 px-4">
        <div className="max-w-7xl mx-auto">
          <Link to="/" className="inline-flex items-center gap-2 text-white/50 hover:text-white text-sm font-mono mb-4" data-testid="analyzer-back">
            <ArrowLeft className="w-4 h-4" /> HOME
          </Link>

          <div className="mb-8">
            <div className="inline-flex items-center gap-2 bg-[#00F0FF]/10 border border-[#00F0FF]/40 px-3 py-1 mb-3">
              <Brain className="w-4 h-4 text-[#00F0FF]" />
              <span className="text-[#00F0FF] font-mono text-xs tracking-widest">VERDICT ENGINE</span>
            </div>
            <h1 className="font-heading text-5xl sm:text-7xl font-black text-white uppercase tracking-tight">
              PACK <span className="text-[#00F0FF]">ANALYZER</span>
            </h1>
            <p className="text-white/60 mt-2 max-w-2xl">
              Pick a pack. Get an instant, market-verified verdict — <span className="text-[#39FF14] font-bold">DUB</span>, <span className="text-yellow-300 font-bold">MID</span>, or <span className="text-[#FF3939] font-bold">TRASH</span>. Know before you rip.
            </p>
          </div>

          {/* Pack Picker */}
          <section className="mb-10">
            <h2 className="font-heading text-lg tracking-widest text-white/70 mb-4 flex items-center gap-2">
              <Flame className="w-4 h-4 text-[#FF0099]" /> SELECT A PACK
            </h2>
            {loadingList ? (
              <div className="text-white/40 font-mono text-sm flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading packs...
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {packs.map((p) => {
                  const sportClass = sportColors[p.sport] || 'border-white/20 bg-white/5 text-white/80';
                  const isActive = selectedId === p.pack_id;
                  return (
                    <button
                      key={p.pack_id}
                      onClick={() => pickPack(p.pack_id)}
                      data-testid={`analyzer-pick-${p.pack_id}`}
                      className={`text-left bg-[#0a0a0a] border p-4 transition-all ${
                        isActive ? 'border-[#00F0FF]' : 'border-[#27272a] hover:border-white/40'
                      }`}
                    >
                      <div className={`inline-flex text-[10px] font-mono px-1.5 py-0.5 border ${sportClass} mb-2`}>
                        {p.sport}
                      </div>
                      <div className="font-heading text-sm text-white tracking-tight leading-tight mb-1">{p.name}</div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-white/50">~${p.retail_price}</span>
                        <span className="text-[10px] font-mono text-[#FF0099]">{p.badge}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* Analysis Result */}
          {analyzing && (
            <div className="bg-[#0a0a0a] border border-[#27272a] p-12 text-center" data-testid="analyzer-loading">
              <Loader2 className="w-12 h-12 text-[#00F0FF] animate-spin mx-auto mb-4" />
              <div className="font-heading text-white tracking-widest text-lg">RUNNING VERDICT ENGINE...</div>
              <div className="text-white/40 text-sm mt-1">Pulling live market data + computing chase strength</div>
            </div>
          )}

          {analysis && !analysis.error && !analysis.paywall && (
            <AnalysisResult data={analysis} />
          )}

          {analysis?.paywall && (
            <div className="bg-[#0a0a0a] border border-[#FF0099]/50 p-8 text-center" data-testid="analyzer-paywall" style={{ boxShadow: '0 0 40px rgba(255,0,153,0.18)' }}>
              <div className="inline-flex items-center gap-2 text-[#FF0099] font-mono text-[10px] tracking-widest mb-3">
                <span className="w-1.5 h-1.5 rounded-full bg-[#FF0099] animate-pulse" /> // FREE TIER LIMIT REACHED
              </div>
              <h3 className="font-heading text-3xl font-black text-white tracking-tight mb-3 uppercase">
                You&apos;ve Maxed Out This Week
              </h3>
              <p className="text-white/70 text-sm sm:text-base mb-2 max-w-md mx-auto">
                {analysis.message || 'Free tier is capped at 2 pack analyses per 7 days.'}
              </p>
              {analysis.used !== undefined && (
                <p className="text-white/40 font-mono text-xs mb-6">
                  {analysis.used} / {analysis.limit} used this week
                </p>
              )}
              <Link
                to={analysis.cta_url || '/vault'}
                data-testid="paywall-upgrade-btn"
                className="inline-block bg-[#FF0099] text-white font-heading tracking-widest px-8 py-4 hover:opacity-90 transition"
              >
                GO PRO TO UNLOCK — $3.99/mo
              </Link>
              <p className="text-white/30 text-[11px] font-mono tracking-widest mt-4">10-DAY FREE TRIAL · CANCEL ANYTIME</p>
            </div>
          )}

          {analysis?.error && (
            <div className="bg-red-500/10 border border-red-500/30 p-6 text-red-300">
              Couldn&apos;t analyze that pack. Try a different one.
            </div>
          )}

          {!selectedId && !analyzing && (
            <div className="bg-[#0a0a0a] border border-dashed border-[#27272a] p-12 text-center text-white/40">
              <Brain className="w-12 h-12 mx-auto mb-3 opacity-40" />
              <p className="font-mono text-sm">↑ Pick a pack above to see the verdict</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}


function AnalysisResult({ data }) {
  const v = data.verdict;
  const style = verdictStyle[v.rating] || verdictStyle.MID;
  const market = data.live_market;
  const sportClass = sportColors[data.pack.sport] || 'border-white/20 bg-white/5 text-white/80';

  return (
    <div className="space-y-6" data-testid="analyzer-result">
      {/* Verdict Card */}
      <div
        className="relative overflow-hidden border-2 p-6 sm:p-10"
        style={{ borderColor: style.color, background: `linear-gradient(135deg, ${style.color}11, #0a0a0a 60%)` }}
        data-testid={`verdict-${v.rating.toLowerCase()}`}
      >
        <div className="absolute top-0 right-0 w-72 h-72 rounded-full blur-[100px] opacity-20" style={{ background: style.color }} />
        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-3 gap-6 items-center">
          <div className="lg:col-span-1 flex flex-col items-start">
            <span className={`inline-flex text-[10px] font-mono px-2 py-0.5 border ${sportClass} mb-3`}>
              {data.pack.sport}
            </span>
            <h2 className="font-heading text-2xl sm:text-3xl font-black text-white tracking-tight leading-tight">
              {data.pack.name}
            </h2>
            <p className="text-white/60 italic text-sm mt-1">{data.pack.tagline}</p>
            <p className="text-white/50 text-xs mt-2">{data.pack.why_hot}</p>
          </div>

          <div className="lg:col-span-1 text-center">
            <div className="inline-flex items-center justify-center w-32 h-32 sm:w-40 sm:h-40 border-4 mb-3 mx-auto"
                 style={{ borderColor: style.color, color: style.color }}>
              {style.icon}
            </div>
            <div className="font-heading text-5xl sm:text-7xl font-black uppercase tracking-tight" style={{ color: style.color }}>
              {v.rating}
            </div>
            <div className="font-mono text-xs text-white/60 tracking-widest mt-1">{style.sub}</div>
            {v.expected_pull_value !== undefined && (
              <div className="mt-3 inline-flex flex-col gap-0.5 items-center bg-black/40 px-3 py-2 font-mono text-[11px] text-white/70">
                <span>Expected: <span style={{ color: style.color }} className="font-bold">${v.expected_pull_value}</span></span>
                <span>Pack cost: <span className="text-white">${v.pack_cost}</span> <span className="text-white/40 text-[9px]">({v.pack_cost_source})</span></span>
              </div>
            )}
          </div>

          <div className="lg:col-span-1">
            <p className="text-white/80 text-sm leading-relaxed mb-3">{v.summary}</p>
            <ul className="space-y-1.5 text-xs">
              {(v.factors || [])
                // Black-box: strip any factor that exposes internal algorithm
                // labels (confidence tiers, blend weights, community pull counts,
                // performance ratios, final score, etc.). Only market-facing
                // signals stay visible.
                .filter((f) => {
                  const label = (typeof f === 'string' ? f : f.label) || '';
                  return !/confidence|community pull|hit.?rate|market perf|final.*score|blended|intelligence|training/i.test(label);
                })
                .map((f, i) => {
                // New shape: {label, value, tone}. Legacy fallback: string.
                if (typeof f === 'string') {
                  return (
                    <li key={i} className={`flex gap-1.5 ${f.startsWith('+') ? 'text-[#39FF14]' : f.startsWith('-') ? 'text-[#FF3939]' : 'text-white/50'}`}>
                      <span className="font-mono">{f}</span>
                    </li>
                  );
                }
                const toneColor = f.tone === 'positive' ? '#39FF14' : f.tone === 'negative' ? '#FF3939' : '#94A3B8';
                return (
                  <li key={i} className="flex items-start justify-between gap-2 bg-black/20 px-2 py-1">
                    <span className="text-white/70">{f.label}</span>
                    <span className="font-mono whitespace-nowrap" style={{ color: toneColor }}>{f.value}</span>
                  </li>
                );
              })}
            </ul>
            <div className="mt-2 text-[9px] font-mono text-[#39FF14]/60 tracking-widest">
              ✓ MARKET-VERIFIED VERDICT
            </div>
          </div>
        </div>

        <div className="relative z-10 mt-6">
          <ShareVerdictButton analysis={data} />
        </div>
      </div>

      {/* Live Market */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-[#0a0a0a] border border-[#27272a] p-5" data-testid="market-stats">          <h3 className="font-heading text-sm text-white/60 tracking-widest mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#39FF14]" /> LIVE eBAY SEALED MARKET
          </h3>
          {market.count > 0 ? (
            <>
              <div className="grid grid-cols-3 gap-2 text-center mb-4">
                <div>
                  <div className="text-[10px] text-white/40 font-mono uppercase">Low</div>
                  <div className="font-mono text-white text-lg">${market.min}</div>
                </div>
                <div className="border-x border-white/10">
                  <div className="text-[10px] text-white/40 font-mono uppercase">Avg</div>
                  <div className="font-mono text-[#39FF14] text-2xl font-bold">${market.avg}</div>
                </div>
                <div>
                  <div className="text-[10px] text-white/40 font-mono uppercase">High</div>
                  <div className="font-mono text-white text-lg">${market.max}</div>
                </div>
              </div>
              <div className="text-xs text-white/40 mb-2">{market.count} live listings · MSRP ~${data.pack.retail_price}</div>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {market.sample_listings.map((l, i) => (
                  <a key={i} href={l.url} target="_blank" rel="noopener noreferrer"
                     className="flex items-center gap-2 bg-black/30 hover:bg-black/60 px-2 py-1.5 text-[11px]">
                    <span className="font-mono text-[#39FF14] min-w-[52px]">{l.price_text}</span>
                    <span className="text-white/70 truncate flex-1">{l.title}</span>
                    <ExternalLink className="w-3 h-3 text-white/30" />
                  </a>
                ))}
              </div>
            </>
          ) : (
            <div className="text-yellow-400/80 text-sm">
              {market.blocked ? 'eBay rate-limited preview pod — production server will pull live data instantly.' : 'No live listings found right now.'}
              <div className="text-white/40 mt-2 text-xs">MSRP ~${data.pack.retail_price}</div>
            </div>
          )}
        </div>

        {/* Tier Odds */}
        <div className="bg-[#0a0a0a] border border-[#27272a] p-5" data-testid="tier-odds">
          <h3 className="font-heading text-sm text-white/60 tracking-widest mb-4">EXPECTED PULLS BY TIER</h3>
          <div className="space-y-2">
            {data.tier_odds.map((t, i) => {
              const intensity = Math.min(t.ratio, 1);
              const barWidth = `${Math.max(5, intensity * 100)}%`;
              return (
                <div key={i} className="flex items-center gap-3 text-xs">
                  <div className="w-32 text-white/80 truncate">{t.tier}</div>
                  <div className="flex-1 bg-white/5 h-2 relative overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-[#00F0FF] to-[#FF0099]" style={{ width: barWidth }} />
                  </div>
                  <div className="font-mono text-white/60 min-w-[100px] text-right">{t.odds_text}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Intelligence Panel — BLACK-BOXED. Internal engine hidden from users by design. */}

      {/* Chase Cards */}
      <div className="bg-[#0a0a0a] border border-[#27272a] p-5" data-testid="chase-cards">
        <h3 className="font-heading text-sm text-white/60 tracking-widest mb-4 flex items-center gap-2">
          <Trophy className="w-4 h-4 text-[#FF0099]" /> CHASE CARDS
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {data.chase_cards.map((c, i) => {
            // Find matching market entry from verdict.chase_market
            const market = (v.chase_market || []).find((m) => m.name === c.name);
            const realSold = market?.ebay_sold_avg;
            return (
              <div key={i} className="bg-[#121212] border border-white/5 p-4 hover:border-[#FF0099] transition-colors">
                <div className="text-[9px] font-mono text-[#FF0099] uppercase mb-1">{c.rarity}</div>
                <h4 className="font-heading text-white text-sm leading-tight mb-2">{c.name}</h4>
                {realSold ? (
                  <div className="mb-1">
                    <div className="font-mono text-[#39FF14] text-base font-bold">${realSold.toFixed(0)}</div>
                    <div className="text-[9px] font-mono text-[#39FF14]/60">eBay sold avg ({market.ebay_sold_count})</div>
                  </div>
                ) : (
                  <div className="mb-1">
                    <div className="font-mono text-white/70 text-sm">{c.value}</div>
                    <div className="text-[9px] font-mono text-white/30">est. range</div>
                  </div>
                )}
                <p className="text-white/50 text-xs italic mt-1">{c.why}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* CTAs */}
      <div className="flex flex-col sm:flex-row gap-3 pt-2">
        <Link to="/predictor" className="flex-1" data-testid="cta-predictor">
          <button className="w-full bg-[#FF0099] text-white font-heading tracking-widest h-14 hover:bg-[#FF0099]/90">
            🎲 SIMULATE A RIP →
          </button>
        </Link>
        <Link to="/case" className="flex-1" data-testid="cta-case">
          <button className="w-full bg-white/5 border border-white/20 text-white font-heading tracking-widest h-14 hover:border-[#39FF14] hover:text-[#39FF14]">
            📦 LOG TO MY DISPLAY CASE →
          </button>
        </Link>
      </div>
    </div>
  );
}
