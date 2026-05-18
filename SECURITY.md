# Security Policy

## Supported versions

Only the latest `main` branch is supported. There is no LTS line.

## Threat model in two paragraphs

Win:Computer Use gives an MCP client real input authority on a Windows machine: it can move the (virtual or real) cursor, click, type, launch apps, read pixels, capture the screen, and read/write arbitrary files. The default permission model is *allowlist on launch* — the model can only `launch_app` for binaries the user has explicitly approved, and `bypass: true` lifts that. Every tool call is logged to `activity.log`; an OS-level emergency hotkey (`Ctrl+Shift+X`) freezes input until the user resumes.

This means a compromised or misaligned MCP client is the primary risk. Treat the server as a privileged automation surface: only register it with clients you trust, never run with `bypass: true` unattended on a machine with secrets, and review `allowed_apps` periodically.

## Reporting a vulnerability

**Please do not open a public issue.** Email **jn03official@gmail.com** with:

- A description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept.
- The version / commit hash you tested against.
- Any suggested mitigation.

You can expect:

- An acknowledgement within 72 hours.
- A status update within 7 days.
- Coordinated disclosure once a fix is shipped.

If you don't get a response in 7 days, feel free to open a minimal public issue (without the exploit) asking for a maintainer ping.

## What is in scope

- Permission bypass — anything that lets the model execute outside `allowed_apps` without `bypass: true`.
- Emergency stop bypass — anything that lets input continue after `Ctrl+Shift+X` until `emergency_resume`.
- Activity-log gaps — tool calls that mutate system state without being recorded.
- Path traversal / arbitrary file writes outside the user's intent in `write_text_file`, `download_file`, `delete_path`.
- Code execution via crafted MCP messages.

## What is out of scope

- The fact that an MCP client with `bypass: true` can run anything — that's documented behavior, not a vulnerability.
- UAC dialogs not being clickable — that's an OS-level Secure Desktop restriction, by design.
- DoS against the user's own machine via macro loops — local denial of service of yourself is not a security issue.
