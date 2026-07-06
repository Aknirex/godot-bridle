# Low Poly Prototype Pack

The following block is the deterministic parser boundary. Free-form design notes
above or below this block are advisory until an LLM/Agent converts them into the
same structured schema.

```bridle-assets
{
  "assets": [
    {
      "asset_id": "hero_knight",
      "kind": "model_3d",
      "title": "Low-poly knight hero",
      "purpose": "Playable prototype character for the first combat test.",
      "description": "A compact low-poly knight with a readable silhouette and simple armor.",
      "style_tags": ["low-poly", "fantasy", "prototype"],
      "target_res_path": "res://bridle/generated/hero_knight/source/asset.glb",
      "priority": 1,
      "dependencies": [],
      "constraints": {
        "camera": "third_person",
        "approx_height_m": 1.8
      },
      "acceptance": {
        "required_format": "glb",
        "godot_import_required": true,
        "target_res_path": "res://bridle/generated/hero_knight/source/asset.glb",
        "scale_hint": "human sized, approximately 1.8m",
        "style_tags": ["low-poly", "fantasy"],
        "must_include": ["helmet", "sword", "simple armor"],
        "must_not_include": ["photorealistic", "gore"],
        "max_provider_attempts": 2,
        "manual_review_required": true
      }
    }
  ]
}
```
