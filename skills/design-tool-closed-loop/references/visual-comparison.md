# Visual Comparison and Deterministic Rendering

Use this workflow when a user supplies a reference image, asks for 1:1 fidelity, or rejects a result as visually rough. It complements platform verification; it never proves a Modao or Figma write by itself.

## Reference boundary

- Record the reference source, viewport, pixel dimensions, and intended learning target.
- Extract layout rhythm, hierarchy, spacing, density, color roles, and interaction patterns.
- Do not copy brand names, logos, proprietary icons, copywriting, photographs, or other unlicensed assets.
- Prefer the user's own assets or openly licensed replacements.

## Deterministic production

- Use HTML/CSS or repository-native UI for text-heavy product screens. Do not ask an image model to typeset long UI copy.
- Use image generation only for illustrations, photos, textures, or decorative assets that benefit from it.
- Freeze the viewport and remove runtime network dependencies before capture. Use local/system fonts and local assets.
- Render with `scripts/render_exact_html.py`; it verifies the PNG IHDR against the requested dimensions.
- Render one representative screen first. Inspect it before rendering a full screen set.

```powershell
python scripts/render_exact_html.py .\screen.html .\screen.png --size 1440x900
```

The renderer refuses silent overwrite. Add `--overwrite` only for an intentional revision. If browser discovery fails, pass an absolute Chrome, Chromium, or Edge path with `--browser`.

## Same-viewport comparison

1. Capture current and reference images at exactly the same viewport and scale.
2. Run `scripts/overlay_compare.py`.
3. Inspect the requested overlay, 30% and 70% overlays, the heat map, and the top grid cells in `summary.json`.
4. Convert high-difference areas into a short repair list grouped by structure, spacing, typography, color, and component state.
5. Modify the source, re-render, and compare again.
6. Record whether the overall mean difference and important hotspot values decreased. A lower global score does not excuse a visibly wrong critical component.

```powershell
python scripts/overlay_compare.py .\current.png .\reference.png .\comparison --alpha 0.4 --grid 40
```

The default behavior rejects different image sizes because automatic scaling can hide a wrong viewport. Use `--resize-reference` only when the mismatch is understood and explicitly accepted. The JSON report records original sizes, SHA-256 values, and whether resizing occurred.

## Acceptance record

Record:

- current/reference filenames, source, SHA-256, and original dimensions;
- viewport, device scale, browser, and final PNG dimensions;
- overlay alpha, grid size, overall mean difference, and top hotspot cells;
- repair list and before/after metrics;
- a direct visual inspection result for text overflow, clipping, font fallback, missing assets, and critical states;
- separate platform evidence required by `evidence-contract.md`.

## Provenance

This workflow was informed by the visual-production and overlay-comparison approach in `lov-team/akasha-grimoire` (inspected 2026-08-11). The bundled scripts are independently implemented for this Skill, with stricter same-size defaults, explicit resize opt-in, hashes, Windows browser discovery, and automated tests. Do not represent these additions as an unmodified copy of Akasha.
