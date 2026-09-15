/**
 * Random phrase coloring — Rip N' Flip palette only.
 *
 * Rules:
 *   • Each pageload picks a fresh random assignment (no persistence — refresh shuffles).
 *   • `keepWhite` controls how many words MUST stay white.
 *   • Remaining words are randomly assigned a color from the brand palette
 *     (toxic green / cyan / pink). No two adjacent words may share the same
 *     color to keep contrast pop.
 *   • Pure deterministic w.r.t. the seed → if you ever want a fixed sequence,
 *     pass a seed via Math.random replacement. Default: real random per load.
 */

export const RNF_PALETTE = ['#39FF14', '#00F0FF', '#FF0099'];

function pickDifferent(prev) {
  // Pick a palette color that doesn't match the previous one (keeps adjacent contrast)
  const pool = RNF_PALETTE.filter((c) => c !== prev);
  return pool[Math.floor(Math.random() * pool.length)];
}

/**
 * Assigns a color (or null = white) to each word.
 * @param {string[]} words
 * @param {number} keepWhite — number of words to leave WHITE
 * @returns {(string|null)[]} parallel array of colors; null = white
 */
export function colorizeWords(words, keepWhite = 2) {
  const n = words.length;
  if (n === 0) return [];

  // Cap keepWhite so at least 1 word always gets a color (otherwise no rotation visible)
  const keepW = Math.max(0, Math.min(keepWhite, Math.max(0, n - 1)));

  // Randomly pick which indices stay white
  const indices = Array.from({ length: n }, (_, i) => i);
  for (let i = indices.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  const whiteSet = new Set(indices.slice(0, keepW));

  const out = new Array(n);
  let prev = null;
  for (let i = 0; i < n; i += 1) {
    if (whiteSet.has(i)) {
      out[i] = null; // white
      prev = null;
    } else {
      const c = pickDifferent(prev);
      out[i] = c;
      prev = c;
    }
  }
  return out;
}
