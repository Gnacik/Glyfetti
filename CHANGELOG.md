# Changelog

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
