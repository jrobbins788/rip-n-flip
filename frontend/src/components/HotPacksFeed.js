import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { TrendingUp, Flame, ArrowUpRight, Loader2, Zap } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const sportColors = {
  NBA: 'border-red-500/40 bg-red-600/10 text-red-300',
  NFL: 'border-blue-500/40 bg-blue-600/10 text-blue-300',
  MLB: 'border-indigo-500/40 bg-indigo-600/10 text-indigo-300',
  NHL: 'border-gray-500/40 bg-gray-600/10 text-gray-200',
  Soccer: 'border-purple-500/40 bg-purple-600/10 text-purple-300',
};

/**
 * "What's Hot Right Now" homepage feed.
 * Pulls curated hot packs from /api/hot-packs and live eBay prices for each.
 */
export default function HotPacksFeed() {
  const [packs, setPacks] = useState([]);
  const [prices, setPrices] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/hot-packs`);
        const list = r.data?.packs || [];
        if (cancelled) return;
        setPacks(list);
        setLoading(false);
        // fetch prices in parallel; update as they arrive
        list.forEach((p) => {
          axios
            .get(`${API}/packs/price`, { params: { q: p.name } })
            .then((res) => !cancelled && setPrices((prev) => ({ ...prev, [p.pack_id]: res.data })))
            .catch(() => !cancelled && setPrices((prev) => ({ ...prev, [p.pack_id]: { error: true } })));
        });
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="py-16 px-4" data-testid="hot-packs-section">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 bg-[#FF0099]/10 border border-[#FF0099]/40 px-3 py-1 mb-3">
              <Flame className="w-4 h-4 text-[#FF0099]" />
              <span className="text-[#FF0099] font-mono text-xs tracking-widest">LIVE FEED</span>
            </div>
            <h2 className="font-heading text-4xl sm:text-5xl font-black text-white uppercase tracking-tight">
              WHAT'S <span className="text-[#FF0099]">HOT</span> <span className="text-white/60 text-3xl sm:text-4xl">RIGHT NOW</span>
            </h2>
            <p className="text-white/50 mt-2 text-sm sm:text-base">
              Top trending packs ranked by hype. Live eBay prices update as you scroll.
            </p>
          </div>
          <Link
            to="/packs"
            data-testid="hot-packs-see-all"
            className="text-[#00F0FF] hover:text-white font-mono text-sm flex items-center gap-1 group"
          >
            SEE ALL PACKS <ArrowUpRight className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </Link>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-[#00F0FF] font-mono">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading the hype feed...
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {packs.slice(0, 8).map((p, i) => {
              const priceData = prices[p.pack_id];
              const hasLive = priceData && !priceData.error && priceData.count > 0;
              const isBlocked = priceData?.blocked;
              const sportClass = sportColors[p.sport] || 'border-white/20 bg-white/5 text-white/80';
              return (
                <Link
                  to={`/analyzer?pack=${p.pack_id}`}
                  key={p.pack_id}
                  data-testid={`hot-pack-${p.pack_id}`}
                  className="group relative bg-[#0a0a0a] border border-[#27272a] p-5 hover:border-[#FF0099] transition-all overflow-hidden"
                >
                  {/* Rank chip */}
                  <div className="absolute top-3 right-3 text-white/20 font-heading text-3xl font-black">
                    #{i + 1}
                  </div>
                  <div className={`inline-flex items-center text-[10px] font-mono px-2 py-0.5 border ${sportClass} mb-3`}>
                    {p.sport}
                  </div>
                  <h3 className="font-heading text-lg font-bold text-white leading-tight mb-1 pr-8">
                    {p.name}
                  </h3>
                  <p className="text-white/50 text-xs italic mb-3">{p.tagline}</p>

                  <div className="flex items-end justify-between mt-4 pt-3 border-t border-white/5">
                    <div>
                      <div className="text-[9px] text-white/40 font-mono uppercase">Live eBay Avg</div>
                      {priceData === undefined ? (
                        <div className="font-mono text-white/40 text-sm flex items-center gap-1">
                          <Loader2 className="w-3 h-3 animate-spin" /> ...
                        </div>
                      ) : hasLive ? (
                        <div className="font-mono text-[#39FF14] text-xl font-bold">${priceData.avg}</div>
                      ) : (
                        <div className="font-mono text-white/60 text-sm">~${p.retail_price}</div>
                      )}
                      {hasLive && (
                        <div className="text-[9px] text-white/30 font-mono">{priceData.count} listings</div>
                      )}
                      {isBlocked && (
                        <div className="text-[9px] text-yellow-400/70 font-mono">live data warming up</div>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-[#FF0099] tracking-wider">{p.badge}</span>
                  </div>

                  <div className="mt-3 flex items-center gap-1 text-[#00F0FF] text-xs font-mono opacity-0 group-hover:opacity-100 transition-opacity">
                    ANALYZE <Zap className="w-3 h-3" />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
