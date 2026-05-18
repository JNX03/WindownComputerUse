<!-- Thanks for the PR! A few things to tick before review. -->

## Summary

<!-- One-paragraph "what" and "why". Link the issue with "Fixes #123" if applicable. -->

## Changes

- 
- 

## Checklist

- [ ] New / changed mouse & keyboard tools default to `PostMessage` (real-cursor fallback opt-in via `use_real_cursor: True`).
- [ ] New tools are wrapped with `@announced(...)` so they show up in `activity.log`.
- [ ] Tools that launch apps respect the `permission` allowlist.
- [ ] `python -c "import server"` still passes.
- [ ] README / docs updated if the public surface changed.
- [ ] Commit subjects follow Conventional Commits and are < 70 chars.

## Test plan

<!-- How you verified this. Paste activity.log lines, screenshots, or a short clip. -->

- [ ] 
- [ ] 
