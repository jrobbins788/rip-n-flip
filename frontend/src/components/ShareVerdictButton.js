import { useCallback, useRef, useState } from 'react';
import { Share2, Download, Link2, Loader2, Check } from 'lucide-react';

const W = 1080;
const H = 1350;
const BRAND = 'ripnflipapp.com';

const VERDICT_COLORS = {
  DUB: '#39FF14',
  MID: '#FACC15',
  TRASH: '#FF3939',
};

function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

function wrapText(ctx, text, maxWidth) {
  const words = String(text || '').split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/**
 * Builds a 1080×1350 neon verdict card entirely in-browser (no engine internals).
 */
async function buildVerdictCard({ packName, rating, packCost, expectedValue, summary, packId }) {
  const color = VERDICT_COLORS[rating] || VERDICT_COLORS.MID;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  // Background
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, '#050505');
  bg.addColorStop(0.45, '#0a0a12');
  bg.addColorStop(1, '#050505');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // Neon frame
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 8;
  ctx.shadowColor = color;
  ctx.shadowBlur = 40;
  roundRect(ctx, 36, 36, W - 72, H - 72, 28);
  ctx.stroke();
  ctx.restore();

  // Soft glow blob behind verdict
  ctx.save();
  ctx.globalAlpha = 0.22;
  const glow = ctx.createRadialGradient(W / 2, 520, 40, W / 2, 520, 420);
  glow.addColorStop(0, color);
  glow.addColorStop(1, 'transparent');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 120, W, 700);
  ctx.restore();

  // Logo
  try {
    const logo = await loadImage('/logo.png');
    const size = 168;
    ctx.save();
    ctx.beginPath();
    ctx.arc(W / 2, 170, size / 2, 0, Math.PI * 2);
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(logo, W / 2 - size / 2, 170 - size / 2, size, size);
    ctx.restore();
    ctx.save();
    ctx.strokeStyle = '#39FF14';
    ctx.lineWidth = 4;
    ctx.shadowColor = '#39FF14';
    ctx.shadowBlur = 18;
    ctx.beginPath();
    ctx.arc(W / 2, 170, size / 2 + 2, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  } catch {
    /* logo optional */
  }

  // Pack name
  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  ctx.font = '700 28px Orbitron, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('PACK VERDICT', W / 2, 300);

  ctx.fillStyle = '#FFFFFF';
  ctx.font = '900 42px Orbitron, system-ui, sans-serif';
  const packLines = wrapText(ctx, packName || 'Unknown Pack', W - 160);
  let y = 360;
  for (const line of packLines.slice(0, 3)) {
    ctx.fillText(line.toUpperCase(), W / 2, y);
    y += 52;
  }

  // Giant verdict word
  ctx.save();
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 48;
  ctx.font = '900 180px Orbitron, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(String(rating || 'MID').toUpperCase(), W / 2, 620);
  ctx.restore();

  // Price rows
  const rows = [
    ['PACK COST', packCost != null ? `$${Number(packCost).toFixed(0)}` : '—'],
    ['EXPECTED PULL', expectedValue != null ? `$${Number(expectedValue).toFixed(0)}` : '—'],
  ];
  let rowY = 720;
  for (const [label, value] of rows) {
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    roundRect(ctx, 140, rowY, W - 280, 78, 12);
    ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.45)';
    ctx.font = '700 24px ui-monospace, monospace';
    ctx.textAlign = 'left';
    ctx.fillText(label, 170, rowY + 48);
    ctx.fillStyle = color;
    ctx.font = '900 36px Orbitron, system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(value, W - 170, rowY + 50);
    rowY += 100;
  }

  // Short summary (no engine internals)
  if (summary) {
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.font = '500 28px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    const lines = wrapText(ctx, summary, W - 200).slice(0, 3);
    let sy = 980;
    for (const line of lines) {
      ctx.fillText(line, W / 2, sy);
      sy += 38;
    }
  }

  // Footer
  ctx.fillStyle = 'rgba(255,255,255,0.35)';
  ctx.font = '700 26px Orbitron, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(BRAND, W / 2, H - 90);
  if (packId) {
    ctx.fillStyle = 'rgba(0,240,255,0.55)';
    ctx.font = '600 20px ui-monospace, monospace';
    ctx.fillText(`/analyzer?pack=${packId}`, W / 2, H - 56);
  }

  return canvas;
}

function shareUrlFor(packId) {
  const origin = typeof window !== 'undefined' ? window.location.origin : `https://${BRAND}`;
  return packId ? `${origin}/analyzer?pack=${packId}` : origin;
}

export default function ShareVerdictButton({ analysis }) {
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const lastBlob = useRef(null);

  const pack = analysis?.pack || {};
  const verdict = analysis?.verdict || {};
  const packId = pack.pack_id || analysis?.pack_id;
  const rating = verdict.rating || 'MID';

  const ensureCard = useCallback(async () => {
    const canvas = await buildVerdictCard({
      packName: pack.name,
      rating,
      packCost: verdict.pack_cost,
      expectedValue: verdict.expected_pull_value,
      summary: verdict.summary,
      packId,
    });
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    lastBlob.current = blob;
    return { canvas, blob, file: new File([blob], `rip-n-flip-${rating.toLowerCase()}.png`, { type: 'image/png' }) };
  }, [pack.name, packId, rating, verdict.expected_pull_value, verdict.pack_cost, verdict.summary]);

  const onShare = async () => {
    setBusy(true);
    try {
      const { file, blob } = await ensureCard();
      const url = shareUrlFor(packId);
      const title = `Rip N' Flip — ${rating}`;
      const text = `${pack.name || 'Pack'} is a ${rating}. Know before you rip.`;

      if (navigator.share && navigator.canShare?.({ files: [file] })) {
        await navigator.share({ title, text, url, files: [file] });
        return;
      }
      if (navigator.share) {
        await navigator.share({ title, text, url });
        return;
      }
      // Desktop fallback: download the card
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = file.name;
      a.click();
      URL.revokeObjectURL(a.href);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      if (err?.name !== 'AbortError') console.warn('Share failed', err);
    } finally {
      setBusy(false);
    }
  };

  const onSave = async () => {
    setBusy(true);
    try {
      const { blob, file } = lastBlob.current
        ? { blob: lastBlob.current, file: new File([lastBlob.current], `rip-n-flip-${rating.toLowerCase()}.png`, { type: 'image/png' }) }
        : await ensureCard();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = file.name;
      a.click();
      URL.revokeObjectURL(a.href);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setBusy(false);
    }
  };

  const onCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrlFor(packId));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Copy failed', err);
    }
  };

  const color = VERDICT_COLORS[rating] || VERDICT_COLORS.MID;

  return (
    <div className="flex flex-col sm:flex-row gap-2" data-testid="share-verdict">
      <button
        type="button"
        onClick={onShare}
        disabled={busy}
        data-testid="share-verdict-btn"
        className="flex-1 inline-flex items-center justify-center gap-2 h-14 font-heading tracking-widest text-black font-black uppercase hover:opacity-90 transition disabled:opacity-60"
        style={{ background: color, boxShadow: `0 0 28px ${color}66` }}
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />}
        SHARE THIS VERDICT
      </button>
      <button
        type="button"
        onClick={onSave}
        disabled={busy}
        data-testid="share-verdict-save"
        className="inline-flex items-center justify-center gap-2 h-14 px-5 bg-white/5 border border-white/20 text-white font-heading tracking-widest uppercase hover:border-white/50 transition"
      >
        {saved ? <Check className="w-4 h-4 text-[#39FF14]" /> : <Download className="w-4 h-4" />}
        {saved ? 'SAVED' : 'SAVE'}
      </button>
      <button
        type="button"
        onClick={onCopyLink}
        data-testid="share-verdict-copy"
        className="inline-flex items-center justify-center gap-2 h-14 px-5 bg-white/5 border border-white/20 text-white font-heading tracking-widest uppercase hover:border-[#00F0FF] hover:text-[#00F0FF] transition"
      >
        {copied ? <Check className="w-4 h-4 text-[#00F0FF]" /> : <Link2 className="w-4 h-4" />}
        {copied ? 'COPIED' : 'COPY LINK'}
      </button>
    </div>
  );
}
