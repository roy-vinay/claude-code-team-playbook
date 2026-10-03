# Claude Code Team Playbook

Starter files for running several Claude Code sessions like a small team.
Companion to the article "More Claude Code Sessions Made Me Ship Less. Here's What Fixed It." by Vinay Roy.

## What's inside

| File | What it does |
|------|--------------|
| `.claude/agents/builder.md` | Builds from a spec, in its own worktree |
| `.claude/agents/qa.md` | Tests and tries to break things. Can't edit code |
| `.claude/agents/reviewer.md` | Reads the diff with fresh eyes. Read only |
| `CLAUDE.md` | Team rules every session follows |
| `.claude/settings.json` | Permissions, a test hook, and a nesting limit |
| `specs/TEMPLATE.md` | A one-page spec to start every feature |
| `rework-log.md` | A simple weekly tally to track rework |

## How to use it

1. Copy `.claude/`, `CLAUDE.md`, and `specs/` into your project.
2. Edit `CLAUDE.md` and the hook command to match your stack.
3. Start with two sessions: `claude --agent builder` and `claude --agent qa`.
4. Add the reviewer once those two feel easy.
5. Cap builders at the number of diffs you can truly read in a day.

## Notes

- Commands and settings follow the Claude Code docs at the time of writing. Check https://code.claude.com/docs if something doesn't work.
- The hook assumes `npm`. Swap in your own lint and test commands.
