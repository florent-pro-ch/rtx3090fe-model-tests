/**
 * Open Graph card of every model page: /og/<slug>.png, 1200 × 630, rendered
 * at build time from the SVG template of src/lib/og/model.ts with resvg and
 * the self-hosted fonts (site/fonts-og/). Every number comes from data/
 * through src/lib/data.ts, as on the model page.
 */
import type { APIRoute, GetStaticPaths } from 'astro';
import type { Model } from '../../lib/data';
import { models } from '../../lib/data';
import { modelOgSvg } from '../../lib/og/model';
import { OG_BUDGET, renderPng } from '../../lib/og/render';

export const getStaticPaths = (() => {
  const list = models();
  if (list.some((m) => m.slug === 'default')) throw new Error('og: a model slug collides with og/default.png');
  return list.map((m) => ({ params: { slug: m.slug }, props: { m } }));
}) satisfies GetStaticPaths;

export const GET: APIRoute = ({ props }) => {
  const { m } = props as { m: Model };
  const png = renderPng(modelOgSvg(m));
  if (png.length > OG_BUDGET) throw new Error(`og: ${m.slug}.png is ${png.length} bytes, over the ${OG_BUDGET}-byte budget`);
  return new Response(new Uint8Array(png), { headers: { 'Content-Type': 'image/png' } });
};
