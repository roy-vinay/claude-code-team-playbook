# Claude Code Team Playbook

**AI made code cheap. Review is now the scarce resource.**
This playbook organizes coding agents around that one constraint.

Companion to the article *More Claude Code Sessions Made Me Ship Less. Here's What Fixed It.* by Vinay Roy.

---

## Why this exists

Running more coding agents did not make me ship more.

It gave me more unfinished work, longer review queues, and more rework.
The agents were fast. I was the bottleneck.
I could only read so many diffs a day, and I started skimming them.

This repo is the workflow I ended up with. It is small on purpose.

## The operating model

```
               ONE-PAGE SPEC
                     │
                     ▼
                  BUILDER
             own worktree
                     │
                     ▼
                   DIFF
                     │
            ┌────────┴────────┐
            ▼                 ▼
           QA             REVIEWER
      tries to break     fresh eyes,
      cannot edit code    read only
            │                 │
            └────────┬────────┘
                     ▼
               HUMAN REVIEW
                     │
              ┌──────┴──────┐
              ▼             ▼
            MERGE         REWORK
                            │
                            └──→ log it

  ╔═══════════════════════════════════════╗
  ║  Builders ≤ diffs you can truly read  ║
  ╚═══════════════════════════════════════╝
```

Four rules, and nothing else:

1. **One spec.** Nothing starts without a one-page spec.
2. **Three roles.** Builder, QA, Reviewer. Each does one job.
3. **One limit.** Never run more builders than the diffs you can properly read today.
4. **One metric.** Measure shipped work and rework, not code generated.

## Why the roles are separate

**Why can't QA edit code?**
If QA can fix what it tests, it becomes a second builder.
Its goal quietly shifts from "find what's broken" to "make my version pass."
A QA role that can only run and report stays honest.

**Why does the reviewer start fresh?**
A session that wrote the code, or watched it being written, shares its blind spots.
A reviewer with no context has nothing to defend.
It reads the diff the way a new teammate would.

**Why must the builder list what it skipped?**
"Done!" is not a report.
A list of what was not done, and what could go wrong, tells you where to look first.

## The constraint

Your review capacity sets your team size. Not your token budget.

For most people, that's two or three builders a day.
On a heavy meeting day, one.
QA and research sessions don't count. Only sessions that make code you must review.

More builders than that does not raise output.
It raises the number of diffs nobody reads properly.

## Does it work?

This section will hold real observations, not lab results.
I'm tracking the same workflow before and after the change, using `rework-log.md`.

| Period | Builders | Changes shipped | Sent back | Review hours |
|--------|----------|-----------------|-----------|--------------|
| Before | —        | —               | —         | —            |
| After  | —        | —               | —         | —            |

Numbers will be added as they come in. They are operational notes from one person's work, not a controlled study.

## Why not Claude Code agent teams?

Claude Code has an experimental agent teams feature, where a lead session coordinates teammates.
It's a good fit when you want the agents to organize themselves.

This playbook makes a different trade:

- **Separate sessions, not one coordinated team.** Each role has its own context, so the reviewer stays truly independent.
- **Explicit human gates.** A person reads every diff before merge.
- **A hard work-in-progress limit.** The number of builders is set by your review capacity, not by what the tool can run.

Use agent teams for speed. Use this when review quality is the thing you can't afford to lose.

---

## What's inside

| File | What it does |
|------|--------------|
| `.claude/agents/builder.md` | Builds from a spec, in its own worktree |
| `.claude/agents/qa.md` | Tries to break the feature. Can't edit code |
| `.claude/agents/reviewer.md` | Reads the diff with fresh eyes. Read only |
| `CLAUDE.md` | Team rules every session follows |
| `.claude/settings.json` | Permissions, a test hook, and a nesting limit |
| `specs/TEMPLATE.md` | The one-page spec every feature starts from |
| `rework-log.md` | Weekly tracking of shipped work and rework |

## How to use it

1. Copy `.claude/`, `CLAUDE.md`, and `specs/` into your project.
2. Edit `CLAUDE.md` and the hook command to match your stack.
3. Start with two sessions: `claude --agent builder` and `claude --agent qa`.
4. Add the reviewer once those two feel easy.
5. Fill in `rework-log.md` every week. Add a builder only when rework goes down.

## Notes

- Commands and settings follow the [Claude Code docs](https://code.claude.com/docs) at the time of writing. Check there if something doesn't work.
- The hook assumes `npm`. Swap in your own lint and test commands.
