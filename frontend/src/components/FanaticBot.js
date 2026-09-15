import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { MessageCircle, X, Send, Loader2, Trash2, Zap, Sparkles } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const SESSION_KEY = 'fanatic_chat_session_id';

export default function FanaticBot() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || null);
  const [botOnline, setBotOnline] = useState(null);
  const scrollRef = useRef(null);

  // Load history on open
  useEffect(() => {
    if (!open) return;
    // ping health
    axios.get(`${API}/chat/health`).then((r) => setBotOnline(r.data.ok)).catch(() => setBotOnline(false));
    if (sessionId) {
      axios.get(`${API}/chat/history/${sessionId}`).then((r) => {
        setMessages(r.data.messages || []);
      }).catch(() => {});
    }
  }, [open, sessionId]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    const ts = new Date().toISOString();
    setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: ts }]);
    setLoading(true);

    // Streaming via fetch + ReadableStream
    let assistantIndex = null;
    try {
      const resp = await fetch(`${API}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Stream failed' }));
        throw new Error(err.detail || 'Stream failed');
      }
      // Create empty assistant message we'll append tokens into
      setMessages((prev) => {
        assistantIndex = prev.length;
        return [...prev, { role: 'assistant', content: '', timestamp: new Date().toISOString(), streaming: true }];
      });

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let gotError = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let newlineIdx;
        while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
          const line = buffer.slice(0, newlineIdx).trim();
          buffer = buffer.slice(newlineIdx + 1);
          if (!line) continue;
          let evt;
          try { evt = JSON.parse(line); } catch { continue; }
          if (evt.type === 'session') {
            if (evt.session_id && evt.session_id !== sessionId) {
              setSessionId(evt.session_id);
              localStorage.setItem(SESSION_KEY, evt.session_id);
            }
          } else if (evt.type === 'token') {
            setMessages((prev) => {
              const updated = [...prev];
              const idx = updated.length - 1;
              updated[idx] = { ...updated[idx], content: (updated[idx].content || '') + evt.content };
              return updated;
            });
          } else if (evt.type === 'error') {
            gotError = true;
            setMessages((prev) => {
              const updated = [...prev];
              const idx = updated.length - 1;
              updated[idx] = { ...updated[idx], content: `⚠️ ${evt.detail}`, error: true, streaming: false };
              return updated;
            });
          } else if (evt.type === 'done') {
            setMessages((prev) => {
              const updated = [...prev];
              const idx = updated.length - 1;
              if (updated[idx]) updated[idx] = { ...updated[idx], streaming: false };
              return updated;
            });
          }
        }
      }
      if (!gotError) {
        setMessages((prev) => {
          const updated = [...prev];
          const idx = updated.length - 1;
          if (updated[idx]) updated[idx] = { ...updated[idx], streaming: false };
          return updated;
        });
      }
    } catch (err) {
      const detail = err?.message || 'The Fanatic is ghosting right now.';
      setMessages((prev) => [...prev, { role: 'assistant', content: `⚠️ ${detail}`, timestamp: new Date().toISOString(), error: true }]);
    } finally {
      setLoading(false);
    }
  };

  const clear = async () => {
    if (sessionId) {
      try { await axios.delete(`${API}/chat/history/${sessionId}`); } catch {}
    }
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    setMessages([]);
  };

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <>
      {/* Floating Trigger Button — Rip N' Flip logo (circle-clipped tight to green ring) */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          data-testid="fanatic-bot-toggle"
          className="fixed right-4 sm:right-6 z-[60] w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-transparent flex items-center justify-center hover:scale-110 transition-transform overflow-hidden"
          style={{
            bottom: `calc(1.5rem + env(safe-area-inset-bottom))`,
            boxShadow: '0 0 24px #39FF14aa, 0 0 48px #00F0FF55',
          }}
          aria-label="Open Jesse SLM 1.0"
        >
          <img src="/logo.png" alt="Rip N' Flip" className="w-full h-full object-cover block" draggable={false} />
          <span className="absolute -top-2 -right-2 text-[8px] font-heading font-black bg-[#FF0099] text-white px-1.5 py-0.5 tracking-widest border-2 border-black">
            SOON
          </span>
        </button>
      )}

      {/* Chat Panel */}
      {open && (
        <div
          data-testid="fanatic-bot-panel"
          className="fixed right-2 sm:right-6 left-2 sm:left-auto z-[60] w-auto sm:w-[92vw] sm:max-w-md h-[80vh] max-h-[640px] bg-[#0a0a0a] border border-[#00F0FF]/40 shadow-2xl flex flex-col"
          style={{ boxShadow: '0 0 40px rgba(0, 240, 255, 0.25)', bottom: `calc(1rem + env(safe-area-inset-bottom))` }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-gradient-to-r from-[#00F0FF]/10 to-[#FF0099]/10">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-full overflow-hidden bg-transparent">
                <img src="/logo.png" alt="Rip N' Flip" className="w-full h-full object-cover block" draggable={false} />
              </div>
              <div>
                <div className="font-heading text-white font-bold tracking-wider text-sm flex items-center gap-2">
                  JESSE SLM 1.0
                  <span className="text-[8px] font-mono px-1.5 py-0.5 bg-[#FF0099]/20 text-[#FF0099] border border-[#FF0099]/40 tracking-widest">SOON</span>
                </div>
                <div className="text-[10px] text-white/50 flex items-center gap-1">
                  <span className={`w-1.5 h-1.5 rounded-full ${botOnline === false ? 'bg-yellow-400' : botOnline ? 'bg-green-400' : 'bg-yellow-400'} animate-pulse`} />
                  {botOnline === false ? 'In training — coming with launch' : botOnline ? 'Ready to talk cards' : 'Connecting...'}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={clear} data-testid="fanatic-bot-clear" className="p-2 text-white/50 hover:text-white" aria-label="Clear chat">
                <Trash2 className="w-4 h-4" />
              </button>
              <button onClick={() => setOpen(false)} data-testid="fanatic-bot-close" className="p-2 text-white/50 hover:text-white" aria-label="Close">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} data-testid="fanatic-bot-messages" className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-center text-white/60 text-sm mt-8 space-y-3">
                <div className="w-16 h-16 mx-auto bg-[#FF0099]/10 border border-[#FF0099]/40 flex items-center justify-center">
                  <Sparkles className="w-8 h-8 text-[#FF0099]" />
                </div>
                <p className="font-heading tracking-wider text-white text-lg">JESSE'S NOT HERE YET</p>
                <p className="text-xs text-white/60 px-4 leading-relaxed">
                  Your personal sports-card fanatic AI is still in the lab —
                  unfiltered, vulgar, razor sharp on cards and packs.
                  Drops with launch. <span className="text-[#FF0099]">Stay ready.</span>
                </p>
                <div className="grid grid-cols-1 gap-2 px-2 pt-2 text-left">
                  {[
                    "💬 Carries full convos like a real buddy",
                    "🃏 Drops hot card hints unprompted",
                    "🏈 Knows last night's games",
                    "🔥 Razor sharp & zero filter",
                  ].map((feat, i) => (
                    <div key={i} className="bg-white/5 border border-white/10 px-3 py-2 text-xs text-white/70">
                      {feat}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                data-testid={`fanatic-msg-${m.role}`}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                    m.role === 'user'
                      ? 'bg-[#00F0FF] text-black'
                      : m.error
                      ? 'bg-red-500/10 border border-red-500/40 text-red-300'
                      : 'bg-white/5 border border-white/10 text-white'
                  }`}
                >
                  {m.content}
                  {m.streaming && <span className="inline-block w-2 h-4 bg-[#00F0FF] ml-0.5 align-middle animate-pulse" />}
                </div>
              </div>
            ))}
            {loading && !messages.some((m) => m.streaming) && (
              <div className="flex justify-start" data-testid="fanatic-loading">
                <div className="bg-white/5 border border-white/10 px-3 py-2 text-sm text-white/60 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-[#00F0FF]" />
                  The Fanatic is cookin'...
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          {botOnline === false ? (
            <div className="border-t border-white/10 p-4 bg-black/40 text-center" data-testid="fanatic-bot-soon">
              <a
                href="/register"
                className="inline-flex items-center justify-center gap-2 w-full bg-[#FF0099] text-white font-heading tracking-widest text-sm py-3 hover:bg-[#FF0099]/90 transition"
              >
                <Sparkles className="w-4 h-4" /> NOTIFY ME WHEN JESSE DROPS
              </a>
              <p className="text-[10px] text-white/40 mt-2 font-mono">Free account · we'll email you the day he goes live</p>
            </div>
          ) : (
            <div className="border-t border-white/10 p-3 flex gap-2 bg-black/40">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKey}
                rows={1}
                placeholder="Ask about cards, packs, grading..."
                data-testid="fanatic-bot-input"
                className="flex-1 bg-[#111] border border-white/10 focus:border-[#00F0FF] text-white text-sm px-3 py-2 resize-none outline-none"
                disabled={loading}
              />
              <button
                onClick={send}
                disabled={loading || !input.trim()}
                data-testid="fanatic-bot-send"
                className="bg-[#00F0FF] text-black px-4 disabled:opacity-40 hover:bg-[#00F0FF]/80 flex items-center justify-center"
                aria-label="Send"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
