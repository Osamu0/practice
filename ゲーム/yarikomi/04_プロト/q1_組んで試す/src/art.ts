// 仮の絵（四角と線）。色はアートディレクション 3.3 の値。製品の絵ではない。
import { PARTS, type PartId } from './params.ts';
import type { Dir } from './core.ts';

const W = '#EAF0F2', AI = '#1E3A5C', KOI = '#0E1A28';
const MAT: Record<string, string> = { '木': '#B07A4F', '縄・布': '#BFAE8A', '真鍮': '#B39A4E', '石': '#A7A39B', '鉄': '#6C7884' };
const ROT: Record<Dir, number> = { up: 0, east: 90, down: 180, west: 270 };

/** 重さの丸：数は重さそのまま、3個ごとに区切る（部品と素材.md 3.1） */
function dots(n: number) {
  let s = '';
  let x = 44;
  for (let i = 0; i < n; i++) {
    if (i > 0 && i % 3 === 0) x -= 3;
    s += `<circle cx="${x}" cy="44" r="2.1" fill="${W}" stroke="${KOI}" stroke-width=".6"/>`;
    x -= 4.6;
  }
  return s;
}
function wearMarks(w: number) {
  let s = '';
  if (w >= 1) s += `<path d="M30 14 l4 6 -3 3" stroke="${W}" stroke-width="1.2" fill="none"/>`;
  if (w >= 2) s += `<path d="M14 30 l5 3 -2 5" stroke="${W}" stroke-width="1.2" fill="none"/><path d="M6 6 l5 0 -5 5z" fill="${AI}"/>`;
  return s;
}

function body(part: PartId): string {
  const c = MAT[PARTS[part].material];
  switch (part) {
    case 'plank':
      return `<rect x="3" y="15" width="42" height="18" rx="1" fill="${AI}" stroke="${W}" stroke-width="2"/>
        <rect x="5" y="17" width="38" height="6" fill="${c}"/><path d="M8 28 H40" stroke="${W}" stroke-width="1"/>`;
    case 'ironBar':
      return `<rect x="3" y="16" width="42" height="16" fill="${c}" stroke="${W}" stroke-width="2"/>
        <circle cx="9" cy="24" r="2" fill="${W}"/><circle cx="39" cy="24" r="2" fill="${W}"/>`;
    case 'spring':
    case 'ironSpring': {
      const sw = part === 'ironSpring' ? 3.2 : 2;
      return `<rect x="8" y="38" width="32" height="6" fill="${c}" stroke="${W}" stroke-width="2"/>
        <polyline points="24,38 14,33 34,27 14,21 34,15 24,11" fill="none" stroke="${W}" stroke-width="${sw}"/>
        <rect x="10" y="5" width="28" height="6" fill="${c}" stroke="${W}" stroke-width="2"/>
        ${part === 'ironSpring' ? `<circle cx="13" cy="41" r="1.5" fill="${W}"/><circle cx="35" cy="41" r="1.5" fill="${W}"/>` : ''}
        <path d="M24 1 l4 4 h-8z" fill="${W}"/>`;
    }
    case 'stoneWeight':
      return `<path d="M18 12 a6 5 0 0 1 12 0" fill="none" stroke="${W}" stroke-width="2"/>
        <rect x="8" y="12" width="32" height="28" rx="7" fill="${c}" stroke="${W}" stroke-width="2"/>
        <circle cx="18" cy="24" r="1.6" fill="${KOI}"/><circle cx="28" cy="30" r="1.6" fill="${KOI}"/>`;
    case 'ironWeight':
      return `<path d="M19 10 a5 5 0 0 1 10 0" fill="none" stroke="${W}" stroke-width="2"/>
        <path d="M13 10 H35 L43 40 H5 Z" fill="${c}" stroke="${W}" stroke-width="2"/>
        <circle cx="13" cy="35" r="1.8" fill="${W}"/><circle cx="35" cy="35" r="1.8" fill="${W}"/>`;
    case 'pebble':
      return `<ellipse cx="24" cy="32" rx="11" ry="9" fill="${c}" stroke="${W}" stroke-width="2"/><circle cx="21" cy="30" r="1.3" fill="${KOI}"/>`;
    case 'sandbag':
      return `<path d="M17 10 L31 10 L28 16 C42 20 42 40 34 41 H14 C6 40 6 20 20 16 Z" fill="${c}" stroke="${W}" stroke-width="2"/>
        <path d="M14 26 l4 -4 M20 30 l4 -4 M26 34 l4 -4" stroke="${KOI}" stroke-width="1"/>`;
  }
}

export function partSVG(part: PartId, size: number, facing?: Dir, wear = 0): string {
  const rot = PARTS[part].springPower !== undefined ? ROT[facing ?? 'up'] : 0;
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" aria-label="${PARTS[part].name}">
    <g transform="rotate(${rot} 24 24)">${body(part)}</g>${wearMarks(wear)}${dots(PARTS[part].weight)}</svg>`;
}

export function leaderSVG(size: number, doll = false): string {
  const dash = doll ? 'stroke-dasharray="3 2"' : '';
  const fill = doll ? '#284A70' : '#F2B544';
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" aria-label="${doll ? '人形' : '当主'}">
    <circle cx="24" cy="12" r="8" fill="${doll ? fill : '#FCE3A6'}" stroke="${doll ? W : KOI}" stroke-width="2.5" ${dash}/>
    <path d="M12 44 L15 24 Q24 18 33 24 L36 44 Z" fill="${fill}" stroke="${doll ? W : KOI}" stroke-width="2.5" ${dash}/>
    ${doll ? '' : `<rect x="19" y="28" width="10" height="12" fill="#FCE3A6"/><circle cx="21" cy="12" r="1.3" fill="${KOI}"/><circle cx="27" cy="12" r="1.3" fill="${KOI}"/>`}
    <circle cx="44" cy="44" r="2.1" fill="${W}"/><circle cx="39.4" cy="44" r="2.1" fill="${W}"/><circle cx="34.8" cy="44" r="2.1" fill="${W}"/></svg>`;
}

export function goalSVG(size: number): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" aria-label="印">
    <rect x="3" y="3" width="42" height="42" fill="none" stroke="#D2A48C" stroke-width="2" stroke-dasharray="5 4"/>
    <path d="M16 42 V8" stroke="#D2A48C" stroke-width="2.5"/><path d="M16 8 L34 13 L16 19 Z" fill="#D2A48C"/></svg>`;
}

/** 道具の小さな絵（持ち物の表示） */
export function toolSVG(cells: [number, number, PartId, Dir | null][], cell: number): string {
  if (!cells.length) return '';
  const w = Math.max(...cells.map(c => c[0])) + 1, h = Math.max(...cells.map(c => c[1])) + 1;
  return `<div style="position:relative;width:${w * cell}px;height:${h * cell}px">${cells.map(([x, y, p, f]) =>
    `<div style="position:absolute;left:${x * cell}px;top:${y * cell}px">${partSVG(p, cell, f ?? undefined)}</div>`).join('')}</div>`;
}
