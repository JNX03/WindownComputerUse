# Contributing to Win:Computer Use

Thanks for your interest — issues and PRs are welcome.

## Ground rules

1. **Keep tools small and composable.** The AI composes them; one tool should do one well-named thing.
2. **Default to `PostMessage` for mouse/keyboard.** Real-cursor synthetic input disturbs the user. If an app needs it (Chromium, games, Paint canvas), accept `use_real_cursor: bool = False` so the caller opts in.
3. **Every new tool must go through `@announced(...)`** so calls appear in `activity.log` and are gated by the emergency-stop flag.
4. **Respect the permission model.** Anything that launches an app must check `permission.allowed("name.exe")` unless `bypass` is set.
5. **No silent failures.** Tools should raise with a useful message — the model needs the error text to recover.

## Dev setup

```powershell
git clone https://github.com/JNX03/WindownComputerUse
cd WindownComputerUse
./setup.bat
```

For Python-only work you can skip Electron and just:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 server.py    # MCP stdio server
```

## Running the server against your client

After registering with Claude Code / Desktop / Codex / OpenCode (see README), restart the client. The MCP server runs as a stdio subprocess — logs land in `activity.log` next to the repo.

## Testing changes

There is no formal test suite yet. Until there is, every PR should:

- Pass `python -c "import server"` (server module imports cleanly).
- Run the affected tool by hand against an MCP client and paste the relevant `activity.log` lines in the PR description.
- If you touched the overlay or the Electron manager, include a short screen recording or screenshot.

## Pull requests

- Branch from `main`. Squash before merging if your branch has scratch commits.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`). Keep subjects under 70 chars.
- Reference any related issue with `Fixes #123` so it auto-closes.
- Don't bundle unrelated changes. One concern per PR.

## Reporting bugs

Use the bug-report issue template. Include:

- Windows build (`winver`).
- Python version (`py -3.12 --version`).
- The exact tool call and the line from `activity.log`.
- A screenshot if it's visual.

## Security

Don't open public issues for security problems. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree your contributions are licensed under the MIT License (same as the project).
