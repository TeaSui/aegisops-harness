# Visual companion

A local server that shows HTML screens in the browser and records the user's clicks. Use it per question, only when seeing beats reading (mockups, layouts, diagrams, side-by-side visual options, look and feel). Requirements, conceptual choices, tradeoffs and API or data decisions stay in the terminal, even when the topic is UI.

## Start

From the plugin root:

```bash
skills/spec/scripts/start-server.sh --project-dir <project root>
```

It prints JSON with `url`, `screen_dir`, `state_dir`; keep them and give the user the URL. `--project-dir` keeps screens in `<project>/.brainstorm/` across restarts (remind the user to gitignore it); without it they go to `/tmp` and are deleted on stop. Lost output → read `<state_dir>/server-info`.

| Host | Launch |
|---|---|
| Claude Code, macOS/Linux | as above (it backgrounds itself) |
| Claude Code, Windows | as above with the Bash tool's `run_in_background: true`; read `server-info` next turn |
| Codex | as above (auto-detects `CODEX_CI`, runs in foreground) |
| Gemini CLI or hosts that reap detached processes | add `--foreground` and run it with the host's background mechanism |

URL unreachable (remote/container) → add `--host 0.0.0.0 --url-host localhost`.

## Loop

1. Before each screen, check `<state_dir>/server-info` exists and `server-stopped` does not; otherwise restart (it exits after 30 minutes idle).
2. Write a new file to `screen_dir` with the Write tool (never cat/heredoc, never reuse a name: `layout.html`, `layout-v2.html`). The newest file is served.
3. Tell the user the URL, one line on what is shown, and to answer in the terminal (clicking is optional); end the turn.
4. Next turn: the terminal reply is primary; `<state_dir>/events` (JSON lines `{"type":"click","choice":…,"text":…,"timestamp":…}`, cleared on each new screen, absent if no clicks) adds the selections; the last choice is usually final.
5. Iterate with a new version until this question is settled. When the conversation moves back to text, push a `waiting-<n>.html` screen ("Continuing in terminal…") so a stale choice is not left up.
6. Done: `skills/spec/scripts/stop-server.sh <session dir>`.

## Screens

Write fragments (no `<html>`, CSS or scripts); the server wraps them in `scripts/frame-template.html` (theme, header, selection bar, `scripts/helper.js`). A file starting with `<!DOCTYPE` or `<html` is served as is plus the helper.

Classes: `h2` title, `.subtitle`, `.section`, `.label`; `.options` > `.option[data-choice][onclick="toggleSelect(this)"]` > `.letter` + `.content` (add `data-multiselect` on `.options` for multi-select); `.cards` > `.card` > `.card-image` + `.card-body`; `.mockup` > `.mockup-header` + `.mockup-body`; `.split` (two columns); `.pros-cons` > `.pros` / `.cons`; wireframe parts `.mock-nav`, `.mock-sidebar`, `.mock-content`, `.mock-button`, `.mock-input`, `.placeholder`.

2-4 options per screen, the question stated on the page, fidelity matched to the question, real content when it affects the judgment.
