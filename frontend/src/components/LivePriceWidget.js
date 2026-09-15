import { useEffect, useState } from 'react';
import axios from 'axios';
import { TrendingUp, ExternalLink, Loader2, RefreshCw } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Live eBay price widget. Shows avg / min / max for a query.
 * Expand to see top listings linking out to eBay.
 */
export default function LivePriceWidget({ query, label }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API}/packs/price`, { params: { q: query, refresh } });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Price check failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  return (
    <div
      className="bg-[#121212] border border-[#27272a] p-3 mt-3"
      data-testid={`price-widget-${query.toLowerCase().replace(/[^a-z0-9]/g, '-').slice(0, 40)}`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-[#39FF14]" />
          <span className="text-[11px] font-mono text-white/60 uppercase tracking-wider">
            {label || 'Live eBay'}
          </span>
          {data?.cached && (
            <span className="text-[9px] font-mono text-white/30 uppercase">cached</span>
          )}
        </div>
        <button
          onClick={() => load(true)}
          disabled={loading}
          className="text-white/40 hover:text-[#39FF14] disabled:opacity-30"
          aria-label="Refresh price"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && (
        <div className="flex items-center gap-2 text-white/40 text-xs">
          <Loader2 className="w-3 h-3 animate-spin" />
          Scanning eBay...
        </div>
      )}
      {error && <div className="text-xs text-red-400">{error}</div>}
      {data && data.count > 0 && (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-[9px] text-white/40 uppercase">Low</div>
              <div className="font-mono text-white text-sm">${data.min}</div>
            </div>
            <div className="border-x border-white/5">
              <div className="text-[9px] text-white/40 uppercase">Avg</div>
              <div className="font-mono text-[#39FF14] text-base font-bold">${data.avg}</div>
            </div>
            <div>
              <div className="text-[9px] text-white/40 uppercase">High</div>
              <div className="font-mono text-white text-sm">${data.max}</div>
            </div>
          </div>
          <div className="text-[10px] text-white/40 mt-2 flex justify-between">
            <span>{data.count} listings</span>
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-[#00F0FF] hover:underline"
              data-testid="price-widget-toggle"
            >
              {expanded ? 'hide' : 'view listings'}
            </button>
          </div>
          {expanded && (
            <div className="mt-2 space-y-1 max-h-48 overflow-y-auto pr-1">
              {data.listings.slice(0, 6).map((l, i) => (
                <a
                  key={i}
                  href={l.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-[11px] bg-black/30 hover:bg-black/50 px-2 py-1.5 group"
                >
                  <span className="font-mono text-[#39FF14] min-w-[52px]">{l.price_text}</span>
                  <span className="text-white/70 truncate flex-1 group-hover:text-white">{l.title}</span>
                  <ExternalLink className="w-3 h-3 text-white/30 group-hover:text-[#00F0FF]" />
                </a>
              ))}
            </div>
          )}
        </>
      )}
      {data && data.count === 0 && data.blocked && (
        <div className="text-[11px] text-yellow-400/80">
          eBay rate-limited this request. Refreshes work once cooldown clears.
        </div>
      )}
      {data && data.count === 0 && !data.blocked && (
        <div className="text-xs text-white/40">No live listings found</div>
      )}
    </div>
  );
}
