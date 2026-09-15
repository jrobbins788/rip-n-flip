import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { 
  User, Package, MessageCircle, Receipt, Settings, 
  Edit2, Trash2, RefreshCcw, ShoppingBag, DollarSign, Crown
} from 'lucide-react';
import SubscriptionPanel from '../components/SubscriptionPanel';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Profile() {
  const navigate = useNavigate();
  const { user, loading: authLoading, updateProfile, logout } = useAuth();
  const [listings, setListings] = useState([]);
  const [messages, setMessages] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cashAppTag, setCashAppTag] = useState('');
  const [editingCashApp, setEditingCashApp] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login');
      return;
    }
    if (user) {
      fetchUserData();
      setCashAppTag(user.cash_app_tag || '');
    }
  }, [user, authLoading]);

  const fetchUserData = async () => {
    try {
      const [listingsRes, messagesRes, transactionsRes, tradesRes] = await Promise.all([
        fetch(`${API}/my-listings`, { credentials: 'include' }),
        fetch(`${API}/messages`, { credentials: 'include' }),
        fetch(`${API}/my-transactions`, { credentials: 'include' }),
        fetch(`${API}/trades`, { credentials: 'include' }),
      ]);

      setListings(await listingsRes.json());
      setMessages(await messagesRes.json());
      setTransactions(await transactionsRes.json());
      setTrades(tradesRes.ok ? await tradesRes.json() : []);
    } catch (error) {
      console.error('Error fetching user data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Trade action dispatcher — buyer marks paid, seller confirms received, either cancels.
  // Action maps 1:1 to backend endpoint: POST /api/trades/{id}/{action}.
  const handleTradeAction = async (tradeId, action) => {
    if (action === 'cancel' && !window.confirm('Cancel this trade?')) return;
    try {
      const res = await fetch(`${API}/trades/${tradeId}/${action}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Trade action failed');
      }
      const labels = { 'mark-paid': 'Marked as paid', confirm: 'Trade confirmed', cancel: 'Trade canceled' };
      toast.success(labels[action] || 'Done');
      fetchUserData();
    } catch (e) {
      toast.error(e.message || 'Trade action failed');
    }
  };

  const handleDeleteListing = async (listingId) => {
    if (!window.confirm('Are you sure you want to delete this listing?')) return;
    
    try {
      const response = await fetch(`${API}/listings/${listingId}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      
      if (!response.ok) throw new Error('Failed to delete listing');
      
      setListings(prev => prev.filter(l => l.listing_id !== listingId));
      toast.success('Listing deleted');
    } catch (error) {
      toast.error('Failed to delete listing');
    }
  };

  const handleUpdateCashApp = async () => {
    try {
      await updateProfile({ cash_app_tag: cashAppTag });
      toast.success('Cash App tag updated');
      setEditingCashApp(false);
    } catch (error) {
      toast.error('Failed to update Cash App tag');
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'active':
        return <Badge className="status-active">Active</Badge>;
      case 'pending':
        return <Badge className="status-pending">Pending</Badge>;
      case 'sold':
        return <Badge className="status-sold">Sold</Badge>;
      default:
        return null;
    }
  };

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="pt-24 flex items-center justify-center">
          <div className="text-[#00F0FF] font-mono animate-pulse">LOADING...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      
      <main className="pt-24 pb-12 px-4">
        <div className="max-w-6xl mx-auto">
          {/* Profile Header */}
          <div className="bg-[#0a0a0a] border border-[#27272a] p-6 mb-8">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-[#00F0FF]/20 border-2 border-[#00F0FF] flex items-center justify-center">
                  {user.picture ? (
                    <img src={user.picture} alt={user.name} className="w-full h-full rounded-full object-cover" />
                  ) : (
                    <User className="w-8 h-8 text-[#00F0FF]" />
                  )}
                </div>
                <div>
                  <h1 className="font-heading text-3xl font-bold text-white">{user.name}</h1>
                  <p className="text-white/50">{user.email}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <Link to="/sell">
                  <Button className="bg-[#FF0099] text-white hover:bg-[#FF0099]/90 font-heading tracking-wider" data-testid="new-listing-btn">
                    <Package className="w-4 h-4 mr-2" />
                    NEW LISTING
                  </Button>
                </Link>
                <Button 
                  variant="outline" 
                  onClick={handleLogout}
                  className="border-[#27272a] text-white hover:bg-red-500/10 hover:border-red-500"
                  data-testid="logout-btn"
                >
                  Logout
                </Button>
              </div>
            </div>
          </div>

          {/* Cash App Settings */}
          <div className="bg-[#0a0a0a] border border-[#27272a] p-6 mb-8">
            <h2 className="font-heading text-xl font-bold text-white mb-4 flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-[#39FF14]" />
              P2P PAYMENT - CASH APP
            </h2>
            <p className="text-white/50 text-sm mb-4">Add your Cash App tag for peer-to-peer trades</p>
            
            {editingCashApp ? (
              <div className="flex gap-2">
                <Input
                  value={cashAppTag}
                  onChange={(e) => setCashAppTag(e.target.value)}
                  placeholder="$YourCashTag"
                  className="max-w-xs bg-[#121212] border-[#27272a] text-white"
                  data-testid="cashapp-input"
                />
                <Button onClick={handleUpdateCashApp} className="bg-[#39FF14] text-black hover:bg-[#39FF14]/90">
                  Save
                </Button>
                <Button variant="outline" onClick={() => setEditingCashApp(false)} className="border-[#27272a] text-white">
                  Cancel
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <span className="text-white font-mono">{user.cash_app_tag || 'Not set'}</span>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => setEditingCashApp(true)}
                  className="border-[#27272a] text-white"
                  data-testid="edit-cashapp-btn"
                >
                  <Edit2 className="w-4 h-4" />
                </Button>
              </div>
            )}
          </div>

          {/* Tabs */}
          <Tabs defaultValue="listings" className="space-y-6">
            <TabsList className="bg-[#0a0a0a] border border-[#27272a] p-1 h-auto">
              <TabsTrigger value="listings" className="font-heading data-[state=active]:bg-[#00F0FF] data-[state=active]:text-black" data-testid="tab-listings">
                <Package className="w-4 h-4 mr-2" />
                MY LISTINGS
              </TabsTrigger>
              <TabsTrigger value="messages" className="font-heading data-[state=active]:bg-[#00F0FF] data-[state=active]:text-black" data-testid="tab-messages">
                <MessageCircle className="w-4 h-4 mr-2" />
                MESSAGES
              </TabsTrigger>
              <TabsTrigger value="transactions" className="font-heading data-[state=active]:bg-[#00F0FF] data-[state=active]:text-black" data-testid="tab-transactions">
                <Receipt className="w-4 h-4 mr-2" />
                TRANSACTIONS
              </TabsTrigger>
              <TabsTrigger value="trades" className="font-heading data-[state=active]:bg-[#39FF14] data-[state=active]:text-black" data-testid="tab-trades">
                <DollarSign className="w-4 h-4 mr-2" />
                CASH APP TRADES
              </TabsTrigger>
              <TabsTrigger value="subscription" className="font-heading data-[state=active]:bg-[#FF0099] data-[state=active]:text-white" data-testid="tab-subscription">
                <Crown className="w-4 h-4 mr-2" />
                PRO
              </TabsTrigger>
            </TabsList>

            {/* Listings Tab */}
            <TabsContent value="listings">
              {loading ? (
                <div className="text-center py-12 text-[#00F0FF] font-mono animate-pulse">LOADING...</div>
              ) : listings.length === 0 ? (
                <div className="text-center py-12 bg-[#0a0a0a] border border-[#27272a]">
                  <ShoppingBag className="w-16 h-16 text-white/20 mx-auto mb-4" />
                  <p className="text-white/50">No listings yet</p>
                  <Link to="/sell" className="text-[#00F0FF] hover:underline mt-2 inline-block">
                    Create your first listing
                  </Link>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {listings.map((listing) => (
                    <div key={listing.listing_id} className="bg-[#0a0a0a] border border-[#27272a] overflow-hidden">
                      <div className="aspect-video bg-[#121212] relative">
                        {listing.images && listing.images.length > 0 ? (
                          <img src={listing.images[0]} alt={listing.title} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <ShoppingBag className="w-12 h-12 text-white/10" />
                          </div>
                        )}
                        <div className="absolute top-2 left-2">
                          {getStatusBadge(listing.status)}
                        </div>
                      </div>
                      <div className="p-4">
                        <h3 className="font-heading text-lg font-bold text-white line-clamp-1">{listing.title}</h3>
                        <p className="text-white/50 text-sm">{listing.player_name}</p>
                        <div className="flex items-center justify-between mt-3">
                          <span className="font-mono text-[#00F0FF]">${listing.price.toFixed(2)}</span>
                          <div className="flex gap-2">
                            <Link to={`/marketplace/${listing.listing_id}`}>
                              <Button variant="outline" size="sm" className="border-[#27272a] text-white">
                                View
                              </Button>
                            </Link>
                            {listing.status === 'active' && (
                              <Button 
                                variant="outline" 
                                size="sm" 
                                onClick={() => handleDeleteListing(listing.listing_id)}
                                className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                                data-testid={`delete-listing-${listing.listing_id}`}
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Messages Tab */}
            <TabsContent value="messages">
              {messages.length === 0 ? (
                <div className="text-center py-12 bg-[#0a0a0a] border border-[#27272a]">
                  <MessageCircle className="w-16 h-16 text-white/20 mx-auto mb-4" />
                  <p className="text-white/50">No messages yet</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {messages.map((msg) => (
                    <div 
                      key={msg.message_id} 
                      className={`bg-[#0a0a0a] border border-[#27272a] p-4 ${!msg.is_read && msg.receiver_id === user.user_id ? 'border-l-4 border-l-[#00F0FF]' : ''}`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-white font-medium">
                              {msg.sender_id === user.user_id ? 'You' : msg.sender_name}
                            </span>
                            <span className="text-white/30 text-xs">
                              {msg.sender_id === user.user_id ? '→' : '←'}
                            </span>
                            <span className="text-white/50 text-sm">
                              Re: Listing #{msg.listing_id.slice(-6)}
                            </span>
                          </div>
                          <p className="text-white/80">{msg.content}</p>
                        </div>
                        <span className="text-white/30 text-xs whitespace-nowrap">
                          {new Date(msg.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Transactions Tab */}
            <TabsContent value="transactions">
              {transactions.length === 0 ? (
                <div className="text-center py-12 bg-[#0a0a0a] border border-[#27272a]">
                  <Receipt className="w-16 h-16 text-white/20 mx-auto mb-4" />
                  <p className="text-white/50">No transactions yet</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {transactions.map((txn) => (
                    <div key={txn.transaction_id} className="bg-[#0a0a0a] border border-[#27272a] p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-white font-medium">
                              {txn.buyer_id === user.user_id ? 'Purchase' : 'Sale'}
                            </span>
                            <Badge className={txn.payment_status === 'paid' ? 'status-active' : 'status-pending'}>
                              {txn.payment_status}
                            </Badge>
                          </div>
                          <p className="text-white/50 text-sm">Listing #{txn.listing_id.slice(-6)}</p>
                        </div>
                        <div className="text-right">
                          <span className="font-mono text-xl text-[#00F0FF]">
                            {txn.buyer_id === user.user_id ? '-' : '+'}${txn.amount.toFixed(2)}
                          </span>
                          <p className="text-white/30 text-xs">
                            {new Date(txn.created_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Cash App Trades Tab */}
            <TabsContent value="trades">
              {trades.length === 0 ? (
                <div className="text-center py-12 bg-[#0a0a0a] border border-[#27272a]">
                  <DollarSign className="w-16 h-16 text-white/20 mx-auto mb-4" />
                  <p className="text-white/50">No Cash App trades yet</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {trades.map((t) => {
                    const isBuyer = t.buyer_id === user.user_id;
                    const counterparty = isBuyer ? t.seller_name : t.buyer_name;
                    const statusColor = t.status === 'completed' ? 'bg-green-500/20 text-green-300 border-green-500/40'
                      : t.status === 'canceled' ? 'bg-red-500/20 text-red-300 border-red-500/40'
                      : t.status === 'paid' ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40'
                      : 'bg-blue-500/20 text-blue-300 border-blue-500/40';
                    return (
                      <div key={t.trade_id} className="bg-[#0a0a0a] border border-[#27272a] p-4" data-testid={`trade-row-${t.trade_id}`}>
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <span className="font-heading text-sm text-white tracking-wider">
                                {isBuyer ? 'BUYING FROM' : 'SELLING TO'} {counterparty}
                              </span>
                              <Badge className={statusColor}>{t.status.replace('_', ' ')}</Badge>
                            </div>
                            <p className="text-white/70 text-sm truncate max-w-md">{t.listing_title}</p>
                            <p className="text-white/40 text-xs mt-1">
                              Cash App: <span className="text-[#39FF14] font-mono">${t.seller_cash_app_tag}</span> · {new Date(t.created_at).toLocaleDateString()}
                            </p>
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            <span className="font-mono text-xl text-[#39FF14]">${t.total_amount}</span>
                            <div className="flex gap-2 flex-wrap justify-end">
                              {isBuyer && t.status === 'awaiting_payment' && (
                                <>
                                  <a href={t.cashapp_url} target="_blank" rel="noopener noreferrer" data-testid={`trade-pay-${t.trade_id}`}>
                                    <Button size="sm" className="bg-[#00D632] text-black hover:bg-[#00D632]/90 h-8">Pay Now</Button>
                                  </a>
                                  <Button size="sm" variant="outline" onClick={() => handleTradeAction(t.trade_id, 'mark-paid')} data-testid={`trade-mark-paid-${t.trade_id}`} className="border-[#39FF14] text-[#39FF14] h-8">
                                    I Paid
                                  </Button>
                                </>
                              )}
                              {!isBuyer && (t.status === 'paid' || t.status === 'awaiting_payment') && (
                                <Button size="sm" onClick={() => handleTradeAction(t.trade_id, 'confirm')} data-testid={`trade-confirm-${t.trade_id}`} className="bg-[#39FF14] text-black hover:bg-[#39FF14]/90 h-8">
                                  Confirm Received
                                </Button>
                              )}
                              {(t.status === 'awaiting_payment' || t.status === 'paid') && (
                                <Button size="sm" variant="outline" onClick={() => handleTradeAction(t.trade_id, 'cancel')} data-testid={`trade-cancel-${t.trade_id}`} className="border-red-500/30 text-red-400 hover:bg-red-500/10 h-8">
                                  Cancel
                                </Button>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </TabsContent>

            {/* Subscription Tab */}
            <TabsContent value="subscription">
              <SubscriptionPanel />
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
