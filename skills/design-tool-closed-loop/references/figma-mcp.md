# Figma Native Execution

## Prerequisite

Native Figma execution requires the actual callable Figma connector, normally `use_figma`. Installed Figma Skills alone are not evidence of connectivity.

Before each write, load the current `figma-use` Skill completely. For composed screens load `figma-generate-design`; for new files load `figma-create-new-file` before calling its tool. These prerequisite Skills define the authoritative call patterns.

## Execution sequence

1. Confirm the target file and page, or create the requested file through the supported tool.
2. Inspect existing variables, components, styles, and relevant frames.
3. Reuse the design system where possible.
4. Build incrementally by section/frame; avoid one giant opaque operation.
5. Name pages, frames, components, and layers semantically.
6. Capture returned node IDs after successful writes.
7. Read back or screenshot the final frames and compare them with the request.

## Required evidence

- File URL/key or connector-provided file identity.
- Page and top-level frame names.
- Returned node IDs for created/updated frames or components.
- Screenshot of each final top-level frame or important state.
- Notes on reused variables/components and any unresolved fallback assets.

Without connector responses and node IDs, use the label `pending import`, never `written to Figma`.

## Connector-absent fallback

Deliver exact-dimension HTML/PNG/SVG and the interaction specification. If `.fig` export is unavailable, do not invent one. Tell the user which assets to import and which objects will remain rasterized.
