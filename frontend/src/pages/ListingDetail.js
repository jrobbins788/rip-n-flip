import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { ArrowLeft, ShoppingCart, RefreshCcw, MessageCircle, User, CreditCard, Info, Shield, X, DollarSign, ExternalLink } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = BACKEND_URL + '/api';

const SPORT_COLORS = {
  NFL: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
  NBA: 'bg-red-600/20 text-red-400 border-red-500/30',
  MLB: 'bg-indigo-600/20 text-indigo-400 border-indigo-500/30',
  NHL: 'bg-gray-600/20 text-gray-300 border-gray-500/30',
  Soccer: 'bg-purple-600/20 text-purple-400 border-purple-500/30'
};

export default function ListingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [tradeModal, setTradeModal] = useState(null); // { trade_id, cashapp_url, total_amount, seller_cash_app_tag }
  const [initiatingTrade, setInitiatingTrade] = useState(false);

  const fetchListing = useCallback(async () => {
    try {
      const response = await fetch(API + '/listings/' + id);
      if (!response.ok) throw new Error('Listing not found');
      setListing(await response.json());
    } catch (err) {
      toast.error('Listing not found');
      navigate('/marketplace');
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => {
    fetchListing();
  }, [fetchListing]);

  const handleBuy = async () => {
    if (!user) { toast.error('Please login to purchase'); navigate('/login'); return; }
    if (listing.user_id === user.user_id) { toast.error("You can't buy your own listing"); return; }

    setPurchasing(true);
    try {
      const res = await fetch(API + '/payments/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ listing_id: listing.listing_id, origin_url: window.location.origin })
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Checkout failed');
      window.location.href = (await res.json()).url;
    } catch (err) {
      toast.error(err.message);
    } finally {
      setPurchasing(false);
    }
  };

  const handleSendMessage = async () => {
    if (!user) { toast.error('Please login'); return; }
    if (!message.trim()) { toast.error('Please enter a message'); return; }

    setSendingMessage(true);
    try {
      const res = await fetch(API + '/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ listing_id: listing.listing_id, receiver_id: listing.user_id, content: message })
      });
      if (!res.ok) throw new Error('Failed to send message');
      toast.success('Message sent!');
      setMessage('');
      setShowModal(false);
    } catch (err) {
      toast.error('Failed to send message');
    } finally {
      setSendingMessage(false);
    }
  };

  const handleCashAppTrade = async () => {
    if (!user) { toast.error('Please login to trade'); navigate('/login'); return; }
    if (listing.user_id === user.user_id) { toast.error("Can't trade with yourself"); return; }
    setInitiatingTrade(true);
    try {
      const res = await fetch(API + '/trades/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ listing_id: listing.listing_id })
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Trade failed');
      const trade = await res.json();
      setTradeModal(trade);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setInitiatingTrade(false);
    }
  };

  const markTradePaid = async () => {
    try {
      const res = await fetch(`${API}/trades/${tradeModal.trade_id}/mark-paid`, {
        method: 'POST',
        credentials: 'include'
      });
      if (!res.ok) throw new Error('Mark paid failed');
      toast.success("Marked as paid — seller will confirm receipt");
      setTradeModal(null);
      navigate('/vault');
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-[#050505]"><Navbar /><div className="pt-24 flex items-center justify-center"><div className="text-[#00F0FF] font-mono animate-pulse">LOADING...</div></div></div>;
  }

  if (!listing) return null;

  const platformFee = listing.price * 0.02;
  const totalPrice = listing.price + platformFee;
  const isOwner = user && listing.user_id === user.user_id;
  const sportColor = SPORT_COLORS[listing.sport] || SPORT_COLORS.NFL;

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
          <div className="bg-[#0a0a0a] border border-[#27272a] p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading text-xl text-white">Message Seller</h3>
              <button onClick={() => setShowModal(false)} className="text-white/50 hover:text-white"><X className="w-5 h-5" /></button>
            </div>
            <Textarea placeholder="Hi, I'm interested..." value={message} onChange={(e) => setMessage(e.target.value)} className="bg-[#121212] border-[#27272a] text-white min-h-[120px] mb-4" data-testid="message-input" />
            <Button onClick={handleSendMessage} disabled={sendingMessage} className="w-full bg-[#FF0099] text-white hover:bg-[#FF0099]/90" data-testid="send-message-btn">{sendingMessage ? 'Sending...' : 'Send Message'}</Button>
          </div>
        </div>
      )}
      {tradeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" data-testid="trade-modal">
          <div className="bg-[#0a0a0a] border border-[#39FF14]/40 p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading text-xl text-white">CASH APP TRADE</h3>
              <button onClick={() => setTradeModal(null)} className="text-white/50 hover:text-white"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3 text-sm">
              <div className="bg-[#121212] border border-[#27272a] p-4 space-y-2">
                <div className="flex justify-between"><span className="text-white/60">Card</span><span className="text-white font-mono text-xs truncate max-w-[180px]">{tradeModal.listing_title}</span></div>
                <div className="flex justify-between"><span className="text-white/60">Seller</span><span className="text-white">{tradeModal.seller_name}</span></div>
                <div className="flex justify-between"><span className="text-white/60">Cash App</span><span className="text-[#39FF14] font-mono">${tradeModal.seller_cash_app_tag}</span></div>
                <div className="flex justify-between pt-2 border-t border-white/10"><span className="text-white font-bold">Pay</span><span className="font-mono text-2xl text-[#39FF14]">${tradeModal.total_amount}</span></div>
              </div>
              <ol className="text-xs text-white/60 space-y-1 list-decimal list-inside">
                <li>Click below → opens Cash App with seller + amount pre-filled</li>
                <li>Send the payment in Cash App</li>
                <li>Come back & mark paid — seller confirms receipt</li>
              </ol>
              <a
                href={tradeModal.cashapp_url}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="cashapp-deeplink"
                className="w-full flex items-center justify-center gap-2 bg-[#00D632] text-black font-bold h-12 hover:bg-[#00D632]/90 transition"
              >
                <DollarSign className="w-5 h-5" /> PAY ${tradeModal.total_amount} ON CASH APP <ExternalLink className="w-4 h-4" />
              </a>
              <Button
                onClick={markTradePaid}
                variant="outline"
                data-testid="mark-paid-btn"
                className="w-full border-[#39FF14] text-[#39FF14] hover:bg-[#39FF14]/10"
              >
                I'VE SENT PAYMENT
              </Button>
              <p className="text-[10px] text-white/40 text-center">Trade ID: {tradeModal.trade_id}</p>
            </div>
          </div>
        </div>
      )}
      <main className="pt-24 pb-12 px-4">
        <div className="max-w-6xl mx-auto">
          <button onClick={() => navigate('/marketplace')} className="flex items-center gap-2 text-white/50 hover:text-white mb-6" data-testid="back-to-marketplace"><ArrowLeft className="w-5 h-5" /><span className="font-mono text-sm">BACK</span></button>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="aspect-[3/4] bg-[#0a0a0a] border border-[#27272a] overflow-hidden">
              {listing.images?.length > 0 ? <img src={listing.images[0]} alt={listing.title} className="w-full h-full object-contain" /> : <div className="w-full h-full flex items-center justify-center"><ShoppingCart className="w-24 h-24 text-white/10" /></div>}
            </div>
            <div className="space-y-6">
              <div>
                <div className="flex flex-wrap gap-2 mb-3">
                  <Badge className={sportColor}>{listing.sport}</Badge>
                  <Badge variant="outline" className="border-[#27272a] text-white/60">{listing.card_type}</Badge>
                  <Badge variant="outline" className="border-[#27272a] text-white/60">{listing.condition}</Badge>
                  {listing.is_tradeable && <Badge className="bg-[#39FF14]/20 text-[#39FF14] border border-[#39FF14]/30"><RefreshCcw className="w-3 h-3 mr-1" />Trade</Badge>}
                </div>
                <h1 className="font-heading text-3xl font-bold text-white">{listing.title}</h1>
              </div>
              <div className="space-y-2">
                <div className="flex gap-2"><span className="text-white/40 text-sm">Player:</span><span className="text-white">{listing.player_name}</span></div>
                {listing.team && <div className="flex gap-2"><span className="text-white/40 text-sm">Team:</span><span className="text-white">{listing.team}</span></div>}
                {listing.year && <div className="flex gap-2"><span className="text-white/40 text-sm">Year:</span><span className="text-white">{listing.year}</span></div>}
              </div>
              <div><h3 className="text-white/40 text-sm mb-2">Description</h3><p className="text-white/80">{listing.description}</p></div>
              <div className="bg-[#0a0a0a] border border-[#27272a] p-4 flex items-center gap-3"><div className="w-10 h-10 rounded-full bg-[#00F0FF]/20 border border-[#00F0FF]/50 flex items-center justify-center"><User className="w-5 h-5 text-[#00F0FF]" /></div><div><span className="text-white/40 text-xs">SELLER</span><p className="text-white font-medium">{listing.seller_name}</p></div></div>
              <div className="bg-[#0a0a0a] border border-[#27272a] p-6">
                <div className="space-y-3 mb-6">
                  <div className="flex justify-between"><span className="text-white/60">Card Price</span><span className="font-mono text-white">${listing.price.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-white/60 flex items-center gap-1">Fee (2%)<Info className="w-3 h-3" /></span><span className="font-mono text-white/60">${platformFee.toFixed(2)}</span></div>
                  <div className="border-t border-[#27272a] pt-3 flex justify-between"><span className="text-white font-bold">Total</span><span className="font-mono text-2xl text-[#00F0FF]">${totalPrice.toFixed(2)}</span></div>
                </div>
                {listing.status === 'sold' ? <div className="text-center py-4 bg-red-500/10 border border-red-500/30 text-red-400">Sold</div> : listing.status === 'pending' ? <div className="text-center py-4 bg-yellow-500/10 border border-yellow-500/30 text-yellow-400">Pending</div> : isOwner ? <div className="text-center py-4 bg-[#00F0FF]/10 border border-[#00F0FF]/30 text-[#00F0FF]">Your listing</div> : (
                  <div className="space-y-3">
                    <Button onClick={handleBuy} disabled={purchasing} className="w-full btn-tactical bg-[#00F0FF] text-black hover:bg-[#00F0FF]/90 h-14 font-heading tracking-wider text-lg" data-testid="buy-now-btn"><span className="flex items-center gap-2">{purchasing ? 'PROCESSING...' : <><CreditCard className="w-5 h-5" />BUY NOW</>}</span></Button>
                    {listing.seller_cash_app_tag && (
                      <Button onClick={handleCashAppTrade} disabled={initiatingTrade} className="w-full bg-[#00D632] text-black hover:bg-[#00D632]/90 h-12 font-heading tracking-wider" data-testid="cashapp-trade-btn">
                        <span className="flex items-center gap-2"><DollarSign className="w-5 h-5" />{initiatingTrade ? 'STARTING...' : `PAY WITH CASH APP ($${listing.seller_cash_app_tag})`}</span>
                      </Button>
                    )}
                    <Button onClick={() => setShowModal(true)} variant="outline" className="w-full border-[#FF0099] text-[#FF0099] hover:bg-[#FF0099]/10 h-12 font-heading tracking-wider" data-testid="contact-seller-btn"><span className="flex items-center gap-2"><MessageCircle className="w-5 h-5" />CONTACT</span></Button>
                  </div>
                )}
                <div className="mt-4 pt-4 border-t border-[#27272a]"><div className="flex items-center gap-2 text-white/40 text-xs mb-2"><Shield className="w-4 h-4" />Secure checkout:</div><div className="flex flex-wrap gap-2 text-white/60 text-xs"><span className="bg-[#121212] px-2 py-1">Card</span><span className="bg-[#121212] px-2 py-1">Afterpay</span><span className="bg-[#121212] px-2 py-1">Klarna</span></div></div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
