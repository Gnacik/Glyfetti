# Glyfetti – Style & Parameter Reference

🌐 **English** | [Polski](STYLE_REFERENCE.pl.md)

> Document version: 0.1.4. Simple and raw styles work with atlas builds and whole-title PNG exports.

A style is a single JSON file. Glyfetti renders every character of a font through the same
stack of layers and writes a PNG atlas + metrics (BMFont `.fnt`, JSON for Unity/TMP) + a preview.

Styles can be written at two levels:

| Level | For whom | Number of parameters |
|---|---|---|
| **Simple** | people, chat assistants via MCP, sliders in the web UI | ~12 knobs |
| **Raw** | fine-tuning, full control | every layer separately |

A simple style is automatically expanded into a raw one. If a file contains both levels,
raw parameters override whatever the simple level produced.

---

## 1. Layer stack

Each glyph is drawn bottom-up in this order:

```
1. shadow   – drop shadow / glow (can be blurred and offset)
2. extrude  – hard "base" OUTSIDE the outline (sticker look)
3. outline  – outline; wraps the letter TOGETHER with its 3D side
4. side     – the letter's side (3D thickness), UNDER the outline
5. fill     – gradient fill of the letter's front
6. bevel    – embossing: lightened and darkened edges
7. gloss    – soft shine on the upper part of the letter
```

Every layer except `outline` and `fill` can be disabled with `"enabled": false` or omitted.

**Units:** all distances are in pixels of the **final atlas** (not the supersampled render).
Colors are `#RRGGBB` hex. Opacity (`opacity`) and strengths (`*_strength`) range from 0 to 1.

---

## 2. Simple style

Put high-level controls inside `simple`. Raw renderer fields stay at the top level.
Only `name` and `simple` are required; the default font is bundled Titan One, size 90,
with Latin/Polish letters, digits and common punctuation.

```json
{
  "name": "treasure_gold",
  "font": "Titan One",
  "simple": {
    "base_color": "#F5B845",
    "outline": "dark",
    "outline_width": "medium",
    "depth_3d": 0.6,
    "shadow": "soft",
    "shine": 0.4,
    "glow": null,
    "width": 0.78,
    "weight": 0,
    "playful": 0.3,
    "spacing": -5
  },
  "outline": { "width": 5 }
}
```

The top-level outline width overrides the generated width while retaining its color.
Objects merge recursively; arrays, scalars and `null` replace generated values.
Explicit `enabled` fields also override generated on/off states. Raw-only styles
are preserved. Expansion is deterministic and never rewrites the source file.

| Field inside `simple` | Type / range | Default | Result |
|---|---|---|---|
| `base_color` | `#RRGGBB` | unset | custom palette; wins over `palette` when both are supplied |
| `palette` | gold, cream, candy, mint, ice, fire, magic, wood, silver | gold | fixed fill, side and outline colors |
| `outline` | dark / light / none / hex | dark | derived outline color; none sets width to zero |
| `outline_width` | thin / medium / thick or 0–40 px | medium | tokens are 2.5/4/6 px at size 100, scaled with size; numbers are final pixels |
| `depth_3d` | 0–1 | 0.5 | side depth up to 10 px at size 100, scaled with size and capped at 40 px |
| `shadow` | none / soft / hard / long | soft | shadow configuration |
| `shine` | 0–1 | 0.4 | bevel lighting and gloss; zero disables both |
| `glow` | null / hex | null | replaces the shadow with a centered glow, including when shadow is none |
| `width` | 0.5–1.5 | 1 | `condense` |
| `weight` | 0–6 px | 0 | `embolden`; font axes remain configurable through top-level `variation` |
| `playful` | 0–1 | 0 | deterministic rotation and vertical jitter |
| `spacing` | −512–512 px | 0 | `tracking` |

For custom colors, fill stops mix the base with white by 70%, 30%, and 0%.
Side colors mix it with black by 20% and 50%; the dark outline uses 80% black.
These are direct sRGB channel mixes, not perceptually uniform color-space conversions.
Named palettes retain their exact listed colors, including the five silver gradient stops.

Bundled font aliases: `Titan One`, `Grandstander`, `Baloo 2`, `Dosis`, `Chewy`, `Sniglet`.
They resolve to bundled font files; any other `font` value remains a normal path.
`size`, `chars`, `preview`, `variation`, `title` and export options stay top-level.

```bash
glyfetti build examples/simple-mint.json --preview-only
glyfetti title examples/simple-mint.json --text "Victory!" -o victory.png
glyfetti expand examples/simple-mint.json -o expanded.json
```

`expand` emits a validated raw style and resolves its font to an absolute local path;
without `-o` it writes JSON to stdout. It resolves the font without applying diacritic
patches; patching remains a build-time operation. The editor's color builder and raw
JSON panel accept compact styles and convert them to editable raw settings. Editor
style downloads and atlas ZIPs contain the expanded form. Source compact files remain
unchanged. Update absolute font paths when moving expanded styles to another computer.

---

## 3. Raw style – full parameter list

### 3.1 General

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | string | **required** | style name, output file name |
| `description` | string | – | description shown in the gallery and in MCP |
| `font` | path | **required** | TTF/OTF file, relative to the style file |
| `variation` | list of numbers or object | – | variable-font axes, e.g. `{"wght": 800, "wdth": 75}` |
| `size` | px | **required** | font size in the atlas; don't scale in-game text above this |
| `supersample` | 1–4 | 3 | render at N× scale, then downscale (smoother edges, slower) |
| `chars` | string | **required** unless `charset` | character set for the atlas (duplicates and spaces are skipped; space is always added) |
| `charset` | name or list | – | named sets appended to `chars`: `ascii`, `latin1`, `latin-ext-a`, `cyrillic`, `polish`, `font` (whole font cmap, max 4096 characters) |
| `atlas_width` | px | 1024 | atlas width; height is picked as a power of 2 |
| `max_atlas_size` | px | 8192 | maximum atlas width and height; oversized exports fail without cropping |
| `atlas_packing` | `maxrects` / `shelf` | `maxrects` | non-rotating compact packing with a shelf fallback |
| `kerning` | bool | `true` | export horizontal advance pairs and apply them in previews |
| `kerning_script` | OpenType tag | `latn` | default-language script for GPOS kern; falls back to DFLT |
| `fnt_format` | `text` / `xml` / `binary` | `text` | AngelCode BMFont `.fnt` flavour (binary = version 3); CLI `--fnt-format` overrides |
| `tracking` | px | 0 | extra letter spacing; negative pulls letters together and merges outlines |
| `line_height` | multiplier | 1.15 | line height relative to font metrics |
| `condense` | 0.5–1.5 | 1.0 | horizontal glyph scaling (condensed < 1) |
| `embolden` | px | 0 | stroke thickening before effects are applied |
| `jitter` | object or `null` | `null` | "bouncy" letters, see 3.9 |
| `preview` | list of strings | 3 test lines | texts for `*_preview.png` |
| `preview_bg` | hex or `"transparent"` | `#ffffff` | preview background (preview only; the atlas is always transparent) |
| `title` | object | `{ "align": "center", "padding": 8 }` | whole-title PNG options; align: left/center/right, padding: 0–200 final pixels |
| `auto_diacritics` | bool | `true` | compose missing Polish letters from accents present in the font |

### 3.2 `fill` – fill (letter front)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `stops` | list of `[position, hex]` | **required** | vertical gradient stops; position 0 = top, 1 = bottom |
| `gradient_space` | `"glyph"` / `"line"` | `"glyph"` | `glyph`: gradient stretched over each letter separately; `line`: shared across the line (lowercase letters get the lower part) |

Solid fill: two stops with the same color.

### 3.3 `outline`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `color` | hex | **required** | outline color |
| `width` | px | **required** | thickness; 0 = no outline |

The outline wraps the letter together with its 3D side (`side`), so the whole shape has a single contour.

### 3.4 `side` – 3D side

| Parameter | Type | Default | Description |
|---|---|---|---|
| `depth` | px | – | side thickness (downward offset) |
| `dx` | px | 0 | additional offset to the right (negative = left), adds a sense of perspective |
| `color_top` | hex | – | side color at the top of the letter |
| `color_bottom` | hex | – | side color at the bottom |
| `enabled` | bool | `true` | |

The side is typically darker and warmer than the letter front (gold → orange).

### 3.5 `bevel` – embossing

Computed from a distance map of the letter's edges: edges are rounded and lit from one direction.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `size` | px | – | width of the rounded edge |
| `soften` | px | 1.0 | smoothing of the height map |
| `light_angle` | degrees | – | light direction: 90 = from the top, 100–120 = from the top-left |
| `highlight_color` | hex | – | color of lit edges |
| `highlight_strength` | 0–1 | – | lightening strength |
| `shadow_color` | hex | – | color of shaded edges |
| `shadow_strength` | 0–1 | – | darkening strength |
| `enabled` | bool | `true` | |

### 3.6 `gloss` – shine

| Parameter | Type | Default | Description |
|---|---|---|---|
| `color` | hex | – | usually white |
| `opacity` | 0–1 | – | shine strength |
| `inset` | px | – | distance from the letter edge |
| `height` | 0–1 | – | fraction of letter height (from the top) covered |
| `blur` | px | – | softness of the transition |
| `enabled` | bool | `true` | |

### 3.7 `shadow` – shadow and glow

| Parameter | Type | Default | Description |
|---|---|---|---|
| `color` | hex | – | shadow color |
| `opacity` | 0–1 | – | opacity |
| `dx`, `dy` | px | – | offset |
| `blur` | px | 0 | blur (0 = hard, comic-style shadow) |
| `enabled` | bool | `true` | |

**Glow:** `dx = 0`, `dy = 0`, large `blur` (10–14), a light color, high opacity (0.7–0.9).

### 3.8 `extrude` – base outside the outline

An older variant of the 3D effect: a dark mass under the entire outline. In new styles usually replaced by `side`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `color` | hex | – | base color |
| `depth` | px | – | downward offset |
| `opacity` | 0–1 | 1.0 | opacity |
| `blur` | px | 0 | blur |
| `enabled` | bool | `true` | |

### 3.9 `jitter` – bouncy letters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `rotate` | degrees | 0 | maximum letter rotation (random ±) |
| `y` | px | 0 | maximum vertical offset (random ±) |
| `seed` | number | 0 | random seed; a different `seed` = a different arrangement |

The randomness is fixed per character: an "o" is always rotated the same way. In long text,
repeated letters can give this away, so set `"jitter": null` for descriptions and numbers.

---

## 4. Vocabulary: description → parameters

Used by chat assistants (MCP) and as a cheat sheet for people.

| When the user says… | Set inside `simple` unless otherwise indicated |
|---|---|
| golden, honey | palette `gold` or `base_color: #F5B845` |
| cream, vanilla | palette `cream` |
| silver, metallic | palette `silver` (gradient with several lightness bands) |
| 3D, embossed, chunky, "like a block" | `depth_3d` 0.6–0.9 |
| flat, minimalist | `depth_3d: 0`, `shine: 0`, `shadow: "none"` or `"soft"` |
| with a shadow, soft shadow | `shadow: "soft"` |
| comic, cartoon, "BOOM!" | `shadow: "hard"`, `shine: 0`, `outline: "#000000"`, `playful` 0.5 |
| glowing, neon, aura, magical | `glow: <light base color>` |
| candy, glossy, jelly | `shine` 0.7–0.9 |
| matte | `shine` 0–0.2 |
| narrow, slim, condensed | `width` 0.75–0.85 |
| thick, heavy, bold | `weight` 2–4 |
| delicate, thin | `weight` 0, `outline_width: "thin"` |
| fun, hand-drawn, fairy-tale | `playful` 0.3–0.5, font Grandstander or Chewy |
| serious, elegant | `playful: 0`, font Baloo 2 or Dosis |
| tight, merged letters | `spacing` −4 to −8 |
| for a button | `outline: "dark"`, `depth_3d` 0.3, white fill |
| for small UI text | preset `flat_ui`, `jitter: null`, no bevel |

### Named palettes

| Palette | Fill (top → bottom) | 3D side | Outline |
|---|---|---|---|
| `gold` | #FFF1BC → #FCE288 → #F8C95A | #EFA032 → #C46A14 | #562506 |
| `cream` | #FFFDF5 → #FBF0D6 → #F1DDB0 | #C9A36B → #8E6838 | #3E1E0A |
| `candy` | #FFE6F1 → #FF9CC7 → #FF5E9E | #E2457F → #9E1C50 | #5A0F2E |
| `mint` | #FFFFFF → #E6FFD9 | #3F8F2E → #27611B | #1F4D17 |
| `ice` | #FFFFFF → #C8F0FF → #62C2F2 | #2E8FD2 → #174F88 | #0E2F55 |
| `fire` | #FFF8B5 → #FFC93C → #FF5E14 | #D23A10 → #7E1404 | #3A0A02 |
| `magic` | #FAF0FF → #CFA6FF → #8C55F0 | #6234C2 → #38197A | #1E0D40 |
| `wood` | #D39657 → #8B5426 | #5A3215 → #3B1F0B | #3B1F0B |
| `silver` | #FFFFFF → #D5DCE3 → #8C96A1 → #C9D1D9 → #EEF2F5 | #5C6671 → #2F363E | #1B2026 |

---

## 5. Presets

All presets include the full character set: A–Z, a–z, Polish letters ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż, digits,
punctuation and symbols (`! ? . , : ; % + - – × * / \ # ' " = ( ) [ ] { } < > & @ _ ~ ^ $ € … « » „ ” “`).

| # | Preset | Font | Character | Key settings | Use for |
|---|---|---|---|---|---|
| 1 | `honey_gold` | Titan One | warm golden 3D letters | 6 px 3D side, bevel, gloss, soft shadow, 77% width, jitter | titles, victory screens |
| 2 | `cream_sign` | Grandstander Black | cream lettering, beige side | 5 px side, subtle bevel, 80% width | headers on dark wood |
| 3 | `candy_pink` | Sniglet (+PL*) | candy pink | strong gloss (0.45), bevel, 6 px side | bonuses, shop, rewards |
| 4 | `mint_button` | Baloo 2 ExtraBold | white fill, green side | 5 px side, no gloss, 85% width | labels on green buttons |
| 5 | `ice_blue` | Titan One | icy blue | #9BE3FF glow, gloss 0.5 | freeze effects |
| 6 | `fire` | Titan One | fire, yellow → red | orange glow, stronger jitter | combos, score multipliers |
| 7 | `magic_purple` | Grandstander Black | purple magic | purple glow, 5 px side | power-ups, spells |
| 8 | `comic_pop` | Titan One | flat comic | flat yellow, 5 px black outline, hard 6/6 shadow, strong jitter | "BOOM!", exclamations |
| 9 | `wood_label` | Grandstander ExtraBold | brown on parchment | thin 3 px outline, shallow 3 px side | labels, panels, settings |
| 10 | `silver_metal` | Baloo 2 ExtraBold | metallic silver | 5-stop gradient, bevel 0.6 | achievements, leaderboards, 2nd place |
| 11 | `chocolate_cream` | Chewy (+PL*) | hand-drawn cream | thick 6 px outline, `extrude` base, jitter | casual titles, sweets |
| 12 | `flat_ui` | Dosis ExtraBold | plain UI text | dark brown, 2 px white outline, light shadow, no 3D effects | descriptions, numbers, small text |

\* Fonts marked "+PL" don't originally include ą ć ę ń ś ź ż. Glyfetti composes them automatically at build
time from accents already present in the font (`auto_diacritics`, on by default) and caches the result in
`~/.cache/glyfetti`. Modified fonts are never shipped in the repository (OFL license).

---

## 6. Fonts

| Font | License | Polish characters | Axes | Character |
|---|---|---|---|---|
| Titan One | OFL | native | – | very heavy, round, tall lowercase |
| Grandstander | OFL | native | `wght` 100–900 | hand-drawn, playful, irregular |
| Baloo 2 | OFL | native | `wght` 400–800 | round, legible, wide (often condensed) |
| Dosis | OFL | native | `wght` 200–800 | narrow, rounded terminals, good for UI |
| Chewy | Apache 2.0 | auto-composed | – | hand-drawn, "rubbery" |
| Sniglet | OFL | auto-composed | – | bubbly, very round |
| Lilita One | OFL | partial (ą ę ż missing even after patching) | – | heavy, cartoonish |
| Fredoka | OFL | auto-composed | `wght`, `wdth` | soft, friendly |

Any other TTF/OTF font works too. `glyfetti check-font <file>` lists missing characters.

---

## 7. Output files

| File | Contents |
|---|---|
| `<name>.png` | atlas with transparency |
| `<name>.fnt` | BMFont metrics (text, XML or binary per `fnt_format`) – Godot, libGDX, Phaser, Cocos, Defold… |
| `<name>.json` | metrics for the Unity importer (TextMeshPro) |
| `<name>_preview.png` | text assembled from the atlas – tests metrics and looks |
| `<name>_atlas_on_white.png` | atlas on a white background for browsing |

---

## 8. Known limitations

- **Bitmap:** in-game text shouldn't be larger than `size`; for large titles, generate a separate atlas with a bigger `size`.
- **Kerning is horizontal advance-only**; contextual positioning, ligatures and other placement corrections require a shaping engine.
- **Jitter is tied to the character**, so repeated letters look identical.
- **Letter outlines overlap** at strongly negative `tracking`; use `glyfetti title` for a shared outline across the complete text.
- **TMP Inspector effects** (Outline, Underlay) don't work with a color atlas – the effects are already baked in.
