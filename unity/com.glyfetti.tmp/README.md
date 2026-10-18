# Glyfetti for TextMeshPro

Install via **Package Manager → Add package from git URL**:

```
https://github.com/Gnacik/glyfetti.git?path=/unity/com.glyfetti.tmp
```

1. Generate a font with `glyfetti build my_style.json` and copy `<name>.png` + `<name>.json` into your `Assets/`.
2. Select the `.json` and run **Tools → Glyfetti → Create TMP Font Asset**.
3. Assign `<name> TMP.asset` to a TextMeshPro component and keep its **vertex color white**.

Status: **experimental** – please report your Unity/TMP version in issues if something breaks.
