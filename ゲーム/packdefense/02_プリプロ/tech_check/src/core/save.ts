// 保存：端末内（localStorage）と、書き出し文字列。版の頭と指紋で、壊れた・違う版のデータをはじく。
// 保存するのは「ウェーブが始まった瞬間」と「ショップが開いた瞬間」だけ（デザインの柱 #16 の案）。
import { fnv1a } from './rng.ts';

export const SAVE_KEY = 'packdefense.techcheck.v1';
export const PREV_KEY = 'packdefense.techcheck.v1.prev'; // ひとつ前の保存（書き込み中に落ちたときの逃げ道）
const PREFIX = 'PD1';

export interface SaveData {
  v: 1;
  seed: string;            // ランのシード
  wave: number;
  phase: 'wave' | 'shop';
  coins: number;
  towerHp: number;
  fame: number;            // 名声（桁が伸びる数の代表。1e308 をこえたら Infinity になる）
  heroes: [number, number, number][]; // x, y, 種類
  packs: number[];         // 次のウェーブで降るパック（レア度）。中身は買ったときに決める前提
  settings: { ringOffset: number; sound: boolean };
  savedAt: number;         // 保存した時刻（ms）。ゲームの計算には使わない
}

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

// JSON は Infinity と NaN を null にしてしまう。数の上限をこえた値を、こわさずに往復させる
const replacer = (_k: string, v: unknown) => (typeof v === 'number' && !Number.isFinite(v) ? { $n: String(v) } : v);
const reviver = (_k: string, v: any) => (v && typeof v === 'object' && typeof v.$n === 'string' && Object.keys(v).length === 1 ? Number(v.$n) : v);

export function exportText(s: SaveData): string {
  const json = JSON.stringify(s, replacer);
  return `${PREFIX}.${b64urlEncode(json)}.${fnv1a(json)}`;
}

export function importText(text: string): SaveData {
  const parts = text.trim().split('.');
  if (parts.length !== 3 || parts[0] !== PREFIX) throw new Error('書き出しの形が違う（版が違うか、途中で切れている）');
  let json: string;
  try { json = b64urlDecode(parts[1]); } catch { throw new Error('文字が壊れている'); }
  if (fnv1a(json) !== parts[2]) throw new Error('指紋が合わない（文字が欠けたか、書き換えられた）');
  const s = JSON.parse(json, reviver) as SaveData;
  if (s.v !== 1) throw new Error(`知らない版：${s.v}`);
  return s;
}

export interface Store { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }

/** 書けたら true。容量オーバーなどで書けなかったら false（ゲームは止めず、書き出しを促す） */
export function saveLocal(store: Store, s: SaveData): boolean {
  try {
    const old = store.getItem(SAVE_KEY);
    if (old) store.setItem(PREV_KEY, old);
    store.setItem(SAVE_KEY, exportText(s));
    return true;
  } catch { return false; }
}

export function loadLocal(store: Store): SaveData | null {
  for (const k of [SAVE_KEY, PREV_KEY]) {
    const t = store.getItem(k);
    if (!t) continue;
    try { return importText(t); } catch { /* 次の候補へ */ }
  }
  return null;
}
