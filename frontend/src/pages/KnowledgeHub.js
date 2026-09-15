import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Minus, Star, Zap, Target, Award } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function KnowledgeHub() {
  const [knowledge, setKnowledge] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeSport, setActiveSport] = useState('NFL');

  const sports = ['NFL', 'NBA', 'MLB', 'NHL', 'Soccer'];

  useEffect(() => {
    fetchKnowledge();
  }, []);

  const fetchKnowledge = async () => {
    try {
      const response = await fetch(`${API}/knowledge/all`);
      const data = await response.json();
      setKnowledge(data);
    } catch (error) {
      console.error('Error fetching knowledge:', error);
    } finally {
      setLoading(false);
    }
  };

  const getTrendIcon = (trend) => {
    switch (trend) {
      case 'Rising':
        return <TrendingUp className="w-4 h-4 text-green-400" />;
      case 'Falling':
        return <TrendingDown className="w-4 h-4 text-red-400" />;
      default:
        return <Minus className="w-4 h-4 text-yellow-400" />;
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
          <div className="text-[#00F0FF] font-mono animate-pulse">LOADING DATA...</div>
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
            <div className="inline-flex items-center gap-2 bg-[#00F0FF]/10 border border-[#00F0FF]/30 px-4 py-2 mb-4">
              <Zap className="w-4 h-4 text-[#00F0FF]" />
              <span className="text-[#00F0FF] font-mono text-sm">COMMAND CENTER</span>
            </div>
            <h1 className="font-heading text-5xl sm:text-6xl font-bold text-white uppercase tracking-tight">
              KNOWLEDGE <span className="text-[#00F0FF]">HUB</span>
            </h1>
            <p className="text-white/50 mt-2">Your expert-curated guide to the best in sports cards</p>
          </div>

          {/* Sport Tabs */}
          <Tabs value={activeSport} onValueChange={setActiveSport} className="mb-8">
            <TabsList className="bg-[#0a0a0a] border border-[#27272a] p-1 h-auto flex-wrap">
              {sports.map((sport) => (
                <TabsTrigger
                  key={sport}
                  value={sport}
                  data-testid={`sport-tab-${sport.toLowerCase()}`}
                  className="font-heading text-lg tracking-wider data-[state=active]:bg-[#00F0FF] data-[state=active]:text-black px-6 py-2"
                >
                  {sport}
                </TabsTrigger>
              ))}
            </TabsList>

            {sports.map((sport) => (
              <TabsContent key={sport} value={sport} className="mt-8">
                {/* Best Packs for Sport */}
                <section className="mb-12">
                  <h2 className="font-heading text-2xl font-bold text-white mb-6 flex items-center gap-2">
                    <Target className="w-6 h-6 text-[#FF0099]" />
                    BEST PACKS TO RIP - {sport}
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {knowledge?.best_packs?.[sport]?.map((pack, i) => (
                      <div
                        key={i}
                        data-testid={`pack-card-${sport.toLowerCase()}-${i}`}
                        className="bg-[#0a0a0a] border border-[#27272a] p-6 hover:border-[#00F0FF] transition-all card-holographic"
                      >
                        <div className="flex justify-between items-start mb-3">
                          <h3 className="font-heading text-xl font-bold text-white">{pack.name}</h3>
                          <span className="font-mono text-[#00F0FF] text-lg">{pack.price_range}</span>
                        </div>
                        <p className="text-white/60 text-sm mb-3">{pack.why}</p>
                        <div className="mb-3">
                          <span className="text-[#FF0099] text-xs font-mono">HOT PULLS:</span>
                          <p className="text-white/80 text-sm">{pack.hot_pulls}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {pack.retailer_links?.map((retailer, j) => (
                            <Badge key={j} variant="outline" className="border-[#27272a] text-white/60 text-xs">
                              {retailer}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </TabsContent>
            ))}
          </Tabs>

          {/* Best Blasters - All Sports */}
          <section className="mb-12">
            <h2 className="font-heading text-2xl font-bold text-white mb-6 flex items-center gap-2">
              <Star className="w-6 h-6 text-[#39FF14]" />
              TOP BLASTERS TO GRAB
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {knowledge?.best_blasters?.map((blaster, i) => (
                <div
                  key={i}
                  data-testid={`blaster-card-${i}`}
                  className="bg-[#0a0a0a] border border-[#27272a] p-5 hover:border-[#39FF14] transition-all"
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-heading text-lg font-bold text-white">{blaster.name}</h3>
                    <Badge className={getSportColor(blaster.sport)}>{blaster.sport}</Badge>
                  </div>
                  <div className="flex items-center gap-4 mb-2">
                    <span className="font-mono text-[#39FF14]">{blaster.price}</span>
                    <span className="text-white/40 text-sm">{blaster.card_count} packs</span>
                  </div>
                  <p className="text-white/60 text-sm">{blaster.best_for}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Hottest Cards */}
          <section className="mb-12">
            <h2 className="font-heading text-2xl font-bold text-white mb-6 flex items-center gap-2">
              <TrendingUp className="w-6 h-6 text-[#00F0FF]" />
              HOTTEST CARDS RIGHT NOW
            </h2>
            <div className="bg-[#0a0a0a] border border-[#27272a] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[#27272a]">
                      <th className="text-left p-4 font-heading text-[#00F0FF] tracking-wider">CARD</th>
                      <th className="text-left p-4 font-heading text-[#00F0FF] tracking-wider">SPORT</th>
                      <th className="text-left p-4 font-heading text-[#00F0FF] tracking-wider">PRICE</th>
                      <th className="text-left p-4 font-heading text-[#00F0FF] tracking-wider">WHY HOT</th>
                      <th className="text-left p-4 font-heading text-[#00F0FF] tracking-wider">TREND</th>
                    </tr>
                  </thead>
                  <tbody>
                    {knowledge?.hottest_cards?.map((card, i) => (
                      <tr key={i} className="border-b border-[#27272a] hover:bg-[#121212]" data-testid={`hot-card-row-${i}`}>
                        <td className="p-4 font-medium text-white">{card.name}</td>
                        <td className="p-4">
                          <Badge className={getSportColor(card.sport)}>{card.sport}</Badge>
                        </td>
                        <td className="p-4 font-mono text-[#00F0FF]">{card.price_range}</td>
                        <td className="p-4 text-white/60 text-sm">{card.why}</td>
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            {getTrendIcon(card.trend)}
                            <span className={card.trend === 'Rising' ? 'text-green-400' : card.trend === 'Falling' ? 'text-red-400' : 'text-yellow-400'}>
                              {card.trend}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* Best Autos */}
          <section>
            <h2 className="font-heading text-2xl font-bold text-white mb-6 flex items-center gap-2">
              <Award className="w-6 h-6 text-[#FF0099]" />
              PREMIUM AUTOS TO CHASE
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {knowledge?.best_autos?.map((auto, i) => (
                <div
                  key={i}
                  data-testid={`auto-card-${i}`}
                  className="bg-[#0a0a0a] border border-[#27272a] p-5 hover:border-[#FF0099] transition-all card-shine"
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-heading text-lg font-bold text-white">{auto.name}</h3>
                    <Badge className={getSportColor(auto.sport)}>{auto.sport}</Badge>
                  </div>
                  <div className="mb-2">
                    <span className="font-mono text-[#FF0099] text-lg">{auto.price_range}</span>
                  </div>
                  <p className="text-white/60 text-sm mb-2">{auto.why}</p>
                  <Badge variant="outline" className="border-[#FF0099]/30 text-[#FF0099] text-xs">
                    {auto.rarity}
                  </Badge>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
