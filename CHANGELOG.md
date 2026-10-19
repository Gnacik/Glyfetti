# Changelog

## Unreleased

- Add Font Quality Inspector: full-render diagnostics for glyph coverage, bounds, overlap, clipping, advances, kerning and Polish characters.
- Add an interactive editor grid with enlarged baseline/advance guides, issue filters and JSON report download.
- Add `glyfetti inspect` (`--strict`, `--out`) and MCP `inspect_font`; cover real atlases, corrupted metrics and editor API with tests.

- Extract approximate fill gradients and outlines from isolated PNG/JPEG lettering references.
- Add reference analysis to the local editor, CLI (`glyfetti reference`) and MCP (`analyze_reference_image`).
- Keep font/effect geometry editable and preserve all image processing on the local machine.
- Validate file types and sizes; include regression tests for transparent PNGs, JPGs, malformed inputs and authenticated HTTP requests.

- Fix reference analysis for EXIF-rotated JPEGs and tightly cropped transparent PNGs; decode only PNG/JPEG.
- Serve editor requests on threads so long inspections no longer block previews; inspection skips preview sheets.
- Resolve `/api/inspect` fonts like editor previews and share style preparation between MCP and the inspector.
- Take the reference size limit from `MAX_REFERENCE_BYTES` everywhere, including the editor.
- Add tests for clipping detection and MCP `analyze_reference_image`.

- Speed up condensed styles (~35% faster `fire` build) by dropping redundant horizontal render padding; metrics unchanged.
- Render glyphs on a thread pool (`build(workers=…)`, `glyfetti build -j N`; default CPU count, `1` = sequential); `fire` build ~5.8x faster, output byte-identical.
- Add a tag-triggered release workflow: checks the tag against the package version, builds sdist + wheel, tests the wheel and publishes to PyPI via trusted publishing.
- CI: ruff and mypy lint job, pytest coverage report, pip cache, Python 3.13 and 3.14 in the test matrix; `dev` extra.
- Speed up the effect stack ~2x per glyph: compositing limited to the layer bounding box, integer/bilinear shifts by slicing instead of `ndi.shift`, large shadow/extrude blurs at reduced resolution, one distance transform for bevel and gloss (max 2/255 premultiplied difference).
- Export BMFont `.fnt` as text, XML or binary (version 3) via `fnt_format` / `glyfetti build --fnt-format`; kerning included in every format.
- Add named character sets (`charset`: `ascii`, `latin1`, `latin-ext-a`, `cyrillic`, `polish`, or `font` for the whole font cmap, capped at 4096), combinable with `chars`.
- Split `engine.build()` into glyph rendering, packing, export and preview helpers; output byte-identical.

## 0.1.5a1

- Add an optional stdio MCP server with preset/font discovery, native coverage
  checks, style expansion, inline PNG previews and full-quality exports.
- Expose the style schema and generated artifacts as MCP resources. Each export
  gets a unique folder and includes an editable raw style without overwriting
  previous exports; artifact resources remain inside the configured output root.
- Add `glyfetti mcp --print-config` using the current Python executable and an
  absolute output path, plus client examples and English/Polish setup guides.
- Keep MCP dependencies optional: the SDK needs Python 3.11+, while the existing
  renderer, CLI and editor retain Python 3.10 support.
- Test actual stdio subprocesses with current and legacy client negotiation,
  image results, artifact readback, validation errors and optional-runtime behavior.

## 0.1.4a1

- Add nested `simple` controls for custom colors, nine palettes, outline, 3D depth,
  shine, shadow/glow, width, weight, playful jitter and spacing.
- Derive raw styles deterministically, merge raw overrides recursively and resolve
  six bundled font aliases while preserving existing raw styles.
- Add `glyfetti expand`, a simple-style example and schema support for both formats.
- Add an editor color/palette builder and compact JSON support; keep saved editor
  styles expanded for further fine-tuning.
- Test compact/raw image equivalence, defaults, palette and font selection, override
  precedence, validation, CLI expansion and both export modes.

## 0.1.3a1

- Add `glyfetti title`: merge letter masks before applying one shared effect stack,
  then export a cropped transparent PNG and a separate background preview.
- Support multiline alignment, configurable transparent margins, kerning, variable
  fonts, condense, jitter, missing-character reports and automatic Polish diacritics.
- Add title mode, alignment, margin controls and direct PNG downloads to the editor.
- Share font configuration and plain glyph shaping between atlas and title modes.
- Reject empty titles and oversized whole-title effect buffers with readable errors.
- Add regression coverage for shared outlines, alignment, transparency, CLI and API
  exports, Polish characters and title previews for all bundled presets.

## 0.1.2a1

- Add horizontal GPOS PairPos kerning (explicit pairs, classes and extension
  lookups), legacy kern fallback, variable-axis scaling and a script selector.
- Apply the same integer kerning pairs in previews, BMFont and JSON; import them
  into the existing Unity font feature table, clearing stale pairs on reimport.
- Add deterministic, non-rotating MaxRects packing with transparent gutters,
  power-of-two height search and a shelf fallback that prevents size regressions.
- Add editor controls for kerning and packing, plus packing, pair-count and
  rectangle occupancy information in previews and exported build reports.
- Prevent multiple editor instances from binding the same port on Windows.
- Test pairs against independent shaping, synthetic OpenType fixtures and
  randomized atlas layouts.

## 0.1.1a1

- Add `glyfetti serve`: local preset editor with draft previews, font selection,
  effect controls, raw JSON editing, style downloads and full-quality atlas ZIPs.
- Validate styles before rendering and add `glyfetti validate` with readable errors.
- Refuse atlas overflow; include all enabled effects when reserving glyph padding.
- Keep shadows and negative advances inside preview images; align line gradients
  to the font baseline.
- Key patched-font caches by font content and variation axes, write caches atomically,
  and handle missing accent references, missing base characters and CFF fonts.
- Update existing Unity font assets and materials without replacing their GUIDs;
  validate imported dimensions and glyph rectangles.
- Include fonts, licenses, presets and the schema in wheels; render galleries in
  temporary folders rather than writing into installed package data.
- Add export, font and local editor regression tests; run CI on Linux and Windows.
