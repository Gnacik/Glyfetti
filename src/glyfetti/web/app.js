'use strict';
const $ = id => document.getElementById(id);
function titleMode() { return $('output-mode').value === 'title'; }
function syncMode() {
  const title = titleMode(); $('atlas-options').hidden = title; $('title-options').hidden = !title;
  $('export').textContent = title ? 'Export title PNG ↗' : 'Export atlas ZIP ↗';
  $('export-description').textContent = title ? 'One transparent image. A shared outline, shadow and 3D finish across your whole title.' : 'Transparent atlas, BMFont metrics, Unity JSON and your style in one ZIP.';
  $('output-note').textContent = title ? 'Title effects and gradients span the complete text. The preview background is not included in your PNG. Save the style JSON to edit this title later.' : 'Preview text characters are added to the exported character set. Missing characters are reported below the preview.';
}
let presets = [], style, token, maxReferenceBytes = 0, timer, rendering = false, pending = false, exporting = false, revision = 0;
const knobs = [
  ['size', 'Size', 16, 180, 1, 'px'], ['outline.width', 'Outline', 0, 20, .5, 'px'],
  ['side.depth', '3D depth', 0, 30, 1, 'px'], ['gloss.opacity', 'Gloss', 0, 1, .01, ''],
  ['shadow.blur', 'Shadow softness', 0, 30, 1, 'px'], ['tracking', 'Letter spacing', -12, 16, 1, 'px'],
  ['condense', 'Width', .5, 1.5, .01, '×']
];
function get(path) { return path.split('.').reduce((v, k) => v?.[k], style); }
function set(path, value) { const keys = path.split('.'); let node = style; for (const k of keys.slice(0, -1)) node = node[k] ||= {}; node[keys.at(-1)] = value; }
function message(text, error = false) { $('status').textContent = text; $('status').dataset.error = String(error); }
function download(data, name) { const url = URL.createObjectURL(data), link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 2000); }
function numberLabel(value) { return Number(Number(value).toFixed(3)); }
function sync() {
  $('title-align').value = style.title?.align || 'center'; $('title-padding').value = style.title?.padding ?? 8; syncMode();
  $('kerning').checked = style.kerning !== false; $('packing').value = style.atlas_packing || 'maxrects';
  $('font').value = style.font; $('text').value = (style.preview || ['Level Complete!']).join('\n');
  $('background').value = style.preview_bg === 'transparent' ? '#f5f1e8' : (style.preview_bg || '#ffffff');
  $('top-color').value = style.fill.stops[0][1]; $('bottom-color').value = style.fill.stops.at(-1)[1]; $('outline-color').value = style.outline.color;
  $('sliders').replaceChildren();
  for (const [path, name, min, max, step, unit] of knobs) {
    const id = path.replace('.', '-'), label = document.createElement('label'), output = document.createElement('output'), input = document.createElement('input');
    label.className = 'range-label'; label.htmlFor = id; label.textContent = name; output.textContent = `${numberLabel(get(path) ?? 0)}${unit}`; label.append(output);
    input.id = id; input.type = 'range'; input.min = min; input.max = max; input.step = step; input.value = get(path) ?? 0;
    input.addEventListener('input', () => {
      if (path === 'side.depth' && !style.side?.color_top) style.side = { depth: 0, dx: 1, color_top: style.fill.stops.at(-1)[1], color_bottom: style.outline.color };
      if (path === 'gloss.opacity' && !style.gloss?.color) style.gloss = { color: '#ffffff', opacity: 0, inset: 2, height: .4, blur: 3 };
      if (path === 'shadow.blur' && !style.shadow?.color) style.shadow = { color: '#000000', opacity: .4, dx: 0, dy: 4, blur: 0 };
      set(path, Number(input.value));
      const layer = path.split('.')[0]; if (['side', 'gloss', 'shadow'].includes(layer)) style[layer].enabled = true;
      output.textContent = `${input.value}${unit}`; schedule();
    });
    $('sliders').append(label, input);
  }
  $('json').value = JSON.stringify(style, null, 2);
}
function schedule() { revision++; pending = true; if (qualityReport) $('quality-state').textContent = 'Style changed. Rerun inspection for current results.'; $('json').value = JSON.stringify(style, null, 2); clearTimeout(timer); timer = setTimeout(preview, 450); }
async function request(endpoint, value) {
  const response = await fetch(`/api/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Glyfetti-Token': token }, body: JSON.stringify(value) });
  if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'Request failed'); }
  return response;
}
async function preview() {
  if (rendering || exporting || !pending) return;
  rendering = true; pending = false; const current = revision; message('Rendering your letters…');
  try {
    const response = await request(titleMode() ? 'title-preview' : 'preview', style), result = await response.json();
    if (current === revision) {
      $('preview').src = result.image; $('preview').hidden = false; $('placeholder').hidden = true;
      const info = result.mode === 'title' ? `${result.size.join(' × ')} PNG · ${result.lines} ${result.lines === 1 ? 'line' : 'lines'} · shared effects` : `${result.glyphs} glyphs · ${result.kernings} kern pairs · ${result.atlas.join(' × ')} · ${result.packing} · ${Math.round(result.occupancy * 100)}% occupied`;
      message(`${info}${result.skipped ? ' · Missing: ' + result.skipped : ''}`, Boolean(result.skipped));
    }
  } catch (error) { if (current === revision) message(error.message, true); }
  finally { rendering = false; if (pending) preview(); }
}
function selectPreset() { style = structuredClone(presets[Number($('preset').value)]); sync(); schedule(); }
$('reference-file').addEventListener('change', () => {
  const file = $('reference-file').files[0];
  $('analyze-reference').disabled = !file || !style;
  $('reference-result').textContent = '';
  if (file) {
    const url = URL.createObjectURL(file);
    const image = $('reference-image');
    if (image.dataset.objectUrl) URL.revokeObjectURL(image.dataset.objectUrl);
    image.dataset.objectUrl = url;
    image.src = url;
    image.hidden = false;
  } else {
    const image = $('reference-image');
    if (image.dataset.objectUrl) URL.revokeObjectURL(image.dataset.objectUrl);
    image.removeAttribute('src');
    delete image.dataset.objectUrl;
    image.hidden = true;
  }
});
function imageAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read reference image.'));
    reader.readAsDataURL(file);
  });
}
$('analyze-reference').addEventListener('click', async () => {
  const file = $('reference-file').files[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > maxReferenceBytes) {
    message(`Choose a PNG/JPG reference smaller than ${maxReferenceBytes / 1048576} MiB.`, true); return;
  }
  $('analyze-reference').disabled = true;
  message('Analyzing reference image locally…');
  try {
    const image = await imageAsDataURL(file);
    const response = await request('reference', { image, style: structuredClone(style) });
    const result = await response.json();
    style = result.style;
    sync(); schedule();
    $('reference-result').textContent = result.analysis.fill_colors.join(' · ') +
      (result.analysis.outline_detected ? ' · Outline: ' + style.outline.color : ' · No outline detected') +
      '. Approximation only; font and effect geometry are unchanged.';
  } catch (error) {
    message(error.message, true);
    $('reference-result').textContent = error.message;
  } finally {
    $('analyze-reference').disabled = false;
  }
});
$('controls').addEventListener('submit', event => event.preventDefault());
$('preset').addEventListener('change', selectPreset); $('reset').addEventListener('click', selectPreset);
$('output-mode').addEventListener('change', () => { syncMode(); schedule(); });
$('title-align').addEventListener('change', () => { style.title ||= {}; style.title.align = $('title-align').value; schedule(); });
$('title-padding').addEventListener('input', () => { style.title ||= {}; style.title.padding = Number($('title-padding').value); schedule(); });
$('font').addEventListener('change', () => { style.font = $('font').value; delete style.variation; schedule(); });
$('kerning').addEventListener('change', () => { style.kerning = $('kerning').checked; schedule(); });
$('packing').addEventListener('change', () => { style.atlas_packing = $('packing').value; schedule(); });
$('use-font').addEventListener('click', () => { const path = $('font-path').value.trim(); if (!path) return; style.font = path; delete style.variation; schedule(); });
$('text').addEventListener('input', () => { style.preview = $('text').value.split('\n'); schedule(); });
for (const [id, change] of [ ['top-color', value => style.fill.stops[0][1] = value], ['bottom-color', value => style.fill.stops.at(-1)[1] = value], ['outline-color', value => style.outline.color = value], ['background', value => style.preview_bg = value] ]) {
  $(id).addEventListener('input', event => { change(event.target.value); schedule(); });
}
function exportStyle() { const result = structuredClone(style); result.chars = [...new Set(result.chars + (result.preview || []).join(''))].join(''); return result; }

let qualityReport = null, qualityAtlas = null, qualitySelected = null, qualityBusy = false;

function qualityChoose(glyph) {
  qualitySelected = glyph.id;
  for (const tile of $('quality-grid').querySelectorAll('button')) tile.classList.toggle('selected', Number(tile.dataset.id) === glyph.id);
  const canvas = $('quality-detail-canvas'), ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const size = Math.max(glyph.w || 1, glyph.h || 1, qualityReport.metrics.size || 1);
  const scale = Math.min(3.5, 175 / size), origin = 70, baseline = 154;
  const top = baseline - qualityReport.metrics.baseline * scale;
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]); ctx.strokeStyle = '#8b8b8b';
  ctx.beginPath(); ctx.moveTo(origin, 8); ctx.lineTo(origin, 232); ctx.stroke();
  ctx.setLineDash([]); ctx.strokeStyle = '#40934b';
  ctx.beginPath(); ctx.moveTo(8, baseline); ctx.lineTo(292, baseline); ctx.stroke();
  ctx.strokeStyle = '#3173b6';
  const advance = origin + (glyph.xa || 0) * scale;
  ctx.beginPath(); ctx.moveTo(advance, 8); ctx.lineTo(advance, 232); ctx.stroke();
  if (qualityAtlas && glyph.w > 0 && glyph.h > 0 && glyph.x >= 0 && glyph.y >= 0 &&
      glyph.x + glyph.w <= qualityAtlas.width && glyph.y + glyph.h <= qualityAtlas.height) {
    ctx.drawImage(qualityAtlas, glyph.x, glyph.y, glyph.w, glyph.h,
      origin + glyph.xo * scale, top + glyph.yo * scale, glyph.w * scale, glyph.h * scale);
  }
  $('quality-metrics').textContent = (glyph.char === ' ' ? 'SPACE' : glyph.char) + '  ' + glyph.codepoint +
    '\nrect: ' + glyph.x + ', ' + glyph.y + ' · ' + glyph.w + ' × ' + glyph.h +
    '\noffset: ' + glyph.xo + ', ' + glyph.yo + '\nadvance: ' + glyph.xa + ' px' +
    '\nbaseline: ' + qualityReport.metrics.baseline + ' px\nline height: ' + qualityReport.metrics.line_height + ' px';
  const notes = qualityReport.issues.filter(item => item.char === glyph.char);
  $('quality-glyph-issues').textContent = notes.length
    ? notes.map(item => item.severity + ': ' + item.message).join('\n') : 'No automated issues detected.';
}

function qualityGrid() {
  if (!qualityReport || !qualityAtlas) return;
  const grid = $('quality-grid'); grid.replaceChildren();
  const query = $('quality-search').value.trim().toLocaleLowerCase(), problematic = $('quality-problems').checked;
  const matches = qualityReport.glyphs.filter(g => (!problematic || g.issues.length) &&
    (!query || g.char.toLocaleLowerCase().includes(query) || g.codepoint.toLocaleLowerCase().includes(query)));
  for (const glyph of matches) {
    const tile = document.createElement('button');
    tile.type = 'button'; tile.dataset.id = glyph.id; tile.className = 'quality-tile';
    tile.title = glyph.codepoint + ' · ' + (glyph.issues.join(', ') || 'No findings');
    if (glyph.issues.length) tile.classList.add('has-issue');
    const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 58;
    if (glyph.w > 0 && glyph.h > 0 && glyph.x >= 0 && glyph.y >= 0 &&
        glyph.x + glyph.w <= qualityAtlas.width && glyph.y + glyph.h <= qualityAtlas.height) {
      const scale = Math.min(60 / glyph.w, 54 / glyph.h, 2.5);
      canvas.getContext('2d').drawImage(qualityAtlas, glyph.x, glyph.y, glyph.w, glyph.h,
        2 + (60 - glyph.w * scale) / 2, 2 + (54 - glyph.h * scale) / 2,
        glyph.w * scale, glyph.h * scale);
    }
    const label = document.createElement('span');
    label.textContent = (glyph.char === ' ' ? '␠' : glyph.char) + ' · ' + glyph.codepoint;
    tile.append(canvas, label);
    tile.addEventListener('click', () => qualityChoose(glyph));
    grid.append(tile);
  }
  if (!matches.length) {
    const note = document.createElement('p'); note.textContent = 'No glyphs match the filters.'; grid.append(note);
    $('quality-metrics').textContent = ''; $('quality-glyph-issues').textContent = '';
  } else qualityChoose(matches.find(g => g.id === qualitySelected) || matches[0]);
}

function qualityPresent(report, image) {
  qualityReport = report; qualityAtlas = image; qualitySelected = null;
  $('quality-results').hidden = false;
  const summary = $('quality-summary'); summary.replaceChildren();
  const stats = report.summary;
  for (const label of [stats.glyphs + ' glyphs', stats.errors + ' errors', stats.warnings + ' warnings',
    stats.missing + ' missing', stats.clipped + ' clipped', stats.kerning_pairs + ' kerning pairs',
    report.atlas.join(' × ') + ' atlas']) {
    const item = document.createElement('span'); item.textContent = label; summary.append(item);
  }
  const polish = $('quality-polish'); polish.replaceChildren();
  for (const entry of report.polish) {
    const cell = document.createElement('span'); cell.className = entry.status;
    cell.textContent = entry.char; cell.title = entry.char + ' — ' + entry.status.replace('_', ' ');
    polish.append(cell);
  }
  const findings = $('quality-issues'); findings.replaceChildren();
  if (!report.issues.length) {
    const item = document.createElement('li'); item.textContent = 'No automated issues detected.'; findings.append(item);
  }
  for (const issue of report.issues) {
    const item = document.createElement('li');
    item.textContent = issue.severity.toUpperCase() + ' ' + (issue.char || '') + ' [' + issue.code + ']: ' + issue.message;
    findings.append(item);
  }
  qualityGrid(); $('quality-save').disabled = false;
}
$('quality-search').addEventListener('input', qualityGrid);
$('quality-problems').addEventListener('change', qualityGrid);
$('quality-save').addEventListener('click', () => {
  if (!qualityReport) return;
  const { atlas_png, ...report } = qualityReport;
  download(new Blob([JSON.stringify(report, null, 2) + '\n'], { type: 'application/json' }),
    report.name + '.quality.json');
});
$('quality-run').addEventListener('click', async () => {
  if (qualityBusy || !style) return;
  qualityBusy = true; $('quality-run').disabled = true;
  $('quality-state').textContent = 'Building the full-size font atlas and checking metrics…';
  const snapshotRevision = revision;
  try {
    const response = await request('inspect', exportStyle()), report = await response.json();
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve; image.onerror = () => reject(new Error('Could not display atlas image.'));
      image.src = report.atlas_png;
    });
    qualityPresent(report, image);
    $('quality-state').textContent = report.summary.errors + ' errors · ' + report.summary.warnings + ' warnings. ' +
      (revision === snapshotRevision ? 'Full-quality inspection complete.' : 'Style changed during inspection; rerun.');
  } catch (error) {
    $('quality-state').textContent = 'Inspection failed: ' + error.message;
  } finally {
    qualityBusy = false; $('quality-run').disabled = false;
  }
});

$('save-style').addEventListener('click', () => download(new Blob([JSON.stringify(exportStyle(), null, 2) + '\n'], { type: 'application/json' }), `${style.name}.style.json`));
$('export').addEventListener('click', async () => {
  exporting = true; $('export').disabled = true; const snapshot = exportStyle(), title = titleMode(); message(title ? 'Rendering your title at full quality…' : 'Building full-quality atlas. This can take a minute…');
  try { const response = await request(title ? 'title-export' : 'export', snapshot); download(await response.blob(), title ? `${snapshot.name}_title.png` : `${snapshot.name}.zip`); message(title ? 'Title exported with a transparent background.' : 'Atlas exported. Your ZIP includes the editable style.'); }
  catch (error) { message(error.message, true); }
  finally { exporting = false; $('export').disabled = false; if (pending) preview(); }
});
$('apply-json').addEventListener('click', async () => {
  try { const parsed = JSON.parse($('json').value); const response = await request('expand', parsed); style = (await response.json()).style; sync(); schedule(); }
  catch (error) { message(error.message, true); }
});
for (const key of ['depth', 'shine', 'playful']) $('simple-' + key).addEventListener('input', event => { $('simple-' + key + '-value').textContent = event.target.value; });
$('simple-palette').addEventListener('change', () => { $('simple-color').disabled = $('simple-palette').value !== 'custom'; });
$('apply-simple').addEventListener('click', async () => {
  $('apply-simple').disabled = true;
  const simple = { depth_3d: Number($('simple-depth').value), shine: Number($('simple-shine').value), playful: Number($('simple-playful').value) };
  if ($('simple-palette').value === 'custom') simple.base_color = $('simple-color').value;
  else simple.palette = $('simple-palette').value;
  const draft = { name: 'custom_style', simple };
  for (const key of ['font', 'size', 'chars', 'preview', 'preview_bg', 'variation', 'title', 'kerning', 'kerning_script', 'atlas_width', 'max_atlas_size', 'atlas_packing', 'supersample']) if (key in style) draft[key] = structuredClone(style[key]);
  try { const response = await request('expand', draft); style = (await response.json()).style; sync(); schedule(); }
  catch (error) { message(error.message, true); }
  finally { $('apply-simple').disabled = false; }
});
(async () => {
  try {
    const response = await fetch('/api/catalog'); if (!response.ok) throw new Error('Could not load presets.');
    const catalog = await response.json(); presets = catalog.presets; token = catalog.token; maxReferenceBytes = catalog.max_reference_bytes;
    presets.forEach((preset, index) => { const option = document.createElement('option'); option.value = index; option.textContent = preset.name.replaceAll('_', ' '); $('preset').append(option); });
    catalog.fonts.forEach(path => { const option = document.createElement('option'); option.value = path; option.textContent = path.split(/[\\/]/).at(-1).replace(/\.ttf$/i, ''); $('font').append(option); });
    selectPreset(); $('export').disabled = false; $('save-style').disabled = false; $('apply-simple').disabled = false; $('quality-run').disabled = false;
  } catch (error) { message(error.message, true); }
})();
