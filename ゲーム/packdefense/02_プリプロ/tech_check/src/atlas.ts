// 絵の一覧（仮の資産）：コードで描いた丸と札を、端末の画素の大きさで1枚の大きな絵にまとめる。
// 毎フレームは、この絵から切り出して貼るだけ（drawImage）。形を毎回描かない。
export interface Frame { x: number; y: number; w: number; h: number }
export interface Atlas { canvas: HTMLCanvasElement; frames: Record<string, Frame>; scale: number }

export const ENEMY_COLORS = ['#c0392b', '#8e44ad', '#d35400', '#7f8c8d'];
export const HERO_COLORS = ['#2e86de', '#10ac84', '#f6b93b', '#e056fd'];
export const RARITY_COLORS = ['#f5f5f5', '#3c8dff', '#a55eea', '#f7c948']; // コモン・レア・エピック・レジェンド（仮。色は art が決める）
export const GLYPHS = '0123456789.e∞万億兆京';

/** scale：論理px 1 あたりの端末の画素の数 */
export function makeAtlas(scale: number): Atlas {
  const canvas = document.createElement('canvas');
  const cell = Math.ceil(56 * scale) + 4;
  const cols = 8;
  canvas.width = cell * cols; canvas.height = cell * 6;
  const g = canvas.getContext('2d')!;
  const frames: Record<string, Frame> = {};
  let slot = 0;
  const put = (name: string, wL: number, hL: number, draw: (g: CanvasRenderingContext2D, w: number, h: number) => void) => {
    const cx = (slot % cols) * cell, cy = Math.floor(slot / cols) * cell; slot++;
    const w = Math.ceil(wL * scale) + 2, h = Math.ceil(hL * scale) + 2;
    g.save(); g.translate(cx, cy); draw(g, w, h); g.restore();
    frames[name] = { x: cx, y: cy, w, h };
  };
  const circle = (fill: string, stroke: string | null, lw: number) => (g: CanvasRenderingContext2D, w: number, h: number) => {
    g.beginPath(); g.arc(w / 2, h / 2, w / 2 - 1 - lw * scale / 2, 0, Math.PI * 2);
    g.fillStyle = fill; g.fill();
    if (stroke) { g.lineWidth = lw * scale; g.strokeStyle = stroke; g.stroke(); }
  };
  ENEMY_COLORS.forEach((c, i) => put('enemy' + i, 14, 14, circle(c, '#2b1b1b', 1.5)));
  HERO_COLORS.forEach((c, i) => put('hero' + i, 18, 18, circle(c, '#ffffff', 2)));
  put('bullet', 5, 5, circle('#fff6a0', null, 0));
  ['#ffd166', '#ef476f', '#ffffff'].forEach((c, i) => put('particle' + i, 4, 4, circle(c, null, 0)));
  RARITY_COLORS.forEach((c, i) => put('pack' + i, 20, 26, (g, w, h) => {
    g.fillStyle = '#3d2c1e'; g.fillRect(1, 1, w - 2, h - 2);
    g.lineWidth = 3 * scale; g.strokeStyle = c; g.strokeRect(1.5 * scale, 1.5 * scale, w - 3 * scale, h - 3 * scale);
  }));
  put('tower', 48, 48, (g, w, h) => {
    g.fillStyle = '#6d6875'; g.fillRect(w * 0.2, h * 0.1, w * 0.6, h * 0.85);
    g.fillStyle = '#b5838d'; g.fillRect(w * 0.15, h * 0.05, w * 0.7, h * 0.15);
  });
  put('ring', 56, 56, (g, w, h) => {
    g.beginPath(); g.arc(w / 2, h / 2, w / 2 - 2 * scale, 0, Math.PI * 2);
    g.lineWidth = 3 * scale; g.strokeStyle = 'rgba(255,255,255,0.9)'; g.stroke();
    g.fillStyle = 'rgba(255,255,255,0.12)'; g.fill();
  });
  // 数字の字（ふつうの数字は fillText を毎回呼ばず、字の絵を並べる）
  g.font = `bold ${Math.round(11 * scale)}px system-ui, sans-serif`; g.textBaseline = 'top';
  for (const ch of GLYPHS) put('g' + ch, /[0-9.e]/.test(ch) ? 8 : 12, 13, (g, w) => {
    g.fillStyle = '#000'; g.fillText(ch, 1 + scale, 1 + scale);
    g.fillStyle = '#fff'; g.fillText(ch, 0, 0); void w;
  });
  return { canvas, frames, scale };
}
