import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import Navbar from '../components/Navbar';
import HotPacksFeed from '../components/HotPacksFeed';
import { Button } from '@/components/ui/button';
import { Brain, ArrowRight, Sparkles, Dice5, Layers, Lock, Zap, ShoppingBag, TrendingUp, Database, Eye } from 'lucide-react';
import { colorizeWords } from '../lib/colorize';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ACCENT = '#39FF14'; // bright green — user's accent of choice

// Random color assignments computed ONCE at module load → shuffles on every refresh
const HERO_TITLE_WORDS = ['KNOW', 'BEFORE', 'YOU', 'RIP.'];
const HERO_TITLE_COLORS = colorizeWords(HERO_TITLE_WORDS, /* keepWhite */ 2);
const ANALYZE_WORDS = ['ANALYZE', 'NOW'];
const ANALYZE_COLORS = colorizeWords(ANALYZE_WORDS, /* keepWhite */ 0);

export default function Landing() {
  const { user } = useAuth();
  const [topPacks, setTopPacks] = useState([]);

  // Fetch top recommended packs (highest-rated by analyzer)
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/analyzer/packs`);
        if (cancel) return;
        // Take first 3 — they're the curated featured packs
        setTopPacks((r.data?.packs || []).slice(0, 3));
      } catch {
        /* ignore — feed below still renders */
      }
    })();
    return () => { cancel = true; };
  }, []);

  const sideTools = [
    {
      icon: <Dice5 className="w-5 h-5" />,
      title: 'PACK PREDICTOR',
      tagline: 'Simulate the rip',
      desc: 'Animated card reveals show what a rip could look like before you commit.',
      link: '/predictor',
      color: '#FF0099',
    },
    {
      icon: <Layers className="w-5 h-5" />,
      title: 'DISPLAY CASE',
      tagline: 'Log every rip',
      desc: 'Your private binder. Track every pull, share what you want, hide the rest.',
      link: '/case',
      color: '#00F0FF',
      featured: true,
    },
    {
      icon: <ShoppingBag className="w-5 h-5" />,
      title: 'MARKETPLACE',
      tagline: 'Buy · Sell · Trade',
      desc: 'P2P card market with Cash App. Public binder = your storefront.',
      link: '/marketplace',
      color: ACCENT,
    },
  ];

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />

      {/* ───────────────────────── ANALYZER HERO ───────────────────────── */}
      <section className="relative pt-20 pb-10 px-4 overflow-hidden">
        {/* glowing orbs */}
        <div className="absolute inset-0 opacity-40 pointer-events-none">
          <div className="absolute top-0 left-1/3 w-[600px] h-[600px] rounded-full blur-[180px]" style={{ background: ACCENT, opacity: 0.18 }} />
          <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[#00F0FF] rounded-full blur-[160px] opacity-20" />
          <div className="absolute top-1/3 left-0 w-80 h-80 bg-[#FF0099] rounded-full blur-[140px] opacity-15" />
        </div>

        <div className="max-w-6xl mx-auto relative z-10 text-center">
          {/* Tag-strip */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 mb-6 border" style={{ background: `${ACCENT}10`, borderColor: `${ACCENT}55` }} data-testid="hero-tagline">
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: ACCENT }} />
            <span className="font-mono text-[11px] tracking-[0.3em]" style={{ color: ACCENT }}>// INSTANT PACK VERDICTS</span>
          </div>

          {/* Headline: KNOW BEFORE YOU RIP. */}
          <h1
            className="font-heading font-black uppercase text-white leading-none tracking-tighter mb-4 text-5xl sm:text-7xl lg:text-[7.5rem]"
            data-testid="hero-headline"
          >
            {HERO_TITLE_WORDS.map((word, i) => {
              const color = HERO_TITLE_COLORS[i];
              const lineBreakAfterSecondWord = i === 1; // "WHAT SHOULD" / "I RIP TODAY?"
              return (
                <span key={`${word}-${i}`}>
                  <span
                    data-testid={`hero-word-${i}`}
                    style={
                      color
                        ? { color, textShadow: `0 0 40px ${color}66` }
                        : { color: '#FFFFFF' }
                    }
                  >
                    {word}
                  </span>
                  {lineBreakAfterSecondWord ? <br /> : i < HERO_TITLE_WORDS.length - 1 ? ' ' : null}
                </span>
              );
            })}
          </h1>

          <p className="text-white/60 text-base sm:text-xl max-w-2xl mx-auto mb-10 font-body leading-relaxed">
            Stop buying blind. Drop any pack, box, or card into the Analyzer and get an instant, market-verified verdict before you pull the trigger.
          </p>

          {/* THE BUTTON — circular logo with ANALYZE NOW arcing OUTSIDE (clear air vs RIP lettering) */}
          <div className="flex flex-col items-center mb-10">
            <Link
              to="/analyzer"
              data-testid="hero-analyze-btn"
              className="group relative inline-flex items-center justify-center w-[17.5rem] h-[17.5rem] sm:w-[21.5rem] sm:h-[21.5rem]"
              aria-label="Analyze a pack"
            >
              {/* Tri-color expanding wave rings — green + cyan + pink, all visible at different radii */}
              <span className="ring-wave ring-wave-green" style={{ inset: '1.6rem' }} />
              <span className="ring-wave ring-wave-cyan" style={{ inset: '1.6rem' }} />
              <span className="ring-wave ring-wave-pink" style={{ inset: '1.6rem' }} />
              {/* Stationary outer glow — tri-color radial, keyed to logo circle */}
              <span
                className="absolute rounded-full animate-pulse-glow opacity-90 pointer-events-none"
                style={{
                  inset: '1.35rem',
                  boxShadow:
                    '0 0 40px #39FF14cc, 0 0 80px #00F0FF66, 0 0 110px #FF009955',
                }}
              />

              {/* Curved "ANALYZE NOW" on the OUTSIDE of the logo circle — clear air above RIP */}
              <svg
                className="absolute inset-0 w-full h-full pointer-events-none overflow-visible"
                viewBox="0 0 280 280"
                aria-hidden="true"
                data-testid="analyze-now-arc"
              >
                <defs>
                  {/* Radius ~128 vs logo circle ~100 → ~28px clear air between arc baseline and green ring */}
                  <path
                    id="analyze-now-arc-path"
                    d="M 40 148 A 128 128 0 0 1 240 148"
                    fill="none"
                  />
                  <filter id="analyze-now-glow" x="-40%" y="-40%" width="180%" height="180%">
                    <feGaussianBlur stdDeviation="2.4" result="b" />
                    <feMerge>
                      <feMergeNode in="b" />
                      <feMergeNode in="b" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                <text
                  filter="url(#analyze-now-glow)"
                  fontSize="22"
                  fontWeight="900"
                  letterSpacing="4"
                  fontFamily="var(--font-heading, 'Orbitron', sans-serif)"
                  style={{ textTransform: 'uppercase' }}
                >
                  <textPath href="#analyze-now-arc-path" startOffset="50%" textAnchor="middle">
                    {ANALYZE_WORDS.map((w, i) => (
                      <tspan
                        key={`${w}-${i}`}
                        fill={ANALYZE_COLORS[i] || '#FFFFFF'}
                        data-testid={`analyze-word-${i}`}
                      >
                        {i === 0 ? w : ` ${w}`}
                      </tspan>
                    ))}
                  </textPath>
                </text>
              </svg>

              {/* Logo circle — clipped tight to green ring; no overlay text on RIP N' FLIP */}
              <span
                className="relative z-[1] flex items-center justify-center w-52 h-52 sm:w-64 sm:h-64 rounded-full overflow-hidden bg-transparent transition-transform group-hover:scale-105"
                style={{
                  boxShadow: `0 0 50px ${ACCENT}aa`,
                }}
              >
                <img
                  src="/logo.png"
                  alt="Rip N' Flip — Analyze a Pack"
                  className="w-full h-full object-cover block"
                  draggable={false}
                />
              </span>
            </Link>

            {/* "START LOGGING" CTA button under the logo */}
            <Link
              to={user ? '/analyzer' : '/register'}
              data-testid="hero-start-logging-btn"
              className="mt-6 inline-flex items-center gap-2 bg-[#39FF14] text-black font-heading font-black tracking-[0.28em] uppercase text-sm sm:text-base px-8 py-3.5 hover:opacity-90 transition"
              style={{ boxShadow: '0 0 30px #39FF1499' }}
            >
              START LOGGING <ArrowRight className="w-4 h-4" />
            </Link>

            <div className="flex items-center gap-3 mt-4 text-[11px] font-mono tracking-widest text-white/40 uppercase flex-wrap justify-center">
              <span className="flex items-center gap-1"><span className="w-1 h-1 rounded-full bg-[#39FF14]" /> Live market comps</span>
              <span className="text-white/20">·</span>
              <span>DUB / MID / TRASH</span>
            </div>
          </div>

          {/* Top recommended packs preview — Mini Analyzer Cards */}
          {topPacks.length > 0 && (
            <div data-testid="hero-recommended-packs" className="max-w-5xl mx-auto">
              <div className="flex items-center justify-between px-1 mb-3">
                <span className="font-mono text-[11px] tracking-[0.3em] text-white/50 uppercase">// TOP PICKS RIGHT NOW</span>
                <Link to="/analyzer" className="text-[11px] font-mono uppercase tracking-widest hover:text-white" style={{ color: ACCENT }}>SEE ALL →</Link>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {topPacks.map((p) => (
                  <Link
                    key={p.pack_id}
                    to={`/analyzer?pack=${p.pack_id}`}
                    data-testid={`hero-pack-${p.pack_id}`}
                    className="text-left bg-[#0a0a0a] border border-[#27272a] hover:border-[#39FF14] p-4 transition-all group"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <span className="text-[9px] font-mono tracking-widest text-white/50 uppercase px-1.5 py-0.5 bg-white/5 border border-white/10">
                        {p.sport}
                      </span>
                      <span className="text-[9px] font-mono text-[#FF0099]">{p.badge || 'HOT'}</span>
                    </div>
                    <div className="font-heading text-lg text-white tracking-tight leading-tight mb-1">{p.name}</div>
                    <div className="text-white/50 text-xs mb-3 line-clamp-1">{p.tagline}</div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[#00F0FF] text-sm">${p.retail_price}</span>
                      <span className="text-[10px] font-mono uppercase tracking-widest opacity-0 group-hover:opacity-100 transition" style={{ color: ACCENT }}>
                        ANALYZE →
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ─────────── HOT PACKS LIVE FEED ─────────── */}
      <HotPacksFeed />

      {/* ─────────── SECONDARY TOOLS — smaller, below ─────────── */}
      <section className="py-12 px-4 border-t border-white/5">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-end justify-between mb-6 flex-wrap gap-3">
            <h2 className="font-heading text-2xl sm:text-3xl font-black text-white uppercase tracking-tight">
              MORE TOOLS <span className="text-white/40 text-base font-normal">/ for the obsessed</span>
            </h2>
            <span className="text-[11px] font-mono uppercase tracking-widest text-white/40">// stack &apos;em up</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {sideTools.map((t) => (
              <Link
                key={t.title}
                to={t.link}
                data-testid={`tool-card-${t.title.toLowerCase().replace(/\s+/g, '-')}`}
                className={`group bg-[#0a0a0a] border p-5 transition-all ${t.featured ? 'border-[#00F0FF]/40' : 'border-[#27272a] hover:border-white/30'}`}
              >
                <div className="flex items-center gap-2 mb-3">
                  <span style={{ color: t.color }}>{t.icon}</span>
                  <span className="font-heading text-base text-white tracking-widest">{t.title}</span>
                  {t.featured && (
                    <span className="ml-auto text-[8px] font-mono px-1.5 py-0.5 bg-[#00F0FF]/15 text-[#00F0FF] border border-[#00F0FF]/30 tracking-widest">
                      POPULAR
                    </span>
                  )}
                </div>
                <p className="text-xs italic mb-1.5" style={{ color: t.color }}>{t.tagline}</p>
                <p className="text-white/55 text-sm leading-snug mb-3">{t.desc}</p>
                <div className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest opacity-50 group-hover:opacity-100 transition" style={{ color: t.color }}>
                  OPEN <ArrowRight className="w-3 h-3" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ─────────── PUBLIC BINDER GALLERY PEEK ─────────── */}
      <section className="py-10 px-4 border-t border-white/5">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-center">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Eye className="w-4 h-4 text-[#00F0FF]" />
                <span className="font-mono text-[10px] tracking-[0.3em] text-[#00F0FF] uppercase">// SOCIAL BINDER</span>
              </div>
              <h2 className="font-heading text-3xl sm:text-4xl font-black text-white uppercase tracking-tight leading-tight mb-3">
                Show off the cards.<br />
                <span className="text-[#00F0FF]">Hide</span> the source pack.
              </h2>
              <p className="text-white/60 text-sm sm:text-base leading-relaxed mb-5">
                Your binder is your marketplace storefront. Public viewers see your hits — they don&apos;t see which pack you pulled them from. Thumbs-up the heaters. Buy what&apos;s listed.
              </p>
              <Link to="/binders" data-testid="public-gallery-btn">
                <Button className="bg-[#00F0FF] text-black hover:bg-[#00F0FF]/90 font-heading tracking-widest px-6 py-5">
                  BROWSE PUBLIC BINDERS <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[1,2,3,4,5,6].map((i) => (
                <div
                  key={i}
                  className={`aspect-[3/4] border ${i === 3 ? 'border-[#FF0099]/40' : 'border-white/10'} bg-gradient-to-br from-white/5 to-transparent flex items-end p-2 relative overflow-hidden`}
                >
                  <span className="text-[8px] font-mono text-white/30 uppercase tracking-widest">card #{i.toString().padStart(3, '0')}</span>
                  {i === 3 && (
                    <span className="absolute top-1 right-1 text-[8px] font-mono text-[#FF0099]">🔥{Math.floor(Math.random()*40)+10}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─────────── PRO TIER PROMO ─────────── */}
      <section className="py-14 px-4 border-t border-white/5">
        <div className="max-w-5xl mx-auto bg-gradient-to-br from-[#FF0099]/10 via-[#0a0a0a] to-[#00F0FF]/10 border border-[#FF0099]/30 p-8 sm:p-12 relative overflow-hidden" data-testid="pro-tier-promo">
          <div className="absolute -top-20 -right-20 w-60 h-60 bg-[#FF0099] rounded-full blur-[100px] opacity-30" />
          <div className="relative z-10">
            <span className="inline-block text-[#FF0099] font-mono text-xs tracking-widest mb-3">// RIP N&apos; FLIP PRO</span>
            <h2 className="font-heading text-3xl sm:text-5xl font-black text-white uppercase tracking-tight mb-4">
              UNLOCK THE FULL VAULT — <span className="text-[#FF0099]">$3.99/mo</span>
            </h2>
            <ul className="space-y-2 text-white/70 mb-8 text-sm sm:text-base">
              <li className="flex items-start gap-2"><span className="text-[#FF0099] mt-1">▶</span> Unlimited pack slots in your Display Case</li>
              <li className="flex items-start gap-2"><span className="text-[#FF0099] mt-1">▶</span> 5 Predictor rips per day (vs 2 free)</li>
              <li className="flex items-start gap-2"><span className="text-[#FF0099] mt-1">▶</span> Sell on the Marketplace + list-from-binder one-tap</li>
              <li className="flex items-start gap-2"><span className="text-[#FF0099] mt-1">▶</span> Bold pro graphics, animated reveals, exclusive themes</li>
              <li className="flex items-start gap-2"><span className="text-[#FF0099] mt-1">▶</span> 10-day free trial, cancel anytime</li>
            </ul>
            <Link to={user ? '/vault' : '/register'} data-testid="pro-cta-btn">
              <Button className="bg-[#FF0099] text-white hover:bg-[#FF0099]/90 font-heading tracking-wider px-8 py-5">
                GO PRO — $3.99/mo
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* CTA */}
      {!user && (
        <section className="py-14 px-4 border-t border-white/5">
          <div className="max-w-3xl mx-auto text-center">
            <h2 className="font-heading text-3xl sm:text-5xl font-black text-white uppercase mb-4 tracking-tight">
              READY TO <span style={{ color: ACCENT }}>RIP</span>?
            </h2>
            <p className="text-white/60 text-base sm:text-lg mb-7">
              Free to join. Every pack you log makes everyone&apos;s verdicts sharper.
            </p>
            <Link to="/register" data-testid="cta-join-btn">
              <Button
                className="text-black hover:opacity-90 text-lg px-12 py-6 font-heading tracking-widest"
                style={{ background: ACCENT }}
              >
                JOIN THE HUNT
              </Button>
            </Link>
          </div>
        </section>
      )}

      {/* FOOTER */}
      <footer className="py-8 px-4 border-t border-white/10 bg-[#0a0a0a]">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
          <Link to="/" className="flex items-center gap-2" data-testid="footer-logo">
            <img src="/logo.png" alt="Rip N' Flip" className="w-10 h-10 object-contain" />
            <span className="sr-only">Rip N&apos; Flip</span>
          </Link>
          <div className="flex items-center gap-6 text-white/40">
            <Link to="/analyzer" className="hover:text-white transition">Analyzer</Link>
            <Link to="/predictor" className="hover:text-white transition">Predictor</Link>
            <Link to="/case" className="hover:text-white transition">Binder</Link>
            <Link to="/marketplace" className="hover:text-white transition">Market</Link>
          </div>
          <span className="text-white/30 font-mono text-xs">© 2026 Rip N&apos; Flip · Rip. Chase. Flip. Repeat.</span>
        </div>
      </footer>
    </div>
  );
}
