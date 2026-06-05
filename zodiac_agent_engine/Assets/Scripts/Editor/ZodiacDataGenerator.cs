// ZodiacDataGenerator.cs
//
// Editor utility that generates all 12 ZodiacData ScriptableObject assets
// from a JSON file exported by zodiac_schema.py.
//
// Usage:
//   1. From the Python project root, run:
//          python -c "
//          import json
//          from zodiac_schema import SIGNS
//          out = []
//          for s in SIGNS:
//              d = s.to_dict()
//              out.append({
//                  'name': d['name'], 'index': d['index'],
//                  'element': d['element'], 'modality': d['modality'],
//                  'polarity': d['polarity'], 'ruler': d['ruler'],
//                  'star': d['star'], 'temperament': d['temperament'],
//                  'core_drive': d['core_drive'], 'behavioral_mode': d['behavioral_mode'],
//                  'base_speed': d['base_speed'], 'base_glow': d['base_glow'],
//                  'orbit_radius': d['orbit_radius'], 'restlessness': d['restlessness'],
//                  'approach_bias': d['approach_bias'], 'social_bias': d['social_bias'],
//                  'interaction_radius': d['interaction_radius'],
//                  'horoscope_weight': d['horoscope_weight'],
//                  'star_glow': d['star_glow'], 'ruler_influence': d['ruler_influence'],
//              })
//          print(json.dumps(out, indent=2))
//          " > zodiac_signs.json
//
//   2. Copy zodiac_signs.json into your Unity project's Assets folder.
//
//   3. In the Unity menu: Zodiac > Generate Sign Data Assets
//      Assets are written to Assets/ZodiacData/SignData/.
//      Re-running overwrites existing assets with fresh values — safe to repeat
//      whenever zodiac_schema.py changes.

#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class ZodiacDataGenerator
{
    private const string JsonPath      = "Assets/zodiac_signs.json";
    private const string OutputFolder  = "Assets/ZodiacData/SignData";

    [MenuItem("Zodiac/Generate Sign Data Assets")]
    public static void Generate()
    {
        if (!File.Exists(JsonPath))
        {
            Debug.LogError(
                $"[ZodiacGenerator] {JsonPath} not found. " +
                "Export it from Python first — see the instructions at the top of this file."
            );
            return;
        }

        string raw = File.ReadAllText(JsonPath);

        SignEntry[] entries;
        try
        {
            entries = JsonHelper.FromJson<SignEntry>(raw);
        }
        catch (Exception e)
        {
            Debug.LogError($"[ZodiacGenerator] Failed to parse {JsonPath}: {e.Message}");
            return;
        }

        // Ensure output folder exists
        if (!AssetDatabase.IsValidFolder("Assets/ZodiacData"))
            AssetDatabase.CreateFolder("Assets", "ZodiacData");
        if (!AssetDatabase.IsValidFolder(OutputFolder))
            AssetDatabase.CreateFolder("Assets/ZodiacData", "SignData");

        int created = 0, updated = 0;

        foreach (var entry in entries)
        {
            string assetPath = $"{OutputFolder}/ZodiacData_{Capitalize(entry.name)}.asset";
            var    existing  = AssetDatabase.LoadAssetAtPath<ZodiacData>(assetPath);

            ZodiacData asset;
            if (existing != null)
            {
                asset = existing;
                updated++;
            }
            else
            {
                asset = ScriptableObject.CreateInstance<ZodiacData>();
                created++;
            }

            Populate(asset, entry);

            if (existing == null)
                AssetDatabase.CreateAsset(asset, assetPath);
            else
                EditorUtility.SetDirty(asset);
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        Debug.Log($"[ZodiacGenerator] Done. Created {created}, updated {updated} sign data assets in {OutputFolder}.");
    }

    // -----------------------------------------------------------------------
    // Copy JSON fields into the ScriptableObject
    // -----------------------------------------------------------------------
    private static void Populate(ZodiacData asset, SignEntry e)
    {
        asset.signName        = e.name;
        asset.signIndex       = e.index;
        asset.element         = e.element;
        asset.modality        = e.modality;
        asset.polarity        = e.polarity;
        asset.ruler           = e.ruler;
        asset.star            = e.star;
        asset.temperament     = e.temperament;
        asset.coreDrive       = e.core_drive;
        asset.behavioralMode  = e.behavioral_mode;
        asset.baseSpeed       = e.base_speed;
        asset.baseGlow        = e.base_glow;
        asset.orbitRadius     = e.orbit_radius;
        asset.restlessness    = e.restlessness;
        asset.approachBias    = e.approach_bias;
        asset.socialBias      = e.social_bias;
        asset.interactionRadius = e.interaction_radius;
        asset.horoscopeWeight = e.horoscope_weight;
        asset.starGlow        = e.star_glow;
        asset.rulerInfluence  = e.ruler_influence;
    }

    private static string Capitalize(string s) =>
        s.Length == 0 ? s : char.ToUpper(s[0]) + s.Substring(1);

    // -----------------------------------------------------------------------
    // JSON deserialization helpers
    // JsonUtility doesn't support top-level arrays — wrap and unwrap.
    // -----------------------------------------------------------------------
    private static class JsonHelper
    {
        public static T[] FromJson<T>(string json)
        {
            string wrapped = "{\"items\":" + json + "}";
            var    wrapper = JsonUtility.FromJson<Wrapper<T>>(wrapped);
            return wrapper.items;
        }

        [Serializable]
        private class Wrapper<T> { public T[] items; }
    }

    // -----------------------------------------------------------------------
    // Mirror of the JSON object shape — field names must match JSON keys exactly
    // -----------------------------------------------------------------------
    [Serializable]
    private class SignEntry
    {
        public string name;
        public int    index;
        public string element;
        public string modality;
        public string polarity;
        public string ruler;
        public string star;
        public string temperament;
        public string core_drive;
        public string behavioral_mode;
        public float  base_speed;
        public float  base_glow;
        public float  orbit_radius;
        public float  restlessness;
        public float  approach_bias;
        public float  social_bias;
        public float  interaction_radius;
        public float  horoscope_weight;
        public float  star_glow;
        public float  ruler_influence;
    }
}
#endif