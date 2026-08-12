# Modao Browser Execution

## Prerequisite

Load the current `browser:control-in-app-browser` Skill completely and follow its connection and browser-state rules. Work only in the visible user-authorized session.

## Recommended construction strategy

### Native elements

Use native Modao elements when the user must frequently edit copy, component positions, colors, or interaction links. Keep names stable and group elements by screen/section.

### Image base plus hotspots

For high-fidelity complex screens:

1. Establish an exact frame size such as 1440×900 or 390×844.
2. Render the maintained HTML/CSS source at that exact size.
3. Import the PNG as a locked background/base layer.
4. Add only the necessary transparent hotspots or native controls above it.
5. Name each hotspot after its intent, for example `open-file-preview`, not `hotspot-1`.
6. Keep a coordinate table so the prototype can be recreated after a visual update.

This route improves visual fidelity but does not make the PNG itself natively editable. State that tradeoff explicitly.

## Interaction table

Record at least:

| Field | Example |
| --- | --- |
| Source page | Chat / desktop |
| Element | File attachment row |
| Trigger | Click |
| Bounds | x=812, y=244, w=268, h=56 |
| Action | Open right preview panel |
| Target/state | Chat + preview panel open |
| Return path | Close icon; Esc if supported |

## Verification

- Reopen prototype/preview mode after edits.
- Test every hotspot separately.
- Click blank areas near hotspots to detect oversized hit regions.
- Verify the close/return path.
- Capture the page and its important states.
- Report project URL, page names, target dimensions, and observed behavior.

## Constraints

- Do not inspect or export cookies, access tokens, local storage, or passwords.
- Do not bypass CAPTCHA or QR login.
- Do not claim that an imported bitmap is fully editable.
- Do not publish or change share permissions unless requested.
