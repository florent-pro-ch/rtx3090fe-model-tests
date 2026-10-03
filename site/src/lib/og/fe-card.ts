/**
 * The RTX 3090 Founders Edition card motif of DESIGN.md (Motifs), drawn at the
 * geometry of the design file's component "Illustration/RTX 3090 FE pair"
 * (Components page, node 21:87, 660 × 406): two cards seen from the front, one
 * behind the other, joined across their top edges by the NVLink bridge.
 *
 * One card (feCard) is 580.4 × 283 at scale 1, in the component's coordinates
 * minus its group origin: the side and top edges in perspective with the plain
 * lettering "GEFORCE RTX 3090", the angled frame (a --muted rim round a
 * --border face) cut by the slanted divider, the front fan on the left, the
 * flow-through fin stack over the rear fan on the right, the I/O bracket and
 * the PCIe contacts. Flat shapes in the DESIGN.md tokens only: no gradient, no
 * shadow, no logo.
 */
import { c, circle, f, group, rect, text, type TextStyle } from './draw';
import { autoLineHeight, baseline } from './fonts';
import type { TokenName } from './tokens';

interface PathStyle {
  fill?: TokenName;
  stroke?: TokenName;
  sw?: number;
  /** whole-shape opacity (Figma layer opacity) */
  opacity?: number;
  /** round joins, as the component's polygons */
  round?: boolean;
}

function path(d: string, st: PathStyle): string {
  const fill = st.fill ? c(st.fill) : 'none';
  const stroke = st.stroke ? ` stroke="${c(st.stroke)}" stroke-width="${f(st.sw ?? 1)}"${st.round ? ' stroke-linejoin="round"' : ''}` : '';
  const op = st.opacity !== undefined && st.opacity < 1 ? ` opacity="${st.opacity}"` : '';
  return `<path d="${d}" fill="${fill}"${stroke}${op}/>`;
}

/** One line of text whose box starts at `top` with the face's natural ("auto") line height. */
function textAuto(x: number, top: number, s: string, st: TextStyle): string {
  return text(x, baseline(top, st.size, autoLineHeight(st.face), st.face), s, st);
}

/** The nine blades of a fan (Figma 21:21–21:29), centred on (151, 154) in card coordinates. */
const BLADES = [
  'M180.4 154C200.87 159.53 217.2 175.57 229.4 202.1C222.44 213.47 213.09 223.2 202 230.6C193.13 211.27 185.5 188.67 179.1 162.8L180.4 154Z',
  'M173.6 172.9C185.67 190.3 187.87 213.1 180.2 241.3C167.55 245.5 154.14 246.9 140.9 245.4C146.5 224.93 155.17 202.73 166.9 178.8L173.6 172.9Z',
  'M156.1 183C154.17 204.13 141.23 223 117.3 239.6C104.89 234.7 93.7 227.16 84.5 217.5C101.97 205.43 122.87 194 147.2 183.2L156.1 183Z',
  'M136.3 179.5C121.23 194.43 99.17 200.57 70.1 197.9C63.76 186.17 60.04 173.21 59.2 159.9C80.33 161.9 103.7 166.57 129.3 173.9L136.3 179.5Z',
  'M123.3 164.1C102.17 165.9 81.37 156.4 60.9 135.6C63.56 122.55 69.02 110.23 76.9 99.5C91.83 114.63 106.73 133.27 121.6 155.4L123.3 164.1Z',
  'M123.3 143.9C105.97 131.7 96.1 111.07 93.7 82C104.13 73.7 116.25 67.76 129.2 64.6C130.93 85.8 130.4 109.63 127.6 136.1L123.3 143.9Z',
  'M136.3 128.5C130.83 107.97 136.53 85.8 153.4 62C166.74 62.34 179.84 65.59 191.8 71.5C179.47 88.83 163.73 106.77 144.6 125.3L136.3 128.5Z',
  'M156.1 125C165.1 105.8 183.73 92.5 212 85.1C221.95 93.93 229.86 104.81 235.2 117C214.67 122.4 191.1 126.03 164.5 127.9L156.1 125Z',
  'M173.6 135.1C192.8 126.17 215.6 127.93 242 140.4C243.96 153.57 243.04 167.02 239.3 179.8C220.1 170.73 199.73 158.37 178.2 142.7L173.6 135.1Z',
] as const;

/** The rear fan sits 283.5 to the right of the front one (Figma 21:33–21:42). */
const REAR_FAN_DX = 283.5;

/** Tops of the fin-stack slats that meet the slanted divider (Figma 21:43); the rest run full height. */
const FIN_TOPS = [191.4, 161.9, 132.5, 103, 73.6, 44.1, 14.7];
const FINS = 34;

export const FE_CARD = { w: 580.4, h: 283 } as const;
export const FE_LETTERING = 'GEFORCE RTX 3090';

/** One RTX 3090 Founders Edition card, 580.4 × 283 at scale 1 (Figma group 21:48 of 21:87). */
export function feCard(): string {
  let s = '';
  // side and top edges, in perspective
  s += path('M556 36L580.4 0V236L556 272Z', { fill: 'panel2', stroke: 'border', sw: 1.5, round: true });
  s += path('M16 36H556L580.4 0H40.4Z', { fill: 'panel', stroke: 'border', sw: 1.5, round: true });
  s += path('M87.6 25.9H303.6L314.3 10.1H98.3Z', { fill: 'bg' });
  // the angled frame: a --muted rim round a --border face
  s += rect(16, 36, 540, 236, { fill: 'muted', rx: 14 });
  s += rect(19, 39, 534, 230, { fill: 'border', rx: 12 });
  // front fan
  s += path('M28 48H318.4L264.4 260H28Z', { fill: 'bg', stroke: 'muted', sw: 1.5, round: true });
  s += circle(151, 154, 99, { fill: 'panel', stroke: 'muted', sw: 2.5 });
  for (const d of BLADES) s += path(d, { fill: 'border' });
  s += circle(151, 154, 29.4, { fill: 'panel2', stroke: 'muted', sw: 2 });
  // flow-through fin stack over the rear fan
  s += path('M338.4 48H544V260H284.4Z', { fill: 'panel2', stroke: 'muted', sw: 1.5, round: true });
  s += circle(434.5, 154, 96, { fill: 'panel' });
  s += group(BLADES.map((d) => path(d, { fill: 'muted', opacity: 0.8 })).join(''), REAR_FAN_DX, 0);
  s += circle(434.5, 154, 29.4, { fill: 'muted', stroke: 'muted', sw: 2 });
  let fins = '';
  for (let i = 0; i < FINS; i++) {
    const top = FIN_TOPS[i] ?? 0;
    fins += `M${f(289.4 + 7.5 * i)} ${f(49 + top)}h3.6V259h-3.6Z`;
  }
  s += path(fins, { fill: 'bg' });
  // I/O bracket with its vents, PCIe connector with its contacts
  s += rect(0, 14, 13, 266, { fill: 'muted', rx: 2 });
  let vents = '';
  for (let i = 0; i < 6; i++) vents += `M3.5 ${f(44 + 34 * i)}h6v24h-6Z`;
  s += path(vents, { fill: 'border' });
  s += rect(70, 272, 226.8, 11, { fill: 'border' });
  let pins = '';
  for (let i = 0; i < 37; i++) pins += `M${f(74 + 6 * i)} 275h3v8h-3Z`;
  s += path(pins, { fill: 'panel2' });
  // lettering on the top edge (Figma: Inter Bold 10, tracking 22 %; drawn in the nearest self-hosted weight)
  s += textAuto(201, 12, FE_LETTERING, { face: 'sans600', size: 10, fill: 'text', anchor: 'middle', ls: 2.2 });
  return s;
}

/** Placement of the two cards and the bridge in the pair (Figma 21:87). */
export const FE_PAIR = {
  w: 660,
  h: 406,
  back: [49.3, 61.9],
  front: [14, 114],
  /** where the bridge label's text box starts (Figma 21:179, relative to the pair) */
  label: [560, 38],
  labelSize: 22,
} as const;

/** The NVLink bridge seen in the pair's perspective (Figma 21:83–21:86): front, side, top, inset. */
function feBridge(): string {
  return (
    rect(412.2, 127.8, 86.4, 16, { fill: 'blue' }) +
    path('M498.6 143.8L549.8 68.2V52.2L498.6 127.8Z', { fill: 'blue', opacity: 0.6 }) +
    path('M412.2 127.8H498.6L549.8 52.2H463.4Z', { fill: 'blue' }) +
    path('M428.1 119.1H494.5L534 60.8H467.6Z', { fill: 'bg', opacity: 0.35 })
  );
}

/**
 * The pair, 660 × 406 at scale 1: the back card, the front card, the bridge
 * across their top edges and, when `label` is given, its word in mono --blue
 * beside the bridge (DESIGN.md: NVLink is --blue).
 */
export function fePair(label: string | null = 'NVLink'): { svg: string; w: number; h: number } {
  const P = FE_PAIR;
  let svg = group(feCard(), P.back[0], P.back[1]) + group(feCard(), P.front[0], P.front[1]) + feBridge();
  if (label) svg += textAuto(P.label[0], P.label[1], label, { face: 'mono400', size: P.labelSize, fill: 'blue' });
  return { svg, w: P.w, h: P.h };
}
