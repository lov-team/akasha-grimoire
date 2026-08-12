# Gundam Online Browser Execution

## Production entry

Use `https://agent.lovtoken.com`. Do not depend on LovBrowser/LovContext and do not start the local `gundam-agent` repository unless the user explicitly asks for local development.

The production login page verified on 2026-08-10 exposes one `API Key` password field and a `用 Key 登录` button. Its Base URL is fixed by the server. Inspect the live page every time because the UI may change; do not use obsolete instructions that ask for a Base URL.

## Login gate

1. Open Gundam in the Codex in-app browser and make the tab visible.
2. Inspect the current DOM before locating fields.
3. Prefer asking the user to enter the Key in the visible password field and tell Codex when login finishes.
4. If the user explicitly provides a Key and authorizes entry into `agent.lovtoken.com`, fill and submit it once. Never repeat it in messages, persist it to files/clipboard, inspect browser storage, or include it in screenshots.
5. Verify login only from the resulting authenticated UI. Do not inspect cookies, local storage, passwords, or session stores.

Do not send the Key to any other origin. Stop if the visible domain, TLS state, or login destination differs from the expected production entry.

## Task submission

Submit a bounded task containing:

- Goal: exact output and target platform.
- Inputs: user-authorized files/text and required dimensions.
- Actions: files or artifacts Gundam may create and tools it may use.
- Acceptance: observable outputs, screenshots, or downloadable artifacts.
- Boundaries: forbidden destructive actions, secrets, publishing, and target-platform claims.

Before submitting, confirm the prompt does not accidentally contain unrelated private data. A normal task submission requested by the user is authorized; additional uploads or sensitive data require their own scope.

## Approvals and execution

- Read each Gundam approval dialog. Approve only actions already authorized by the user's task.
- Ask before destructive filesystem operations, publication, permission changes, external messages, or actions outside the stated target.
- Observe progress until a terminal success, failure, or human gate appears.
- If the task produces files or media, retrieve them through the supported browser download/asset flow and verify file existence and usability.
- If Gundam only provides text, treat it as advice or source content, not proof of an external write.

## Platform handoff

- Figma: use the native Figma connector route when callable; require node IDs and screenshots.
- Modao: use the in-app-browser Modao route; require project/page identity and interaction checks.
- Neither available: deliver exact-dimension HTML/PNG/SVG and an interaction table as pending import.

Gundam completion evidence and target-platform completion evidence are separate. Keep both when Gundam contributes assets later imported into Modao or Figma.

## Required evidence

- Final Gundam URL/session state without secrets.
- The submitted task summary with sensitive values omitted.
- Visible terminal result or error/human gate.
- Retrieved artifact paths and dimensions, when present.
- Downstream Modao/Figma evidence if a target-platform update was requested.
