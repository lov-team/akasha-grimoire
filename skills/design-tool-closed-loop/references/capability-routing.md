# Capability Routing

## Capability probe

Inspect the current enabled-tool catalog before promising platform writes. Exact tool names may vary by environment; match by callable capability, not folder names.

| Probe | Meaning | Route |
| --- | --- | --- |
| Figma write tool such as `use_figma` is callable | Native Figma canvas reads/writes are possible | A |
| In-app browser control and its Node/Playwright bridge are callable | Visible web UI automation is possible | B for Modao |
| In-app browser control is callable and `https://agent.lovtoken.com` is reachable | Gundam online can be used as an execution surface after user-authorized Key login | C |
| Skills exist but their underlying callable tools do not | Instructions are installed, connector is absent | Do not claim native writes |
| Neither connector nor browser control is callable | Platform mutation is unavailable | D |

## Routing order

1. Use the platform explicitly requested by the user when its real route is available.
2. If Figma was requested but its connector is absent, offer/import-ready local assets; use browser automation for Figma only if the loaded browser instructions support the visible workflow and it can be verified reliably.
3. If Modao was requested and browser control is available, browser UI automation is a valid execution route even without a public API or MCP.
4. If the user selects Gundam, use the in-app browser against its online production entry. Do not require LovBrowser and do not start the local Gundam repository unless explicitly asked.
5. Gundam is an execution surface, not automatic evidence that a separate target platform changed. Pass its artifacts to the actual Figma/Modao route and verify there.
6. If authentication blocks the target, pause only authenticated actions. Continue source design, rendering, asset preparation, naming, and interaction mapping.

## Failure handling

- Re-inspect after navigation or modal changes; do not reuse stale selectors blindly.
- If browser automation becomes unreliable, reduce scope to deterministic actions and switch complex visuals to image-base import.
- If a Figma tool call fails, preserve returned errors and do not fabricate node IDs.
- A missing connector is a route decision, not a reason to abandon the whole design task.
