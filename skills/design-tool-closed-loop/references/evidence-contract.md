# Evidence Contract

## Evidence levels

| Level | Evidence | Permitted claim |
| --- | --- | --- |
| E0 | Plan or prompt only | Planned |
| E1 | Local HTML/CSS/source | Source prepared |
| E2 | Exact-dimension PNG/SVG plus interaction table | Visual draft complete; pending import |
| E3-G | Gundam task visible after submission, observed completion state, retrieved response/artifacts | Executed and verified in Gundam |
| E3-M | Modao project/page visible after edit, preview screenshots, hotspot tests | Updated and verified in Modao |
| E3-F | Figma connector response, page/frame IDs, node IDs, screenshots | Written and verified in Figma |

E3-G does not upgrade to E3-M or E3-F without independent evidence from the target platform.

## Acceptance checklist

- Frame dimensions match the stated targets.
- Typography, spacing, colors, borders, shadows, and content hierarchy were visually checked.
- When a reference is in scope, current and reference captures use the same viewport; the report records dimensions, hashes, overlays, hotspots, and before/after convergence.
- Distinct controls have distinct hit areas and outcomes.
- Blank-area clicks do not trigger unrelated actions.
- Open/close/back flows are tested.
- Desktop/mobile and important component states are covered when in scope.
- Evidence was gathered from the final state.

## Blocked reporting

When blocked, report:

1. The exact gate: login, QR scan, CAPTCHA, connector absent, permission denied, or platform error.
2. The last verified state.
3. Assets and specifications already completed.
4. The single smallest action needed from the user.

Do not repeatedly retry a human gate or imply completion while it remains unresolved.
