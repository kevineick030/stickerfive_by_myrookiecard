/* Schicht B, Ausgabestufe: den Renderplan im Browser rastern.
 *
 * Verlauf, Praegung und weicher Schatten sind im Browser eingebaut und
 * brauchen keine Handarbeit. Derselbe Weg liefert spaeter die Druck-PDF in
 * exakten Millimetern, und dieselbe Datei kann als Kundenvorschau dienen -
 * Vorschau und Druck kommen dann nicht nur aus derselben Quelle, sondern
 * aus demselben Renderer.
 *
 *   node tools/render.mjs out/plan/*.json --out out/karten
 */
import { chromium } from '/tmp/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const args = process.argv.slice(2);
const outIdx = args.indexOf('--out');
const ziel = outIdx >= 0 ? args[outIdx + 1] : 'out/karten';
const pdf = args.includes('--pdf');
const plaene = args.filter((a, i) => a.endsWith('.json') && (outIdx < 0 || i !== outIdx + 1));
fs.mkdirSync(ziel, { recursive: true });

// setContent laeuft auf about:blank - von dort sind file://-Adressen
// gesperrt. Deshalb wandern Vorlage, Spieler und Schriften als Daten-URL
// in die Seite. Bei einer Karte sind das ein paar Megabyte, lokal egal.
const b64 = p => fs.readFileSync(p).toString('base64');
const typ = p => ({ '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp' }[path.extname(p).toLowerCase()] || 'image/png');
const datei = p => `data:${typ(p)};base64,${b64(p)}`;

function seite(plan) {
  const [B, H] = plan.trim;
  const fonts = Object.entries(plan.schriften).map(([n, p]) =>
    `@font-face{font-family:"${n}";src:url(data:font/ttf;base64,${b64(p)}) format("truetype");}`).join('');

  const p = plan.placements;
  const foto = p.find(x => x.slot === 'photo');
  const [ox, oy] = foto.offset_mm, [pw, ph] = foto.placed_size_mm;
  const fb = foto.box_mm;

  const flecken = (plan.patches || []).map(o => {
    const s = o.source_offset || { dx: 0, dy: 0 };
    return `<div class="stueck" style="left:${o.box.x}mm;top:${o.box.y}mm;width:${o.box.w}mm;
      height:${o.box.h}mm;background-position:${-(o.box.x + s.dx)}mm ${-(o.box.y + s.dy)}mm"></div>`;
  }).join('');
  const decken = (plan.overlays || []).map(o =>
    `<div class="stueck" style="left:${o.box.x}mm;top:${o.box.y}mm;width:${o.box.w}mm;
      height:${o.box.h}mm;background-position:${-o.box.x}mm ${-o.box.y}mm"></div>`).join('');

  // Text als SVG: dort ist die Grundlinie eine echte Koordinate (y), und ein
  // Verlauf laesst sich ueber die Glyphen legen, ohne dass die Zeile eine
  // Kastenhoehe braucht. Als HTML-Element scheiterte genau daran der erste
  // Versuch - line-height:0 laesst den Verlaufskasten auf null zusammenfallen
  // und der Text verschwindet.
  const verlaeufe = [], zeilen = [];
  p.filter(x => x.type === 'text' && x.text).forEach((x, n) => {
    const f = plan.farben[x.slot] || '#ffffff';
    const groesse = x.size_pt * 25.4 / 72;
    const spur = (x.letter_spacing_em || 0) * groesse;
    let fuellung = f;
    if (Array.isArray(f)) {
      verlaeufe.push(`<linearGradient id="v${n}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${f[0]}"/><stop offset=".42" stop-color="${f[1]}"/>
        <stop offset="1" stop-color="${f[2]}"/></linearGradient>`);
      fuellung = `url(#v${n})`;
    }
    const anker = { center: 'middle', right: 'end', left: 'start' }[x.align] || 'start';
    const tief = (x.slot === 'jersey_number' || x.slot === 'serial')
      ? ` filter="drop-shadow(0 ${(groesse * 0.05).toFixed(3)}mm ${(groesse * 0.055).toFixed(3)}mm rgba(6,9,16,.75))"`
      : '';
    x.lines.forEach((zeile, i) => zeilen.push(
      `<text x="${x.anchor_x_mm}" y="${x.baselines_mm[i]}" text-anchor="${anker}"
        font-family="${x.font}" font-size="${groesse.toFixed(3)}"
        letter-spacing="${spur.toFixed(3)}" fill="${fuellung}"${tief}
        >${zeile.replace(/[<&]/g, c => ({ '<': '&lt;', '&': '&amp;' }[c]))}</text>`));
  });
  const texte = `<svg class="satz" viewBox="0 0 ${B} ${H}" xmlns="http://www.w3.org/2000/svg">
    <defs>${verlaeufe.join('')}</defs>${zeilen.join('')}</svg>`;

  return `<!doctype html><meta charset="utf-8"><style>
    ${fonts}
    *{margin:0;padding:0;box-sizing:border-box}
    html,body{width:${B}mm;height:${H}mm;overflow:hidden;background:#000}
    .karte{position:relative;width:${B}mm;height:${H}mm;overflow:hidden}
    .karte>img.grund{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
    .fenster{position:absolute;left:${fb.x}mm;top:${fb.y}mm;width:${fb.w}mm;height:${fb.h}mm;
      overflow:hidden}
    .fenster img{position:absolute;left:${ox - fb.x}mm;top:${oy - fb.y}mm;
      width:${pw}mm;height:${ph}mm}
    .stueck{position:absolute;background-image:url("${datei(plan.vorlage)}");
      background-size:${B}mm ${H}mm;background-repeat:no-repeat}
    .satz{position:absolute;inset:0;width:${B}mm;height:${H}mm;overflow:visible}
    .satz text{font-weight:800;paint-order:stroke fill}
  </style>
  <div class="karte">
    <img class="grund" src="${datei(plan.vorlage)}">
    <div class="fenster"><img src="${datei(plan.spieler)}"></div>
    ${decken}${flecken}${texte}
  </div>`;
}

const browser = await chromium.launch({ executablePath: CHROME });
for (const datei_ of plaene) {
  const plan = JSON.parse(fs.readFileSync(datei_, 'utf8'));
  const [B, H] = plan.trim;
  const seiteMm = mm => Math.round(mm / 25.4 * 96);
  const pg = await browser.newPage({
    viewport: { width: seiteMm(B), height: seiteMm(H) },
    deviceScaleFactor: plan.dpi / 96,
  });
  await pg.setContent(seite(plan), { waitUntil: 'load' });
  await pg.evaluate(() => document.fonts.ready);
  const ausgabe = path.join(ziel, plan.id + '.png');
  await pg.screenshot({ path: ausgabe });
  if (pdf) await pg.pdf({ path: path.join(ziel, plan.id + '.pdf'), width: `${B}mm`, height: `${H}mm`, printBackground: true });
  const px = Math.round(B / 25.4 * plan.dpi);
  console.log(`${plan.id}.png  ${px} px breit  ${plan.gesperrt ? 'GESPERRT' : 'ok'}  ${plan.befunde.length} Befund(e)`);
  await pg.close();
}
await browser.close();
