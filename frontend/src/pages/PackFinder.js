import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Package, ExternalLink, DollarSign, Store, Zap } from 'lucide-react';
import LivePriceWidget from '../components/LivePriceWidget';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function PackFinder() {
  const [packs, setPacks] = useState({});
  const [retailers, setRetailers] = useState({});
  const [blasters, setBlasters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeSport, setActiveSport] = useState('NFL');

  const sports = ['NFL', 'NBA', 'MLB', 'NHL', 'Soccer'];

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [packsRes, retailersRes, blastersRes] = await Promise.all([
        fetch(`${API}/knowledge/packs`),
        fetch(`${API}/knowledge/retailers`),
        fetch(`${API}/knowledge/blasters`)
      ]);
      
      setPacks(await packsRes.json());
      setRetailers(await retailersRes.json());
      setBlasters(await blastersRes.json());
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getSportColor = (sport) => {
    const colors = {
      NFL: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
      NBA: 'bg-red-600/20 text-red-400 border-red-500/30',
      MLB: 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30',
      NHL: 'bg-gray-600/20 text-gray-300 border-gray-500/30',
      Soccer: 'bg-purple-600/20 text-purple-400 border-purple-500/30'
    };
    return colors[sport] || colors.NFL;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="pt-24 flex items-center justify-center">
          <div className="text-[#00F0FF] font-mono animate-pulse">SCANNING RETAILERS...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      
      <main className="pt-24 pb-12 px-4">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-12">
            <div className="inline-flex items-center gap-2 bg-[#39FF14]/10 border border-[#39FF14]/30 px-4 py-2 mb-4">
              <Package className="w-4 h-4 text-[#39FF14]" />
              <span className="text-[#39FF14] font-mono text-sm">PACK SCANNER ONLINE</span>
            </div>
            <h1 className="font-heading text-5xl sm:text-6xl font-bold text-white uppercase tracking-tight">
              PACK <span className="text-[#39FF14]">FINDER</span>
            </h1>
            <p className="text-white/50 mt-2">Compare prices across retailers. Find the best deals.</p>
          </div>

          {/* Retailer Quick Links */}
          <section className="mb-12">
            <h2 className="font-heading text-xl font-bold text-white mb-4 flex items-center gap-2">
              <Store className="w-5 h-5 text-[#00F0FF]" />
              TRUSTED RETAILERS
            </h2>
            <div className="flex flex-wrap gap-3">
              {Object.entries(retailers).map(([name, url]) => (
                <a
                  key={name}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid={`retailer-link-${name.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
                  className="inline-flex items-center gap-2 bg-[#0a0a0a] border border-[#27272a] px-4 py-2 hover:border-[#00F0FF] transition-all group"
                >
                  <span className="text-white group-hover:text-[#00F0FF]">{name}</span>
                  <ExternalLink className="w-4 h-4 text-white/40 group-hover:text-[#00F0FF]" />
                </a>
              ))}
            </div>
          </section>

          {/* Sport Tabs */}
          <Tabs value={activeSport} onValueChange={setActiveSport} className="mb-8">
            <TabsList className="bg-[#0a0a0a] border border-[#27272a] p-1 h-auto flex-wrap">
              {sports.map((sport) => (
                <TabsTrigger
                  key={sport}
                  value={sport}
                  data-testid={`pack-sport-tab-${sport.toLowerCase()}`}
                  className="font-heading text-lg tracking-wider data-[state=active]:bg-[#39FF14] data-[state=active]:text-black px-6 py-2"
                >
                  {sport}
                </TabsTrigger>
              ))}
            </TabsList>

            {sports.map((sport) => (
              <TabsContent key={sport} value={sport} className="mt-8">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {packs[sport]?.map((pack, i) => (
                    <div
                      key={i}
                      data-testid={`pack-finder-card-${sport.toLowerCase()}-${i}`}
                      className="bg-[#0a0a0a] border border-[#27272a] overflow-hidden hover:border-[#39FF14] transition-all card-holographic"
                    >
                      <div className="p-6">
                        <div className="flex justify-between items-start mb-4">
                          <div>
                            <h3 className="font-heading text-2xl font-bold text-white">{pack.name}</h3>
                            <p className="text-white/50 text-sm mt-1">{pack.why}</p>
                          </div>
                          <Badge className={getSportColor(sport)}>{sport}</Badge>
                        </div>
                        
                        <div className="bg-[#121212] p-4 mb-4">
                          <div className="flex items-center gap-2 mb-2">
                            <DollarSign className="w-5 h-5 text-[#39FF14]" />
                            <span className="font-mono text-2xl text-[#39FF14]">{pack.price_range}</span>
                          </div>
                          <p className="text-white/40 text-xs">Price varies by retailer</p>
                        </div>

                        <div className="mb-4">
                          <span className="text-[#FF0099] text-xs font-mono block mb-1">TOP PULLS:</span>
                          <p className="text-white/80 text-sm">{pack.hot_pulls}</p>
                        </div>

                        <LivePriceWidget query={pack.name} label="Live eBay Prices" />

                        <div className="pt-4 border-t border-[#27272a]">
                          <span className="text-white/40 text-xs font-mono block mb-3">BUY FROM:</span>
                          <div className="flex flex-wrap gap-2">
                            {pack.retailer_links?.map((retailer, j) => {
                              const url = retailers[retailer];
                              return url ? (
                                <a
                                  key={j}
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 bg-[#121212] border border-[#27272a] px-3 py-2 hover:border-[#39FF14] hover:text-[#39FF14] transition-all text-white text-sm"
                                >
                                  {retailer}
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              ) : (
                                <span key={j} className="text-white/40 text-sm px-3 py-2 bg-[#121212] border border-[#27272a]">
                                  {retailer}
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>
            ))}
          </Tabs>

          {/* Blasters Section */}
          <section className="mt-16">
            <h2 className="font-heading text-3xl font-bold text-white mb-6 flex items-center gap-2">
              <Zap className="w-7 h-7 text-[#FF0099]" />
              BEST BLASTERS - ALL SPORTS
            </h2>
            <p className="text-white/50 mb-8">Budget-friendly retail boxes perfect for casual ripping</p>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {blasters.map((blaster, i) => (
                <div
                  key={i}
                  data-testid={`blaster-finder-${i}`}
                  className="bg-[#0a0a0a] border border-[#27272a] p-5 hover:border-[#FF0099] transition-all"
                >
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="font-heading text-lg font-bold text-white">{blaster.name}</h3>
                    <Badge className={getSportColor(blaster.sport)}>{blaster.sport}</Badge>
                  </div>
                  <div className="flex items-center gap-4 mb-3">
                    <span className="font-mono text-xl text-[#FF0099]">{blaster.price}</span>
                    <span className="text-white/40 text-sm">{blaster.card_count} packs</span>
                  </div>
                  <p className="text-white/60 text-sm mb-4">{blaster.best_for}</p>
                  <LivePriceWidget query={blaster.name} label="Live eBay" />
                  <div className="flex gap-2 mt-3">
                    <a
                      href={retailers['Target']}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 text-center bg-[#121212] border border-[#27272a] px-3 py-2 hover:border-[#FF0099] hover:text-[#FF0099] transition-all text-white text-sm"
                    >
                      Target
                    </a>
                    <a
                      href={retailers['Walmart']}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 text-center bg-[#121212] border border-[#27272a] px-3 py-2 hover:border-[#FF0099] hover:text-[#FF0099] transition-all text-white text-sm"
                    >
                      Walmart
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
