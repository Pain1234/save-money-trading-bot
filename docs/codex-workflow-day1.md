# Day-1: Cursor–Codex workflow

After PR #187 is merged into `main`:

1. Open Cursor on `C:\Users\justi\Projects\save-money-trading-bot` (not the Figma plugin cache).
2. `git checkout main && git pull`
3. Create a feature branch from `main` for the next issue.
4. Ensure Codex CLI: `codex --version` (install: `npm i -g @openai/codex`) and `codex login` if needed.
5. Implement → tests → commit on the feature branch.
6. **Windows local:** live gate is fail-closed (`OS isolation not available`). Use mock/prep only; run live `APPROVED` under **WSL or Linux CI**.
7. Live gate (Linux/WSL):

```powershell
pwsh -ExecutionPolicy Bypass -File .agent-loop/run-codex-review.ps1 -BaseRef origin/main
```

8. Address confirmed BLOCKER/MAJOR (max 3 rounds), require `APPROVED` on current HEAD.
9. Push PR, wait for required CI; **human merges** — no auto-merge/deploy.