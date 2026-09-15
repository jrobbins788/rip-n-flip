import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, Filter, Plus, ShoppingBag, RefreshCcw, DollarSign } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Marketplace() {
  const { user } = useAuth();
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sportFilter, setSportFilter] = useState('all');
  const [cardTypeFilter, setCardTypeFilter] = useState('all');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');

  const sports = ['NFL', 'NBA', 'MLB', 'NHL', 'Soccer'];
  const cardTypes = ['Auto', 'Rookie', 'Numbered', 'Parallel', 'Base', 'Insert', 'Patch'];

  useEffect(() => {
    fetchListings();
  }, [sportFilter, cardTypeFilter]);

  const fetchListings = async () => {
    setLoading(true);
    try {
      let url = `${API}/listings?`;
      if (sportFilter !== 'all') url += `sport=${sportFilter}&`;
      if (cardTypeFilter !== 'all') url += `card_type=${cardTypeFilter}&`;
      if (search) url += `search=${encodeURIComponent(search)}&`;
      if (minPrice) url += `min_price=${minPrice}&`;
      if (maxPrice) url += `max_price=${maxPrice}&`;
      
      const response = await fetch(url);
      const data = await response.json();
      setListings(data);
    } catch (error) {
      console.error('Error fetching listings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchListings();
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

  const getStatusBadge = (status) => {
    switch (status) {
      case 'active':
        return <Badge className="status-active">Available</Badge>;
      case 'pending':
        return <Badge className="status-pending">Pending</Badge>;
      case 'sold':
        return <Badge className="status-sold">Sold</Badge>;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      
      <main className="pt-24 pb-12 px-4">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8">
            <div>
              <div className="inline-flex items-center gap-2 bg-[#FF0099]/10 border border-[#FF0099]/30 px-4 py-2 mb-4">
                <ShoppingBag className="w-4 h-4 text-[#FF0099]" />
                <span className="text-[#FF0099] font-mono text-sm">COMMUNITY MARKETPLACE</span>
              </div>
              <h1 className="font-heading text-5xl sm:text-6xl font-bold text-white uppercase tracking-tight">
                MARKET<span className="text-[#FF0099]">PLACE</span>
              </h1>
              <p className="text-white/50 mt-2">Buy, sell, and trade cards with collectors</p>
            </div>
            {user && (
              <Link to="/sell" data-testid="create-listing-btn">
                <Button className="btn-tactical bg-[#FF0099] text-white hover:bg-[#FF0099]/90 font-heading tracking-wider">
                  <span className="flex items-center gap-2">
                    <Plus className="w-5 h-5" /> LIST A CARD
                  </span>
                </Button>
              </Link>
            )}
          </div>

          {/* Filters */}
          <div className="bg-[#0a0a0a] border border-[#27272a] p-4 mb-8">
            <form onSubmit={handleSearch} className="space-y-4">
              <div className="flex flex-col lg:flex-row gap-4">
                {/* Search */}
                <div className="flex-1 relative">
                  <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
                  <Input
                    type="text"
                    placeholder="Search cards, players, teams..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    data-testid="marketplace-search"
                    className="pl-12 bg-[#121212] border-[#27272a] text-white placeholder:text-white/30 h-12"
                  />
                </div>

                {/* Sport Filter */}
                <Select value={sportFilter} onValueChange={setSportFilter}>
                  <SelectTrigger className="w-full lg:w-40 bg-[#121212] border-[#27272a] text-white h-12" data-testid="sport-filter">
                    <SelectValue placeholder="Sport" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#0a0a0a] border-[#27272a]">
                    <SelectItem value="all">All Sports</SelectItem>
                    {sports.map((sport) => (
                      <SelectItem key={sport} value={sport}>{sport}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Card Type Filter */}
                <Select value={cardTypeFilter} onValueChange={setCardTypeFilter}>
                  <SelectTrigger className="w-full lg:w-40 bg-[#121212] border-[#27272a] text-white h-12" data-testid="type-filter">
                    <SelectValue placeholder="Card Type" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#0a0a0a] border-[#27272a]">
                    <SelectItem value="all">All Types</SelectItem>
                    {cardTypes.map((type) => (
                      <SelectItem key={type} value={type}>{type}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Button type="submit" className="bg-[#00F0FF] text-black hover:bg-[#00F0FF]/90 h-12 px-6" data-testid="search-btn">
                  <Filter className="w-5 h-5" />
                </Button>
              </div>

              {/* Price Range */}
              <div className="flex items-center gap-4">
                <span className="text-white/40 text-sm flex items-center gap-1">
                  <DollarSign className="w-4 h-4" /> Price:
                </span>
                <Input
                  type="number"
                  placeholder="Min"
                  value={minPrice}
                  onChange={(e) => setMinPrice(e.target.value)}
                  className="w-24 bg-[#121212] border-[#27272a] text-white h-10"
                  data-testid="min-price"
                />
                <span className="text-white/40">-</span>
                <Input
                  type="number"
                  placeholder="Max"
                  value={maxPrice}
                  onChange={(e) => setMaxPrice(e.target.value)}
                  className="w-24 bg-[#121212] border-[#27272a] text-white h-10"
                  data-testid="max-price"
                />
              </div>
            </form>
          </div>

          {/* Results Count */}
          <div className="flex items-center justify-between mb-6">
            <span className="text-white/50 font-mono text-sm">
              {listings.length} LISTING{listings.length !== 1 ? 'S' : ''} FOUND
            </span>
            <button
              onClick={fetchListings}
              className="text-white/50 hover:text-[#00F0FF] transition-colors flex items-center gap-2"
              data-testid="refresh-btn"
            >
              <RefreshCcw className="w-4 h-4" />
              <span className="text-sm font-mono">REFRESH</span>
            </button>
          </div>

          {/* Listings Grid */}
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="text-[#00F0FF] font-mono animate-pulse">LOADING LISTINGS...</div>
            </div>
          ) : listings.length === 0 ? (
            <div className="text-center py-20 border border-[#27272a] bg-[#0a0a0a]">
              <ShoppingBag className="w-16 h-16 text-white/20 mx-auto mb-4" />
              <p className="text-white/50 font-mono">No listings found</p>
              <p className="text-white/30 text-sm mt-2">Try adjusting your filters or be the first to list!</p>
            </div>
          ) : (
            <div className="masonry-grid">
              {listings.map((listing) => (
                <Link
                  key={listing.listing_id}
                  to={`/marketplace/${listing.listing_id}`}
                  data-testid={`listing-card-${listing.listing_id}`}
                  className="masonry-item block"
                >
                  <div className="bg-[#0a0a0a] border border-[#27272a] overflow-hidden hover:border-[#FF0099] transition-all card-tilt group">
                    {/* Card Image */}
                    <div className="aspect-[3/4] bg-[#121212] relative overflow-hidden">
                      {listing.images && listing.images.length > 0 ? (
                        <img
                          src={listing.images[0]}
                          alt={listing.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <ShoppingBag className="w-16 h-16 text-white/10" />
                        </div>
                      )}
                      <div className="absolute top-3 left-3">
                        {getStatusBadge(listing.status)}
                      </div>
                      {listing.is_tradeable && (
                        <div className="absolute top-3 right-3">
                          <Badge className="bg-[#39FF14]/20 text-[#39FF14] border border-[#39FF14]/30">
                            <RefreshCcw className="w-3 h-3 mr-1" /> Trade
                          </Badge>
                        </div>
                      )}
                    </div>

                    {/* Card Info */}
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h3 className="font-heading text-lg font-bold text-white line-clamp-2">{listing.title}</h3>
                        <Badge className={getSportColor(listing.sport)}>{listing.sport}</Badge>
                      </div>
                      
                      <p className="text-white/50 text-sm mb-2">{listing.player_name}</p>
                      
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xl text-[#00F0FF]">${listing.price.toFixed(2)}</span>
                        <span className="text-white/30 text-xs">{listing.condition}</span>
                      </div>
                      
                      <div className="mt-3 pt-3 border-t border-[#27272a]">
                        <span className="text-white/40 text-xs">by {listing.seller_name}</span>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* CTA for non-logged in users */}
          {!user && listings.length > 0 && (
            <div className="mt-12 text-center bg-[#0a0a0a] border border-[#27272a] p-8">
              <h3 className="font-heading text-2xl font-bold text-white mb-2">WANT TO SELL YOUR CARDS?</h3>
              <p className="text-white/50 mb-4">Join the community and start listing today</p>
              <Link to="/register" data-testid="marketplace-join-btn">
                <Button className="btn-tactical bg-[#FF0099] text-white hover:bg-[#FF0099]/90 font-heading tracking-wider">
                  <span>JOIN NOW</span>
                </Button>
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
