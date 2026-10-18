// Glyfetti importer: atlas PNG + JSON (from `glyfetti build`) -> TMP_FontAsset with a color atlas.
// Usage: select the .json file in the Project window, then  Tools > Glyfetti > Create TMP Font Asset.
// The PNG must sit next to the JSON and share its name.
#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore;
using UnityEngine.TextCore.LowLevel;

namespace Glyfetti.Editor
{
    public static class BitmapFontToTMP
    {
        [System.Serializable] class CharDef { public int id, x, y, w, h, xo, yo, xa; }
        [System.Serializable] class KerningDef { public int first, second, amount; }
        [System.Serializable] class FontDef { public string name; public int size, lineHeight, baseline, scaleW, scaleH; public CharDef[] chars; public KerningDef[] kernings; }

        [MenuItem("Tools/Glyfetti/Create TMP Font Asset")]
        static void CreateFromSelection()
        {
            var json = Selection.activeObject as TextAsset;
            if (json == null) { EditorUtility.DisplayDialog("Glyfetti", "Select a Glyfetti .json file in the Project window.", "OK"); return; }
            string jsonPath = AssetDatabase.GetAssetPath(json);
            Build(jsonPath);
        }

        public static TMP_FontAsset Build(string jsonPath)
        {
            var def = JsonUtility.FromJson<FontDef>(File.ReadAllText(jsonPath));
            if (def == null || string.IsNullOrEmpty(def.name) ||
                !System.Text.RegularExpressions.Regex.IsMatch(def.name, @"^[A-Za-z0-9][A-Za-z0-9_-]*$") ||
                def.size <= 0 || def.scaleW <= 0 || def.scaleH <= 0 || def.chars == null)
                throw new System.ArgumentException("Invalid Glyfetti font metadata.");
            var shader = Shader.Find("Glyfetti/ColorBitmapFont");
            if (shader == null) throw new System.InvalidOperationException("Glyfetti color shader is missing. Reinstall the package.");
            var ids = new HashSet<int>();
            foreach (var c in def.chars)
                if (c.id < 0 || c.id > 0x10FFFF || !ids.Add(c.id) || c.x < 0 || c.y < 0 ||
                    c.w < 0 || c.h < 0 || c.x + c.w > def.scaleW || c.y + c.h > def.scaleH)
                    throw new System.ArgumentException("Invalid or duplicate character in Glyfetti metadata.");
            if (def.kernings != null)
            {
                var pairs = new HashSet<ulong>();
                foreach (var pair in def.kernings)
                    if (!ids.Contains(pair.first) || !ids.Contains(pair.second) ||
                        !pairs.Add(((ulong)(uint)pair.first << 32) | (uint)pair.second))
                        throw new System.ArgumentException("Invalid or duplicate kerning pair in Glyfetti metadata.");
            }
            string dir = Path.GetDirectoryName(jsonPath).Replace('\\', '/');
            string texPath = $"{dir}/{Path.GetFileNameWithoutExtension(jsonPath)}.png";

            // atlas import settings: uncompressed, alpha-is-transparency (prevents dark fringes when filtering)
            var imp = (TextureImporter)AssetImporter.GetAtPath(texPath);
            if (imp == null) { Debug.LogError($"[Glyfetti] Atlas not found: {texPath}"); return null; }
            imp.textureType = TextureImporterType.Default;
            imp.alphaIsTransparency = true;
            imp.mipmapEnabled = true;          // nicer when scaled down
            imp.npotScale = TextureImporterNPOTScale.None;
            imp.maxTextureSize = Mathf.NextPowerOfTwo(Mathf.Max(def.scaleW, def.scaleH));
            imp.isReadable = false;
            imp.textureCompression = TextureImporterCompression.Uncompressed;
            imp.wrapMode = TextureWrapMode.Clamp;
            imp.filterMode = FilterMode.Bilinear;
            imp.SaveAndReimport();
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            if (tex.width != def.scaleW || tex.height != def.scaleH)
                throw new System.ArgumentException("Atlas dimensions do not match JSON metadata. Check texture import size limits.");

            string assetPath = $"{dir}/{def.name} TMP.asset";
            var fa = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(assetPath);
            bool isNew = fa == null;
            if (isNew && AssetDatabase.LoadMainAssetAtPath(assetPath) != null)
                throw new System.InvalidOperationException("Output path is occupied by a different asset.");
            if (isNew) fa = ScriptableObject.CreateInstance<TMP_FontAsset>();
            else Undo.RecordObject(fa, "Update Glyfetti font");
            fa.glyphTable.Clear();
            fa.characterTable.Clear();
            fa.name = def.name;
            fa.atlasPopulationMode = AtlasPopulationMode.Static;

            var face = new FaceInfo();
            face.familyName = def.name;
            face.styleName = "Regular";
            face.pointSize = def.size;
            face.scale = 1f;
            face.lineHeight = def.lineHeight;
            face.ascentLine = def.baseline;
            face.capLine = def.baseline * 0.8f;
            face.meanLine = def.baseline * 0.55f;
            face.baseline = 0;
            face.descentLine = -(def.lineHeight - def.baseline);
            face.underlineOffset = -def.size * 0.1f;
            face.underlineThickness = def.size * 0.05f;
            face.strikethroughOffset = def.baseline * 0.3f;
            face.tabWidth = def.size;
            fa.faceInfo = face;

            uint idx = 0;
            var glyphIndices = new Dictionary<int, uint>();
            foreach (var c in def.chars)
            {
                // TextCore measures rect Y from the atlas BOTTOM, the JSON from the top
                var rect = new GlyphRect(c.x, def.scaleH - c.y - c.h, c.w, c.h);
                var metrics = new GlyphMetrics(c.w, c.h, c.xo, def.baseline - c.yo, c.xa);
                var glyph = new Glyph(idx, metrics, rect, 1f, 0);
                fa.glyphTable.Add(glyph);
                fa.characterTable.Add(new TMP_Character((uint)c.id, glyph));
                glyphIndices.Add(c.id, idx);
                idx++;
            }

            // Map Unicode IDs to this asset's glyph indices, which TMP pairs require.
            var featureTable = fa.fontFeatureTable;
            featureTable.glyphPairAdjustmentRecords.Clear();
            if (def.kernings != null)
                foreach (var pair in def.kernings)
                {
                    var first = new TMP_GlyphAdjustmentRecord(glyphIndices[pair.first], new TMP_GlyphValueRecord(0, 0, pair.amount, 0));
                    var second = new TMP_GlyphAdjustmentRecord(glyphIndices[pair.second], new TMP_GlyphValueRecord(0, 0, 0, 0));
                    featureTable.glyphPairAdjustmentRecords.Add(new TMP_GlyphPairAdjustmentRecord(first, second));
                }

            var mat = fa.material;
            bool ownsMaterial = mat != null && AssetDatabase.GetAssetPath(mat) == assetPath;
            bool addMaterial = !ownsMaterial;
            if (addMaterial) mat = new Material(shader) { name = def.name + " Material" };
            else Undo.RecordObject(mat, "Update Glyfetti material");
            mat.shader = shader;
            mat.SetTexture("_MainTex", tex);
            fa.material = mat;
            fa.atlasTextures = new[] { tex };

            if (isNew) AssetDatabase.CreateAsset(fa, assetPath);
            if (addMaterial) AssetDatabase.AddObjectToAsset(mat, fa);
            EditorUtility.SetDirty(mat);

            // fields with internal setters – set via SerializedObject
            var so = new SerializedObject(fa);
            SetInt(so, "m_AtlasWidth", def.scaleW);
            SetInt(so, "m_AtlasHeight", def.scaleH);
            SetInt(so, "m_AtlasPadding", 0);
            SetInt(so, "m_AtlasRenderMode", (int)GlyphRenderMode.SMOOTH);
            var ver = so.FindProperty("m_Version");
            if (ver != null) ver.stringValue = "1.1.0";
            so.ApplyModifiedPropertiesWithoutUndo();

            fa.ReadFontAssetDefinition();
            EditorUtility.SetDirty(fa);
            AssetDatabase.SaveAssets();
            AssetDatabase.ImportAsset(assetPath);
            Debug.Log($"[Glyfetti] Created {assetPath} ({def.chars.Length} characters)");
            Selection.activeObject = fa;
            return fa;
        }

        static void SetInt(SerializedObject so, string prop, int v)
        {
            var p = so.FindProperty(prop);
            if (p != null) p.intValue = v;
            else Debug.LogWarning($"[Glyfetti] Field {prop} not found on TMP_FontAsset (different TMP version?) – please open an issue");
        }
    }
}
#endif
