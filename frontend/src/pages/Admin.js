import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Shield, Lock, Loader2, Database, Users, Activity, BarChart3, DollarSign,
  Upload, Trash2, FileText, Search, ShieldCheck, ShieldOff, Crown, Calendar,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TABS = [
  { id: 'dashboard', label: 'DASHBOARD', icon: BarChart3 },
  { id: 'users', label: 'USERS', icon: Users },
  { id: 'cards', label: 'CARDS DB', icon: Database },
  { id: 'activity', label: 'ACTIVITY', icon: Activity },
];

export default function Admin() {
  const { user, loading: authLoading } = useAuth();
  const [tab, setTab] = useState('dashboard');
  const [forbidden, setForbidden] = useState(false);
  const [stats, setStats] = useState(null);

  // Initial admin check by hitting a gated endpoint
  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/admin/dashboard/stats`, { withCredentials: true })
      .then((r) => { setStats(r.data); setForbidden(false); })
      .catch((e) => { if (e?.response?.status === 403) setForbidden(true); });
  }, [user]);

  if (authLoading) return <div className="min-h-screen bg-[#050505] flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/40" /></div>;

  if (!user) {
    return (
      <div className="min-h-screen bg-[#050505] flex items-center justify-center p-4">
        <div className="text-center max-w-sm">
          <Shield className="w-12 h-12 text-[#FF0099] mx-auto mb-3" />
          <h1 className="font-heading text-3xl text-white mb-2">ADMIN ACCESS</h1>
          <p className="text-white/50 mb-4">Please log in with an admin account.</p>
          <Link to="/admin/login" data-testid="goto-admin-login">
            <button className="bg-[#FF0099] text-white px-6 py-2.5 font-heading tracking-widest">ADMIN LOGIN</button>
          </Link>
        </div>
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className="min-h-screen bg-[#050505] flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <Lock className="w-12 h-12 text-[#FF0099] mx-auto mb-3" />
          <h1 className="font-heading text-3xl text-white mb-2">NOT AN ADMIN</h1>
          <p className="text-white/50 mb-2">Your email <span className="text-[#00F0FF] font-mono">{user.email}</span> is not in the admin list.</p>
          <p className="text-white/40 text-sm">Add it to <code className="bg-[#121212] px-2 py-0.5 text-[#FF0099]">ADMIN_EMAILS</code> in <code className="bg-[#121212] px-2 py-0.5">backend/.env</code>.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      {/* Admin top bar — distinct from regular nav */}
      <header className="bg-gradient-to-r from-[#FF0099]/10 via-black to-[#00F0FF]/10 border-b border-[#FF0099]/30 px-4 py-3 sticky top-0 z-40 backdrop-blur">
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-[#FF0099] flex items-center justify-center">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-heading text-white text-lg tracking-tight">ADMIN <span className="text-[#FF0099]">CONTROL</span></div>
              <div className="text-[9px] font-mono text-white/40 tracking-widest">SIGNED IN: {user.email}</div>
            </div>
          </div>
          <Link to="/" className="text-white/50 hover:text-white text-sm font-mono">← BACK TO APP</Link>
        </div>
      </header>

      {/* Tab Nav */}
      <div className="border-b border-white/5 bg-[#050505]/80 backdrop-blur sticky top-[57px] z-30">
        <div className="max-w-7xl mx-auto flex overflow-x-auto px-4">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                data-testid={`admin-tab-${t.id}`}
                className={`px-5 py-3 font-heading text-sm tracking-widest flex items-center gap-2 border-b-2 ${
                  active ? 'border-[#FF0099] text-[#FF0099]' : 'border-transparent text-white/50 hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {tab === 'dashboard' && <DashboardTab stats={stats} />}
        {tab === 'users' && <UsersTab />}
        {tab === 'cards' && <CardsTab />}
        {tab === 'activity' && <ActivityTab />}
      </main>
    </div>
  );
}

/* ============= DASHBOARD ============= */
function DashboardTab({ stats }) {
  if (!stats) return <div className="text-center py-12"><Loader2 className="w-6 h-6 animate-spin text-white/40 mx-auto" /></div>;

  const u = stats.users;
  const r = stats.revenue;
  const m = stats.marketplace;
  const c = stats.display_case;
  const p = stats.predictor;

  return (
    <div className="space-y-6" data-testid="dashboard-tab">
      {/* MRR Hero */}
      <div className="bg-gradient-to-br from-[#FF0099]/15 via-[#0a0a0a] to-[#00F0FF]/10 border-2 border-[#FF0099]/30 p-6 sm:p-8 relative overflow-hidden">
        <div className="absolute -top-20 -right-20 w-72 h-72 bg-[#FF0099] rounded-full blur-[120px] opacity-25" />
        <div className="relative z-10 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <div className="text-[10px] font-mono text-white/50 tracking-widest mb-1">MONTHLY RECURRING</div>
            <div className="font-heading text-5xl font-black text-[#39FF14]" data-testid="mrr-value">${r.monthly_recurring.toFixed(2)}</div>
            <div className="text-white/50 text-xs mt-1">{r.active_subs} active sub{r.active_subs === 1 ? '' : 's'} × ${r.price_per_sub.toFixed(2)}/mo</div>
          </div>
          <div>
            <div className="text-[10px] font-mono text-white/50 tracking-widest mb-1">LIFETIME REVENUE</div>
            <div className="font-heading text-3xl font-black text-white">${r.lifetime_revenue.toFixed(2)}</div>
            <div className="text-white/40 text-xs mt-1">all paid invoices</div>
          </div>
          <div>
            <div className="text-[10px] font-mono text-white/50 tracking-widest mb-1">PRO PRICE</div>
            <div className="font-heading text-3xl font-black text-white">${r.price_per_sub.toFixed(2)}</div>
            <div className="text-white/40 text-xs mt-1">per month</div>
          </div>
        </div>
      </div>

      {/* User Tier breakdown */}
      <div>
        <h2 className="font-heading text-lg tracking-widest text-white/70 mb-3">USER TIER BREAKDOWN</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard label="Total Users" value={u.total} accent="#00F0FF" />
          <KpiCard label="Pro Active" value={u.pro_active} accent="#FF0099" />
          <KpiCard label="Trial Users" value={u.trial} accent="#FACC15" />
          <KpiCard label="Free Users" value={u.free} accent="#94A3B8" />
        </div>
      </div>

      {/* Growth */}
      <div>
        <h2 className="font-heading text-lg tracking-widest text-white/70 mb-3">GROWTH</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard label="New / Week" value={u.new_this_week} accent="#39FF14" />
          <KpiCard label="New / Month" value={u.new_this_month} accent="#39FF14" />
          <KpiCard label="Pending Cancel" value={u.pending_cancel} accent="#FACC15" />
          <KpiCard label="Canceled" value={u.canceled} accent="#FF3939" />
        </div>
      </div>

      {/* Marketplace */}
      <div>
        <h2 className="font-heading text-lg tracking-widest text-white/70 mb-3">MARKETPLACE</h2>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <KpiCard label="Total Listings" value={m.listings_total} accent="#00F0FF" />
          <KpiCard label="Active" value={m.listings_active} accent="#39FF14" />
          <KpiCard label="Sold" value={m.listings_sold} accent="#FF0099" />
          <KpiCard label="Trades" value={m.trades_total} accent="#00F0FF" />
          <KpiCard label="Completed Trades" value={m.trades_completed} accent="#39FF14" />
        </div>
      </div>

      {/* Activity */}
      <div>
        <h2 className="font-heading text-lg tracking-widest text-white/70 mb-3">ENGAGEMENT</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KpiCard label="Packs Logged" value={c.packs_logged} accent="#00F0FF" />
          <KpiCard label="Pulls Logged" value={c.pulls_logged} accent="#39FF14" />
          <KpiCard label="Predictor Uses 24h" value={p.uses_24h} accent="#FF0099" />
          <KpiCard label="Predictor All-Time" value={p.uses_total} accent="#FACC15" />
        </div>
      </div>

      <div className="text-[10px] font-mono text-white/30 text-right">Refreshed: {new Date(stats.generated_at).toLocaleString()}</div>
    </div>
  );
}

function KpiCard({ label, value, accent }) {
  return (
    <div className="bg-[#0a0a0a] border border-[#27272a] px-4 py-3" style={{ borderColor: `${accent}33` }}>
      <div className="text-[10px] font-mono text-white/40 tracking-widest uppercase">{label}</div>
      <div className="font-mono text-2xl sm:text-3xl font-black mt-1" style={{ color: accent }}>{value}</div>
    </div>
  );
}

/* ============= USERS ============= */
function UsersTab() {
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = async (q = '') => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/users`, { params: q ? { search: q } : {}, withCredentials: true });
      setUsers(r.data.users || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const grant = async (uid) => {
    setBusyId(uid);
    try {
      await axios.post(`${API}/admin/users/${uid}/grant-pro`, null, { params: { days: 30 }, withCredentials: true });
      toast.success('Pro granted (30 days)');
      load(search);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Grant failed');
    } finally { setBusyId(null); }
  };
  const revoke = async (uid) => {
    if (!window.confirm('Revoke Pro immediately?')) return;
    setBusyId(uid);
    try {
      await axios.post(`${API}/admin/users/${uid}/revoke-pro`, null, { withCredentials: true });
      toast.success('Pro revoked');
      load(search);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Revoke failed');
    } finally { setBusyId(null); }
  };

  return (
    <div data-testid="users-tab">
      <div className="flex items-center gap-3 mb-4">
        <Search className="w-4 h-4 text-white/40" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && load(search)}
          placeholder="search by email or name..."
          data-testid="users-search-input"
          className="flex-1 bg-[#121212] border border-white/10 focus:border-[#FF0099] text-white text-sm px-3 py-2 outline-none"
        />
        <button onClick={() => load(search)} className="bg-[#FF0099] text-white px-4 font-heading text-xs tracking-widest h-9">SEARCH</button>
      </div>

      {loading ? <div className="text-center py-8"><Loader2 className="w-5 h-5 animate-spin text-white/40 mx-auto" /></div> : (
        <div className="bg-[#0a0a0a] border border-[#27272a] overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-black/30 text-[10px] font-mono text-white/40 uppercase tracking-widest">
              <tr>
                <th className="text-left px-3 py-2">Email</th>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Tier</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Joined</th>
                <th className="text-right px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-t border-white/5 hover:bg-white/2" data-testid={`user-row-${u.user_id}`}>
                  <td className="px-3 py-2 text-white">{u.email}{u.is_admin && <span className="ml-2 text-[8px] font-mono px-1 bg-[#FF0099]/20 text-[#FF0099] tracking-widest">ADMIN</span>}</td>
                  <td className="px-3 py-2 text-white/70">{u.name}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 tracking-widest ${
                      u.tier === 'pro' ? 'bg-[#FF0099]/20 text-[#FF0099]' :
                      u.tier === 'trial' ? 'bg-yellow-500/20 text-yellow-300' :
                      'bg-white/5 text-white/50'
                    }`}>{u.tier.toUpperCase()}</span>
                  </td>
                  <td className="px-3 py-2 text-white/60 text-xs">{u.subscription_status || '—'}{u.cancel_at_period_end ? ' · canceling' : ''}</td>
                  <td className="px-3 py-2 text-white/40 text-xs">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                  <td className="px-3 py-2 text-right">
                    {u.tier !== 'pro' ? (
                      <button onClick={() => grant(u.user_id)} disabled={busyId === u.user_id} data-testid={`grant-pro-${u.user_id}`} className="text-[#39FF14] hover:underline text-xs disabled:opacity-30">Grant 30d</button>
                    ) : (
                      <button onClick={() => revoke(u.user_id)} disabled={busyId === u.user_id} data-testid={`revoke-pro-${u.user_id}`} className="text-red-400 hover:underline text-xs disabled:opacity-30">Revoke</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {users.length === 0 && <div className="p-6 text-center text-white/40 text-sm">No users found</div>}
        </div>
      )}
    </div>
  );
}

/* ============= CARDS DB (existing CSV importer) ============= */
function CardsTab() {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [sets, setSets] = useState([]);
  const [totalCards, setTotalCards] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);

  const loadSets = async () => {
    try {
      const r = await axios.get(`${API}/admin/cards/sets`, { withCredentials: true });
      setSets(r.data.sets || []);
      setTotalCards(r.data.total_cards || 0);
    } catch {}
  };
  useEffect(() => { loadSets(); }, []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true); setImportResult(null);
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await axios.post(`${API}/admin/cards/import`, fd, { headers: { 'Content-Type': 'multipart/form-data' }, withCredentials: true });
      setImportResult(r.data);
      toast.success(`Imported ${r.data.inserted} cards`);
      loadSets();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Import failed');
    } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const clearSet = async (s) => {
    if (!window.confirm(`Delete all ${s.count} cards from ${s.set} (${s.year})?`)) return;
    await axios.delete(`${API}/admin/cards/clear`, { params: { set_name: s.set, year: s.year }, withCredentials: true });
    toast.success(`Cleared ${s.set} ${s.year}`); loadSets();
  };
  const runSearch = async () => {
    if (!searchQuery.trim()) return;
    const r = await axios.get(`${API}/cards/search`, { params: { q: searchQuery } });
    setSearchResults(r.data);
  };

  return (
    <div className="space-y-5" data-testid="cards-tab">
      <div className="text-white/50 text-sm">{totalCards.toLocaleString()} cards across {sets.length} sets</div>

      <section className="bg-[#0a0a0a] border border-[#27272a] p-5">
        <h3 className="font-heading text-sm text-white tracking-widest mb-3 flex items-center gap-2">
          <Upload className="w-4 h-4 text-[#00F0FF]" /> IMPORT CSV CHECKLIST
        </h3>
        <p className="text-white/50 text-xs mb-3">Columns (flexible): card_number, player, team, set, year, brand, sport, parallel, image_url</p>
        <input type="file" ref={fileRef} accept=".csv,text/csv" onChange={handleUpload} disabled={uploading} data-testid="csv-upload-input"
          className="block w-full text-sm text-white/70 file:mr-4 file:py-2 file:px-4 file:border-0 file:text-xs file:font-heading file:tracking-widest file:bg-[#FF0099] file:text-white hover:file:bg-[#FF0099]/90" />
        {uploading && <div className="mt-2 text-[#00F0FF] text-xs flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Importing...</div>}
        {importResult && (
          <div className="mt-3 bg-[#121212] border border-white/10 p-3 text-xs font-mono space-y-1" data-testid="import-result">
            <div className="text-[#39FF14]">✓ Inserted: {importResult.inserted}</div>
            <div className="text-yellow-300">⚠ Skipped: {importResult.skipped}</div>
            <div className="text-white/50">Total: {importResult.total_in_db.toLocaleString()}</div>
          </div>
        )}
      </section>

      <section className="bg-[#0a0a0a] border border-[#27272a] p-5">
        <h3 className="font-heading text-sm text-white tracking-widest mb-3 flex items-center gap-2"><FileText className="w-4 h-4 text-[#39FF14]" /> SETS</h3>
        {sets.length === 0 ? <div className="text-white/40 text-xs">No sets imported yet</div> : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {sets.map((s, i) => (
              <div key={i} className="flex items-center justify-between bg-[#121212] border border-white/5 px-3 py-2 text-sm">
                <div><span className="text-white">{s.set}</span><span className="text-white/40 ml-2">({s.year})</span><span className="text-[#39FF14] font-mono ml-2">· {s.count}</span></div>
                <button onClick={() => clearSet(s)} className="text-red-400/70 hover:text-red-400"><Trash2 className="w-4 h-4" /></button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="bg-[#0a0a0a] border border-[#27272a] p-5">
        <h3 className="font-heading text-sm text-white tracking-widest mb-3 flex items-center gap-2"><Search className="w-4 h-4 text-[#FF0099]" /> CARD SEARCH</h3>
        <div className="flex gap-2 mb-3">
          <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && runSearch()}
            placeholder="player or set name..." data-testid="card-search-input"
            className="flex-1 bg-[#121212] border border-white/10 focus:border-[#FF0099] text-white text-sm px-3 py-2 outline-none" />
          <button onClick={runSearch} data-testid="card-search-btn" className="bg-[#FF0099] text-white px-4 font-heading text-xs tracking-widest">SEARCH</button>
        </div>
        {searchResults && (
          <div className="bg-[#121212] border border-white/5 p-3" data-testid="search-results">
            <div className="text-[10px] text-white/40 font-mono mb-2">Source: <span className="text-[#00F0FF]">{searchResults.source}</span> · {searchResults.count} results</div>
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {searchResults.results.slice(0, 10).map((r, i) => (
                <div key={i} className="text-sm bg-black/30 px-2 py-1.5">
                  <span className="text-white">{r.title || `${r.player} (${r.year} ${r.set})`}</span>
                  {r.card_number && <span className="text-[#FF0099] font-mono ml-2">#{r.card_number}</span>}
                  {r.price !== undefined && r.price !== null && <span className="text-[#39FF14] font-mono ml-2">${r.price}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

/* ============= ACTIVITY ============= */
function ActivityTab() {
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    axios.get(`${API}/admin/recent-activity`, { withCredentials: true })
      .then((r) => { setActivity(r.data.activity || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-center py-8"><Loader2 className="w-5 h-5 animate-spin text-white/40 mx-auto" /></div>;

  return (
    <div className="space-y-2" data-testid="activity-tab">
      {activity.map((a, i) => <ActivityRow key={i} a={a} />)}
      {activity.length === 0 && <div className="text-white/40 text-sm">No recent activity</div>}
    </div>
  );
}

function ActivityRow({ a }) {
  const meta = {
    signup:  { icon: <Users className="w-4 h-4" />, color: '#39FF14', label: 'NEW USER' },
    listing: { icon: <DollarSign className="w-4 h-4" />, color: '#00F0FF', label: 'LISTING' },
    trade:   { icon: <Crown className="w-4 h-4" />, color: '#FF0099', label: 'TRADE' },
    pull:    { icon: <FileText className="w-4 h-4" />, color: '#FACC15', label: 'PULL' },
  }[a.type] || { icon: <Activity className="w-4 h-4" />, color: '#94A3B8', label: 'EVENT' };

  return (
    <div className="bg-[#0a0a0a] border border-[#27272a] px-4 py-3 flex items-center gap-3 text-sm">
      <div className="w-8 h-8 flex items-center justify-center" style={{ background: `${meta.color}22`, color: meta.color }}>{meta.icon}</div>
      <div className="flex-1">
        <div className="text-[9px] font-mono tracking-widest" style={{ color: meta.color }}>{meta.label}</div>
        <div className="text-white/80">
          {a.type === 'signup' && <>{a.name || a.user} joined</>}
          {a.type === 'listing' && <>{a.seller} listed <span className="text-white">{a.title}</span> for <span className="text-[#39FF14]">${a.price}</span></>}
          {a.type === 'trade' && <>{a.buyer} → {a.seller} · <span className="text-white">{a.title}</span> · ${a.amount} · <span className="text-[#FF0099]">{a.status}</span></>}
          {a.type === 'pull' && <>Logged <span className="text-white">{a.card}</span> from {a.set} <span className="text-white/40">({a.source})</span></>}
        </div>
      </div>
      <div className="text-[10px] font-mono text-white/30">{a.at ? new Date(a.at).toLocaleString() : ''}</div>
    </div>
  );
}
