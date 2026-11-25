// 保存：端末内（localStorage）と、書き出し文字列。版の番号と指紋で、壊れた・違う版のデータをはじく。
import { type State, fingerprint, replay } from './sim.ts';

export const SAVE_KEY = 'yarikomi.techcheck.v1';
const PREFIX = 'YK1';

function b64urlEncode(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function b64urlDecode(s: string): string {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4);
  const bin = atob(b64);
  return new TextDecoder().decode(Uint8Array.from(bin, c => c.charCodeAt(0)));
}

export function exportText(s: State): string {
  const body = b64urlEncode(JSON.stringify(s));
  return `${PREFIX}.${body}.${fingerprint(s)}`;
}

export function importText(text: string): State {
  const parts = text.trim().split('.');
  if (parts.length !== 3 || parts[0] !== PREFIX) throw new Error('書き出しの形が違う（版が違うか、途中で切れている）');
  const s = JSON.parse(b64urlDecode(parts[1])) as State;
  if (s.v !== 1) throw new Error(`知らない版：${s.v}`);
  if (fingerprint(s) !== parts[2]) throw new Error('指紋が合わない（文字が欠けたか、書き換えられた）');
  // 記録から作り直して、同じ盤面になることも確かめる（規則が変わった版の読み込みを見つける）
  if (fingerprint(replay(s.seed, s.log)) !== parts[2]) throw new Error('記録から作り直すと盤面が合わない（規則の版が違う）');
  return s;
}

export interface Store { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }

export function saveLocal(store: Store, s: State): void { store.setItem(SAVE_KEY, exportText(s)); }
export function loadLocal(store: Store): State | null {
  const t = store.getItem(SAVE_KEY);
  if (!t) return null;
  try { return importText(t); } catch { return null; }
}
