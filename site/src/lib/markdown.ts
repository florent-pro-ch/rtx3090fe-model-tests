/**
 * Markdown for bench cards (benches/<id>/CARD.md), methodology/*.md and
 * CHANGELOG.md, rendered at build time with `marked`.
 *
 * Why marked rather than Astro's own markdown: these files live outside
 * site/src and are read as strings from ../ at build time; marked is one
 * dependency-free package with a synchronous string -> HTML call, and keeps
 * the site independent of Astro's internal markdown pipeline. The sources
 * are the repository's own reviewed files, not user input.
 *
 * Relative links are rewritten: methodology/*.md -> /methodology/<doc>/
 * (methodology/PITFALLS.md -> /pitfalls/),
 * benches/<id>/CARD.md -> /benches/<id>/, CHANGELOG.md -> /changelog/, any
 * other repo file -> its page on GitHub. Images become links (no runtime
 * request to another host). Tables are wrapped so they scroll in place.
 */
import { Marked } from 'marked';
import path from 'node:path';
import { githubUrl, slugify } from './data';
import { href } from './site';

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
}

function headingId(text: string): string {
  return (
    text
      .replace(/<[^>]+>/g, '')
      .toLowerCase()
      .replace(/&[a-z]+;/g, '')
      .replace(/[^\p{L}\p{N}\s-]/gu, '')
      .trim()
      .replace(/\s+/g, '-') || 'section'
  );
}

/** Rewrite one link found in a markdown file whose repo path is docPath. */
export function rewriteLink(link: string, docPath: string): string | null {
  if (!link) return link;
  if (/^(https?:|mailto:|#)/i.test(link)) return link;
  if (link.startsWith('/')) return null; // absolute local paths are never valid in this repo
  const [target, hash] = link.split('#');
  const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(docPath), target));
  if (resolved.startsWith('..')) return null;
  const anchor = hash ? `#${hash}` : '';
  let m = resolved.match(/^methodology\/([^/]+)\.md$/i);
  if (m) {
    const slug = slugify(m[1]);
    if (slug === 'pitfalls') return href('pitfalls/') + anchor;
    // Fragments shown inside pages rather than as documents of their own.
    if (slug === 'headline-rule') return href('methodology/#headline-run-rule');
    if (slug === 'judge-banner' || slug === 'judge-banner-local') return href('methodology/judge/');
    return slug === 'methodology' ? href('methodology/') + anchor : href(`methodology/${slug}/`) + anchor;
  }
  m = resolved.match(/^benches\/(.+)\/CARD\.md$/i);
  if (m) return href(`benches/${m[1]}/`) + anchor;
  if (/^CHANGELOG\.md$/i.test(resolved)) return href('changelog/') + anchor;
  if (/^GLOSSARY\.md$/i.test(resolved)) return href('glossary/') + anchor;
  return githubUrl(resolved) + anchor;
}

export function renderMarkdown(md: string, docPath: string): string {
  const marked = new Marked({
    gfm: true,
    walkTokens(token) {
      if (token.type === 'link') {
        const r = rewriteLink(token.href, docPath);
        (token as { href: string }).href = r ?? '';
      }
    },
    renderer: {
      heading({ tokens, depth }) {
        const inner = this.parser.parseInline(tokens);
        return `<h${depth} id="${headingId(inner)}">${inner}</h${depth}>\n`;
      },
      link({ href: h, title, tokens }) {
        const inner = this.parser.parseInline(tokens);
        if (!h) return `<span>${inner}</span>`;
        const ext = /^https?:/i.test(h) ? ' rel="noopener"' : '';
        return `<a href="${escapeHtml(h)}"${title ? ` title="${escapeHtml(title)}"` : ''}${ext}>${inner}</a>`;
      },
      image({ href: h, text }) {
        const r = rewriteLink(h, docPath);
        const label = `${escapeHtml(text || 'figure')} (figure)`;
        return r ? `<a href="${escapeHtml(r)}">${label}</a>` : `<span>${label}</span>`;
      },
    },
  });
  const html = marked.parse(md, { async: false }) as string;
  return html.replace(/<table>/g, '<div class="table-wrap"><table>').replace(/<\/table>/g, '</table></div>');
}
