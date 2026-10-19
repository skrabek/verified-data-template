@AGENTS.md

## Claude Code specifics

- `.claude/settings.json` runs `.claude/hooks/guard.py` before every edit and shell command. If it denies
  a call, do not look for another route to the same change. Tell the owner what you were trying to do.
- Edits to the project's rules (`tools/`, `tests/`, `AGENTS.md`, `CLAUDE.md`, `project.json`, `.claude/`)
  ask the owner first. Explain why before making one.
- `tools/decide.py` refuses to run without an interactive terminal. Give the owner the exact command
  in a `bash` code block and wait.
