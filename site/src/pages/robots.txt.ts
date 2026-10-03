// robots.txt. Note: a project site lives under /rtx3090fe-model-tests/, and
// crawlers only read robots.txt at the host root; this file documents intent
// and points to the sitemap. Model pages without a number carry their own
// <meta name="robots" content="noindex">.
import type { APIRoute } from 'astro';

export const GET: APIRoute = ({ site }) => {
  const base = (import.meta.env.BASE_URL || '/').replace(/\/?$/, '/');
  const sitemap = new URL(`${base}sitemap.xml`, site).href;
  return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${sitemap}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
