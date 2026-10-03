// Astro config of the rtx3090fe-model-tests site.
// Static output for GitHub Pages under the project path /rtx3090fe-model-tests.
// Data is read at build time from ../data (see src/lib/data.ts); nothing is
// fetched at runtime and no external request is made by any page.
import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import sitemap from './integrations/sitemap.mjs';
import labGuard from './integrations/lab-guard.mjs';

const SITE_DIR = path.dirname(fileURLToPath(import.meta.url));
// The repository root (parent of site/). data.ts reads ../data, ../methodology,
// ../benches and ../evidence from here. Override with RTX_REPO_ROOT to build
// against another tree (e.g. a staging export).
process.env.RTX_REPO_ROOT ??= path.resolve(SITE_DIR, '..');

export default defineConfig({
  site: 'https://florent-pro-ch.github.io',
  base: '/rtx3090fe-model-tests',
  trailingSlash: 'always',
  output: 'static',
  build: { format: 'directory' },
  // Every page is plain HTML; the only scripts are two tiny inline ones in the
  // layout (theme toggle, table sort/filter).
  devToolbar: { enabled: false },
  integrations: [sitemap(), labGuard()],
});
