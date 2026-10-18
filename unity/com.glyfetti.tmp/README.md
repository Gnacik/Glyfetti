# Glyfetti for TextMeshPro

Install via **Package Manager → Add package from git URL**:

```
https://github.com/Gnacik/glyfetti.git?path=/unity/com.glyfetti.tmp
```

1. Generate a font with `glyfetti build my_style.json` and copy `<name>.png` + `<name>.json` into your `Assets/`.
2. Select the `.json` and run **Tools → Glyfetti → Create TMP Font Asset**.
3. Assign `<name> TMP.asset` to a TextMeshPro component and keep its **vertex color white**.

Status: **experimental** – please report your Unity/TMP version in issues if something breaks.

Reimporting the same name in the same folder updates the existing font asset and its material in place, preserving GUIDs and scene references. Import checks atlas dimensions and glyph rectangles before changing the font asset.

Kerning pairs from JSON are mapped to TMP glyph indices and replace the previous feature table entries on reimport. Keep kerning/font features enabled on your TextMeshPro components. Old JSON files without a `kernings` array remain supported.
