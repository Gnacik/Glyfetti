# Changelog

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
