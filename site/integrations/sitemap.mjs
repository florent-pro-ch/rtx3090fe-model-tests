// A minimal sitemap writer (no dependency): after the build, walk dist/ for
// every index.html, skip the pages that carry <meta name="robots" content="noindex">
// (models with no numeric run, the 404 page), and write dist/sitemap.xml.
// Reading the rendered HTML means the sitemap can never disagree with the
// pages' own robots meta, which @astrojs/sitemap's route filter could.
import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const NOINDEX = /<meta\s+name="robots"\s+content="[^"]*noindex/i;

async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await walk(full)));
    else if (entry.name === 'index.html') out.push(full);
  }
  return out;
}

export default function sitemap() {
  let site = '';
  let base = '/';
  return {
    name: 'local-sitemap',
    hooks: {
      'astro:config:done': ({ config }) => {
        site = String(config.site || '').replace(/\/$/, '');
        base = (config.base || '/').replace(/\/?$/, '/');
      },
      'astro:build:done': async ({ dir, logger }) => {
        const root = fileURLToPath(dir);
        const files = (await walk(root)).sort();
        const urls = [];
        let skipped = 0;
        for (const file of files) {
          const html = await readFile(file, 'utf8');
          if (NOINDEX.test(html)) { skipped += 1; continue; }
          const rel = path.relative(root, path.dirname(file)).split(path.sep).join('/');
          const loc = site + base + (rel ? rel.split('/').map(encodeURIComponent).join('/') + '/' : '');
          urls.push(loc);
        }
        const xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
          + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + urls.map((u) => `  <url><loc>${u}</loc></url>`).join('\n')
          + (urls.length ? '\n' : '') + '</urlset>\n';
        await writeFile(path.join(root, 'sitemap.xml'), xml, 'utf8');
        logger.info(`sitemap.xml: ${urls.length} URLs (${skipped} noindex pages left out)`);
      },
    },
  };
}
