---
name: design-tool-closed-loop
description: Execute and verify product-design work through Modao (墨刀), Figma, the Gundam online agent at agent.lovtoken.com, or a local HTML/PNG/SVG fallback, including same-viewport reference comparison and exact-size rendering. Use when the user asks Codex to create, edit, align, import, prototype, add interactions, or verify screens in 墨刀/Figma; asks for 1:1 fidelity to a reference image; asks Codex to operate Gundam with the in-app browser and a user-authorized Key login; when a previous agent says there is no API or MCP; or when a design task must produce auditable evidence instead of a mock claim.
---

# Design Tool Closed Loop

## Purpose

Turn design requests into a real, verifiable delivery. Do not stop merely because a platform lacks a public API or an MCP connector. Detect available capabilities, choose the strongest truthful route, execute what is possible, and read the result back before declaring completion.

Use the five-point record throughout the task:

1. Goal — target platform, screens, dimensions, interactions, and fidelity.
2. Current state — source files, target URL, login state, enabled tools, and existing design structure.
3. Actions — concrete edits and the route used.
4. Acceptance — screenshots, URLs, node IDs, page names, and interaction checks.
5. Risks/blockers — authentication, missing connector, destructive action, or unsupported platform behavior.

## Required Workflow

### 1. Audit before acting

- Inspect the available tool catalog; do not infer availability from installed Skill folders alone.
- Check whether the user supplied a Modao/Figma URL, a Gundam task, reference image, source HTML, or dimensions.
- Inspect the target non-destructively before editing.
- Treat login, QR scan, CAPTCHA, and SSO as a human gate. Ask the user to complete the gate in the visible app; never request or extract cookies, tokens, passwords, or local-storage credentials.
- Read [capability-routing.md](references/capability-routing.md) before selecting a route.

### 2. Route to the strongest real capability

Choose exactly one primary route and state it briefly to the user.

#### Route A — native Figma connector

Use only when the current tool catalog contains the required Figma write tool, normally `use_figma`.

- Load the available `figma-use` Skill completely before every Figma write call.
- For a full screen, page, modal, drawer, or panel, also load the available `figma-generate-design` Skill.
- If a new file is required, load the available `figma-create-new-file` Skill before its tool call.
- Read [figma-mcp.md](references/figma-mcp.md) and follow its evidence contract.
- Installed Figma Skills without an active connector do not count as Figma write capability.

#### Route B — Modao through the in-app browser

Use when browser control is enabled and the user can open or authenticate to Modao.

- Load `browser:control-in-app-browser` completely before using its browser-control tools.
- Read [modao-browser.md](references/modao-browser.md).
- Prefer editable native Modao elements for high-value text, controls, and hotspots when reliable.
- For visually complex screens, prefer a fixed-size HTML/CSS render imported as a PNG base plus narrowly bounded Modao hotspots. Preserve the HTML/CSS as the editable visual source.
- Never create a page-sized hotspot. Each clickable region must map to one intended action.

#### Route C — Gundam online through the in-app browser

Use when the user wants Gundam to perform or assist with the work and browser control is enabled.

- Do not depend on LovBrowser, LovContext, or a local Gundam process.
- Open the production entry `https://agent.lovtoken.com` in the in-app browser.
- Load `browser:control-in-app-browser` completely before browser actions, then read [gundam-browser.md](references/gundam-browser.md).
- Treat Key entry as a sensitive login gate. Prefer the user entering it in the visible page. If the user explicitly supplies a Key and authorizes transmission to this exact domain, it may be filled once without echoing, logging, persisting, or exposing it in screenshots.
- After login, submit a structured task, observe approvals and outputs, and read the final result back. Never treat Gundam's textual assertion as proof that Modao or Figma changed.
- Route any generated assets onward to Route A or B for target-platform writes; otherwise deliver them under the local-draft evidence level.

#### Route D — local design delivery

Use when neither native Figma writes nor authenticated Modao browser work is available.

- Build the screen in HTML/CSS or repository-native UI code.
- Render exact-dimension PNG assets; provide SVG only when it improves editability or import.
- Produce a hotspot/interaction table with source screen, target screen, event, bounds, and state change.
- Mark this result as `visual draft / pending import`; do not say it was added to Modao or Figma.
- If browser control later becomes available, continue from these assets instead of restarting.

### 3. Apply human and destructive-action gates

- Prefer that the user handles Key entry, QR scan, CAPTCHA, and SSO in the visible client. A Key may be entered by Codex only after narrow, explicit authorization for the exact destination.
- Ask before deleting pages/nodes, overwriting a substantial existing design, publishing, transferring ownership, or changing share permissions.
- Normal in-scope creation and reversible edits do not require extra confirmation.

### 4. Read back and verify

Read [evidence-contract.md](references/evidence-contract.md). Verification is mandatory.

- Compare the result against requested dimensions, visual hierarchy, content, component states, and interaction bounds.
- When a reference image or 1:1 requirement exists, read [visual-comparison.md](references/visual-comparison.md), render at the same viewport, run the overlay comparison, turn hotspots into a repair list, and verify that the revision converges.
- For text-heavy screens, prefer deterministic HTML/CSS or repository-native UI. Use generated imagery for illustrations, photos, and textures rather than long UI copy.
- Test intended hotspots one by one and sample non-interactive blank areas for accidental navigation.
- Capture evidence after the final edit, not only before it.
- If a platform action fails, record the exact blocker and continue all route-independent work.

### 5. Report truthfully

Use one of these completion labels:

- `Written and verified in Figma` — requires connector responses, file/page/frame identity, node IDs, and screenshots.
- `Updated and verified in Modao` — requires project/page identity, preview evidence, and interaction checks.
- `Executed and verified in Gundam` — requires the Gundam session state, submitted task, observed completion, and retrieved artifacts; this label does not imply a Modao/Figma write.
- `Local visual draft complete; pending import` — requires source, exact-dimension render, and interaction specification.
- `Blocked at human gate` — identify the visible gate and list what is already complete.

Never convert “assets prepared” into “platform updated.” Never treat a generated mock, screenshot, or guessed node ID as proof.

## Interaction Acceptance Rules

- Define every interaction by trigger, bounded hit area, action, target/state, and return path.
- A button/card may not inherit a page-wide click target.
- Resizable or closable panels must expose separate drag/resize and close affordances.
- Desktop and mobile variants must specify breakpoint or frame size; voice input needs idle, listening, processing, permission-denied, and error states when requested.
- For prototype navigation, verify each distinct control reaches its own expected state or screen.

## Handoff

End with:

- route used and why;
- files or platform URL;
- Figma page/frame/node IDs or Modao page names;
- Gundam session/task evidence when Route C was used;
- screenshots/renders;
- reference source, viewport, hashes, and before/after visual-difference metrics when a fidelity comparison was required;
- interaction checks performed;
- remaining blockers and the smallest next action.
