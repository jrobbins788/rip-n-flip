import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { Plus, Upload, X, DollarSign } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const SPORTS = ['NFL', 'NBA', 'MLB', 'NHL', 'Soccer'];
const CARD_TYPES = ['Auto', 'Rookie', 'Numbered', 'Parallel', 'Base', 'Insert', 'Patch', 'Relic'];
const CONDITIONS = ['Mint', 'Near Mint', 'Excellent', 'Good', 'Fair'];
const BRANDS = ['Panini Prizm', 'Topps Chrome', 'Bowman Chrome', 'National Treasures', 'Select', 'Mosaic', 'Donruss', 'Upper Deck', 'SP Authentic', 'Other'];

export default function CreateListing() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [sport, setSport] = useState('');
  const [cardType, setCardType] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [team, setTeam] = useState('');
  const [year, setYear] = useState('');
  const [brand, setBrand] = useState('');
  const [condition, setCondition] = useState('');
  const [price, setPrice] = useState('');
  const [isTradeable, setIsTradeable] = useState(false);
  const [images, setImages] = useState([]);

  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login');
    }
  }, [authLoading, user, navigate]);

  const handleImageUrl = () => {
    const url = prompt('Enter image URL:');
    if (url && url.trim()) {
      setImages(prev => [...prev, url.trim()]);
    }
  };

  const removeImage = (index) => {
    setImages(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!title || !sport || !cardType || !playerName || !condition || !price) {
      toast.error('Please fill in all required fields');
      return;
    }

    const priceNum = parseFloat(price);
    if (isNaN(priceNum) || priceNum <= 0) {
      toast.error('Please enter a valid price');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API}/listings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          title,
          description,
          sport,
          card_type: cardType,
          player_name: playerName,
          team,
          year,
          brand,
          condition,
          price: priceNum,
          is_tradeable: isTradeable,
          images
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create listing');
      }

      const listing = await response.json();
      toast.success('Listing created successfully!');
      navigate(`/marketplace/${listing.listing_id}`);
    } catch (error) {
      console.error('Create listing error:', error);
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="pt-24 flex items-center justify-center">
          <div className="text-[#00F0FF] font-mono animate-pulse">LOADING...</div>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      
      <main className="pt-24 pb-12 px-4">
        <div className="max-w-3xl mx-auto">
          <div className="mb-8">
            <div className="inline-flex items-center gap-2 bg-[#FF0099]/10 border border-[#FF0099]/30 px-4 py-2 mb-4">
              <Plus className="w-4 h-4 text-[#FF0099]" />
              <span className="text-[#FF0099] font-mono text-sm">NEW LISTING</span>
            </div>
            <h1 className="font-heading text-4xl sm:text-5xl font-bold text-white uppercase tracking-tight">
              LIST YOUR <span className="text-[#FF0099]">CARD</span>
            </h1>
            <p className="text-white/50 mt-2">Fill out the details to list your card on the marketplace</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-8">
            <div className="bg-[#0a0a0a] border border-[#27272a] p-6 space-y-6">
              <h2 className="font-heading text-xl font-bold text-white">CARD DETAILS</h2>
              
              <div className="space-y-4">
                <div>
                  <Label htmlFor="title" className="text-white/60">Title *</Label>
                  <Input
                    id="title"
                    placeholder="e.g., 2023 Prizm Victor Wembanyama RC Silver"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="mt-1 bg-[#121212] border-[#27272a] text-white"
                    data-testid="listing-title"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <Label className="text-white/60">Sport *</Label>
                    <Select value={sport} onValueChange={setSport}>
                      <SelectTrigger className="mt-1 bg-[#121212] border-[#27272a] text-white" data-testid="listing-sport">
                        <SelectValue placeholder="Select sport" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#0a0a0a] border-[#27272a]">
                        {SPORTS.map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-white/60">Card Type *</Label>
                    <Select value={cardType} onValueChange={setCardType}>
                      <SelectTrigger className="mt-1 bg-[#121212] border-[#27272a] text-white" data-testid="listing-card-type">
                        <SelectValue placeholder="Select type" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#0a0a0a] border-[#27272a]">
                        {CARD_TYPES.map((t) => (
                          <SelectItem key={t} value={t}>{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <Label htmlFor="player_name" className="text-white/60">Player Name *</Label>
                  <Input
                    id="player_name"
                    placeholder="e.g., Victor Wembanyama"
                    value={playerName}
                    onChange={(e) => setPlayerName(e.target.value)}
                    className="mt-1 bg-[#121212] border-[#27272a] text-white"
                    data-testid="listing-player"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <Label htmlFor="team" className="text-white/60">Team</Label>
                    <Input
                      id="team"
                      placeholder="e.g., Spurs"
                      value={team}
                      onChange={(e) => setTeam(e.target.value)}
                      className="mt-1 bg-[#121212] border-[#27272a] text-white"
                      data-testid="listing-team"
                    />
                  </div>

                  <div>
                    <Label htmlFor="year" className="text-white/60">Year</Label>
                    <Input
                      id="year"
                      placeholder="e.g., 2023"
                      value={year}
                      onChange={(e) => setYear(e.target.value)}
                      className="mt-1 bg-[#121212] border-[#27272a] text-white"
                      data-testid="listing-year"
                    />
                  </div>

                  <div>
                    <Label className="text-white/60">Brand</Label>
                    <Select value={brand} onValueChange={setBrand}>
                      <SelectTrigger className="mt-1 bg-[#121212] border-[#27272a] text-white" data-testid="listing-brand">
                        <SelectValue placeholder="Select brand" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#0a0a0a] border-[#27272a]">
                        {BRANDS.map((b) => (
                          <SelectItem key={b} value={b}>{b}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <Label className="text-white/60">Condition *</Label>
                  <Select value={condition} onValueChange={setCondition}>
                    <SelectTrigger className="mt-1 bg-[#121212] border-[#27272a] text-white" data-testid="listing-condition">
                      <SelectValue placeholder="Select condition" />
                    </SelectTrigger>
                    <SelectContent className="bg-[#0a0a0a] border-[#27272a]">
                      {CONDITIONS.map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="description" className="text-white/60">Description</Label>
                  <Textarea
                    id="description"
                    placeholder="Describe your card in detail..."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="mt-1 bg-[#121212] border-[#27272a] text-white min-h-[100px]"
                    data-testid="listing-description"
                  />
                </div>
              </div>
            </div>

            <div className="bg-[#0a0a0a] border border-[#27272a] p-6 space-y-6">
              <h2 className="font-heading text-xl font-bold text-white">IMAGES</h2>
              
              <div className="space-y-4">
                {images.length > 0 && (
                  <div className="flex flex-wrap gap-3">
                    {images.map((img, i) => (
                      <div key={i} className="relative w-24 h-24 bg-[#121212] border border-[#27272a]">
                        <img src={img} alt="" className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => removeImage(i)}
                          className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 rounded-full flex items-center justify-center"
                        >
                          <X className="w-4 h-4 text-white" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleImageUrl}
                  className="border-[#27272a] text-white hover:border-[#00F0FF]"
                  data-testid="add-image-btn"
                >
                  <Upload className="w-4 h-4 mr-2" />
                  Add Image URL
                </Button>
                <p className="text-white/40 text-sm">Add URLs to images of your card</p>
              </div>
            </div>

            <div className="bg-[#0a0a0a] border border-[#27272a] p-6 space-y-6">
              <h2 className="font-heading text-xl font-bold text-white">PRICING</h2>
              
              <div className="space-y-4">
                <div>
                  <Label htmlFor="price" className="text-white/60">Price (USD) *</Label>
                  <div className="relative mt-1">
                    <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
                    <Input
                      id="price"
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="0.00"
                      value={price}
                      onChange={(e) => setPrice(e.target.value)}
                      className="pl-10 bg-[#121212] border-[#27272a] text-white font-mono text-xl"
                      data-testid="listing-price"
                    />
                  </div>
                  <p className="text-white/40 text-sm mt-1">A 5% platform fee will be added at checkout</p>
                </div>

                <div className="flex items-center justify-between bg-[#121212] p-4">
                  <div>
                    <Label className="text-white">Open to Trades</Label>
                    <p className="text-white/40 text-sm">Allow users to offer trades</p>
                  </div>
                  <Switch
                    checked={isTradeable}
                    onCheckedChange={setIsTradeable}
                    data-testid="listing-tradeable"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/marketplace')}
                className="flex-1 border-[#27272a] text-white hover:bg-white/5"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={loading}
                className="flex-1 btn-tactical bg-[#FF0099] text-white hover:bg-[#FF0099]/90 font-heading tracking-wider"
                data-testid="submit-listing-btn"
              >
                <span>{loading ? 'Creating...' : 'CREATE LISTING'}</span>
              </Button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
