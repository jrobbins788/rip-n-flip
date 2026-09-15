import { useEffect, useState } from 'react';
import axios from 'axios';
import Navbar from '../components/Navbar';
import { Zap, AlertCircle, CheckCircle2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function FanaticChat() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    axios.get(`${API}/chat/health`).then((r) => setHealth(r.data)).catch((e) => setHealth({ ok: false, reason: e.message }));
  }, []);

  return (
    <div className="min-h-screen bg-[#050505] text-white">
      <Navbar />
      <div className="max-w-4xl mx-auto px-6 pt-24 pb-12">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 bg-[#00F0FF] flex items-center justify-center glow-cyan">
            <Zap className="w-7 h-7 text-black" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="font-heading text-4xl font-black tracking-tight">
              ASK <span className="text-[#00F0FF]">THE FANATIC</span>
            </h1>
            <p className="text-white/60 text-sm">Unfiltered sports card wisdom. Click the neon button bottom-right to start.</p>
          </div>
        </div>

        {/* Status Panel */}
        <div className="bg-[#0a0a0a] border border-white/10 p-6 space-y-4" data-testid="fanatic-status-panel">
          <h2 className="font-heading text-xl tracking-wider">BOT STATUS</h2>
          {!health && <p className="text-white/50 text-sm">Checking Ollama connection...</p>}
          {health?.ok && (
            <div className="flex items-start gap-3 bg-green-500/10 border border-green-500/30 p-4">
              <CheckCircle2 className="w-5 h-5 text-green-400 mt-0.5" />
              <div className="text-sm">
                <p className="text-green-300 font-bold">Fanatic is ONLINE</p>
                <p className="text-white/70">Model: <span className="text-[#00F0FF]">{health.model}</span></p>
                <p className="text-white/70">Tunnel: <span className="text-white/90 break-all">{health.base_url}</span></p>
                {health.model_available === false && (
                  <p className="text-yellow-400 mt-1">
                    Warning: model "{health.model}" not found on server. Run: <code className="bg-black/40 px-1">ollama pull {health.model}</code>
                  </p>
                )}
              </div>
            </div>
          )}
          {health && !health.ok && (
            <div className="flex items-start gap-3 bg-red-500/10 border border-red-500/30 p-4">
              <AlertCircle className="w-5 h-5 text-red-400 mt-0.5" />
              <div className="text-sm">
                <p className="text-red-300 font-bold">Fanatic is OFFLINE</p>
                <p className="text-white/70 mt-1">{health.reason}</p>
              </div>
            </div>
          )}
        </div>

        {/* Setup Guide */}
        <div className="bg-[#0a0a0a] border border-white/10 p-6 mt-6 space-y-3" data-testid="fanatic-setup-guide">
          <h2 className="font-heading text-xl tracking-wider">SETUP YOUR OLLAMA TUNNEL</h2>
          <ol className="list-decimal list-inside text-sm text-white/70 space-y-2 leading-relaxed">
            <li>On your Linux Mint PC, install Ollama: <code className="bg-black/40 px-1 text-[#00F0FF]">curl -fsSL https://ollama.com/install.sh | sh</code></li>
            <li>Pull the model: <code className="bg-black/40 px-1 text-[#00F0FF]">ollama pull huihui_ai/qwen2.5-abliterate:7b</code></li>
            <li>Start Ollama server (binds to 127.0.0.1:11434 by default): <code className="bg-black/40 px-1 text-[#00F0FF]">ollama serve</code></li>
            <li>Expose it publicly with Cloudflare Tunnel: <code className="bg-black/40 px-1 text-[#00F0FF]">cloudflared tunnel --url http://localhost:11434</code></li>
            <li>Copy the <code className="text-[#FF1493]">https://xxx.trycloudflare.com</code> URL it prints.</li>
            <li>Paste it into <code className="bg-black/40 px-1">backend/.env</code> as <code className="text-[#00F0FF]">OLLAMA_BASE_URL=https://xxx.trycloudflare.com</code></li>
            <li>Restart backend: <code className="bg-black/40 px-1 text-[#00F0FF]">sudo supervisorctl restart backend</code></li>
          </ol>
          <p className="text-xs text-white/50 pt-2">
            Once connected, the floating bot is available on every page. Uncensored, unfiltered, zero corporate filter.
          </p>
        </div>
      </div>
    </div>
  );
}
