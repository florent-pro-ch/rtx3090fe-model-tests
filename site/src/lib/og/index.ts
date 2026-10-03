/**
 * What a page needs to point at its Open Graph card: the image path (under
 * the site base) and its alt text. Wire it in the layout's <head> as
 *   <meta property="og:image" content={new URL(ogImage(slug), Astro.site)} />
 *   <meta property="og:image:width" content="1200" /> <meta property="og:image:height" content="630" />
 *   <meta property="og:image:alt" content={ogAlt(m)} /> <meta name="twitter:card" content="summary_large_image" />
 * with ogImage() (no slug) for every other page.
 */
import type { Model } from '../data';
import { href } from '../site';
import { modelOgAlt, OG_W, OG_H } from './model';
import { defaultOgSvg } from './social';

export { OG_W, OG_H };
export const ogImage = (slug?: string) => href(`og/${slug ?? 'default'}.png`);
export const ogAlt = (m?: Model) => (m ? modelOgAlt(m) : defaultOgSvg().alt);
