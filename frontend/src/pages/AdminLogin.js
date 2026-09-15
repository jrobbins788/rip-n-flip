import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Shield, Lock, Mail, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminLogin() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email || !password) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/admin/login`, { email, password }, { withCredentials: true });
      toast.success('Welcome, admin');
      // Full reload so AuthContext picks up the new cookie cleanly
      window.location.href = '/admin';
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Admin login failed');
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center p-4 noise-bg" data-testid="admin-login-page">
      {/* Background glow */}
      <div className="absolute inset-0 opacity-20 pointer-events-none">
        <div className="absolute top-1/3 left-1/3 w-96 h-96 bg-[#FF0099] rounded-full blur-[140px]" />
      </div>

      <div className="relative z-10 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-[#FF0099]/10 border-2 border-[#FF0099] mb-4">
            <Shield className="w-8 h-8 text-[#FF0099]" />
          </div>
          <h1 className="font-heading text-4xl font-black text-white tracking-tight uppercase">
            ADMIN <span className="text-[#FF0099]">CONTROL</span>
          </h1>
          <p className="text-white/40 text-xs font-mono tracking-widest mt-2">
            RIP N' FLIP · RESTRICTED ACCESS
          </p>
        </div>

        <form onSubmit={submit} className="bg-[#0a0a0a] border border-[#FF0099]/30 p-6 space-y-4">
          <div>
            <label className="text-[10px] font-mono text-white/50 tracking-widest mb-1 block flex items-center gap-1">
              <Mail className="w-3 h-3" /> ADMIN EMAIL
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              data-testid="admin-login-email"
              className="w-full bg-[#121212] border border-white/10 focus:border-[#FF0099] text-white text-sm px-3 py-2.5 outline-none"
            />
          </div>
          <div>
            <label className="text-[10px] font-mono text-white/50 tracking-widest mb-1 block flex items-center gap-1">
              <Lock className="w-3 h-3" /> PASSWORD
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              data-testid="admin-login-password"
              className="w-full bg-[#121212] border border-white/10 focus:border-[#FF0099] text-white text-sm px-3 py-2.5 outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            data-testid="admin-login-submit"
            className="w-full bg-[#FF0099] text-white font-heading tracking-widest h-12 hover:bg-[#FF0099]/90 disabled:opacity-30 flex items-center justify-center gap-2"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> AUTHORIZING...</> : 'ENTER CONTROL ROOM'}
          </button>
        </form>

        <p className="text-center text-white/30 text-[10px] font-mono mt-4 tracking-widest">
          NON-ADMIN LOGIN? <a href="/login" className="text-[#00F0FF] hover:underline">USER LOGIN →</a>
        </p>
      </div>
    </div>
  );
}
