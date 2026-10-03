// Build-time guard for the uncensored-model lab (refusal rates only): after the
// build, the pages of its runs and of their byte copies (labo-* in the
// 2026-09-11/12 watch folders) and its campaign page must show no speed, no
// VRAM, no launch line and no tutoring or code score. The build fails otherwise.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const LAB = '2026-09-05-labo-non-censures';
const COPIES = ['2026-09-11-tests-veille', '2026-09-12-tests-veille'];
const BANNED = [/tok\/s/, /\bMiB\b/, /tuteur\/v1/, /code\/v1/, /docker run/, /id="launch"/];

function pages(dir, keep) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && keep(e.name))
    .map((e) => path.join(dir, e.name, 'index.html'))
    .filter((f) => fs.existsSync(f));
}

export default function labGuard() {
  return {
    name: 'lab-guard',
    hooks: {
      'astro:build:done': ({ dir, logger }) => {
        const root = fileURLToPath(dir);
        const files = [
          ...pages(path.join(root, 'runs', LAB), () => true),
          ...COPIES.flatMap((c) => pages(path.join(root, 'runs', c), (n) => n.startsWith('labo-'))),
          path.join(root, 'campaigns', LAB, 'index.html'),
        ].filter((f) => fs.existsSync(f));
        const bad = [];
        for (const f of files) {
          const html = fs.readFileSync(f, 'utf8').replace(/<script[\s\S]*?<\/script>/g, '');
          for (const re of BANNED) if (re.test(html)) bad.push(`${path.relative(root, f)}: ${re.source}`);
        }
        if (bad.length) throw new Error(`lab-guard: refusal-only pages show other material:\n  ${bad.join('\n  ')}`);
        logger.info(`${files.length} uncensored-lab pages checked: refusal rates only`);
      },
    },
  };
}
