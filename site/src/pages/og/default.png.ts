/**
 * The site's default Open Graph card, /og/default.png, 1200 × 630: the
 * composition of the repository's social preview (figures/specs/
 * social-preview.json), rendered at build time from data/.
 */
import type { APIRoute } from 'astro';
import { defaultOgSvg } from '../../lib/og/social';
import { OG_BUDGET, renderPng } from '../../lib/og/render';

export const GET: APIRoute = () => {
  const png = renderPng(defaultOgSvg().svg);
  if (png.length > OG_BUDGET) throw new Error(`og: default.png is ${png.length} bytes, over the ${OG_BUDGET}-byte budget`);
  return new Response(new Uint8Array(png), { headers: { 'Content-Type': 'image/png' } });
};
