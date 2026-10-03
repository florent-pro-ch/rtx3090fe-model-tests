/**
 * The colour tokens of DESIGN.md, read from its "Theme" table at build time,
 * so the generated images (OG cards, README banner, social preview) use the
 * same eleven colours as the site and nothing else.
 *
 * `swapToLight` is the DESIGN.md token swap: every dark hex of the table is
 * replaced by its light counterpart, once, in a single pass. A figure's light
 * variant is always made this way from its dark one, never drawn separately.
 */
import fs from 'node:fs';
import path from 'node:path';
import { ROOT } from '../data';

export const TOKEN_NAMES = ['bg', 'panel', 'panel2', 'border', 'text', 'muted', 'green', 'blue', 'amber', 'red', 'grid'] as const;
export type TokenName = (typeof TOKEN_NAMES)[number];
export type Palette = Record<TokenName, string>;

const ROW = /^\|\s*`--([a-z0-9]+)`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|/;

function readTokens(): { dark: Palette; light: Palette } {
  const file = path.join(ROOT, 'DESIGN.md');
  const text = fs.readFileSync(file, 'utf8');
  const dark: Partial<Palette> = {};
  const light: Partial<Palette> = {};
  for (const line of text.split('\n')) {
    const m = ROW.exec(line);
    if (!m) continue;
    const name = m[1] as TokenName;
    if (!(TOKEN_NAMES as readonly string[]).includes(name)) continue;
    dark[name] = m[2].toLowerCase();
    light[name] = m[3].toLowerCase();
  }
  const missing = TOKEN_NAMES.filter((n) => !dark[n] || !light[n]);
  if (missing.length) throw new Error(`og/tokens: DESIGN.md lacks the token(s) ${missing.join(', ')}`);
  const darkValues = new Set(Object.values(dark));
  if (darkValues.size !== TOKEN_NAMES.length) throw new Error('og/tokens: two dark tokens share a value; the swap would be ambiguous');
  return { dark: dark as Palette, light: light as Palette };
}

let cache: { dark: Palette; light: Palette } | null = null;
export function tokens(): { dark: Palette; light: Palette } {
  cache ??= readTokens();
  return cache;
}

/** Dark palette: every figure is drawn in it first. */
export function dark(): Palette {
  return tokens().dark;
}

const HEX = /#[0-9a-fA-F]{6}\b/g;

/** Every #rrggbb of an SVG that is not a dark token (for the self-check). */
export function foreignColours(svg: string, pal: Palette): string[] {
  const allowed = new Set(Object.values(pal));
  return [...new Set((svg.match(HEX) ?? []).map((h) => h.toLowerCase()))].filter((h) => !allowed.has(h));
}

/** The DESIGN.md token swap: dark hex to light hex, one pass. Fails on a colour that is not a token. */
export function swapToLight(svg: string): string {
  const { dark: d, light: l } = tokens();
  const foreign = foreignColours(svg, d);
  if (foreign.length) throw new Error(`og/tokens: colour(s) outside the DESIGN.md tokens: ${foreign.join(', ')}`);
  const map = new Map<string, string>(TOKEN_NAMES.map((n) => [d[n], l[n]]));
  return svg.replace(HEX, (h) => map.get(h.toLowerCase()) ?? h);
}
