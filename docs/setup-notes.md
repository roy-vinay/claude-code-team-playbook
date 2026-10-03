# Setup notes

Details that help in practice but would clutter the README.
Check the [Claude Code docs](https://code.claude.com/docs) if anything has changed.

## Limits worth knowing

- **Effort.** Set it per role in the agent file. Low or medium for routine work. High or xhigh for review. Max only for a truly hard bug.
- **Nesting.** Agents can start other agents, three levels deep by default. This repo sets `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` to 1. Deep chains are hard to review.
- **Concurrency.** Up to 20 subagents can run at once by default. Raise it with `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`. If you hit the limit, you likely have more work than anyone can review.

## Running the standup

- `claude agents` shows every session: working, waiting on you, or done.
- Check in this order: waiting on me, then done, then taking too long.
- Name sessions by job, like `builder-refunds`. "Session 4" tells you nothing.

## Messages between sessions

- Ask one session to tell another about a change: "Tell @qa-refunds the order API changed."
- Press `Ctrl+O` to read a message in full.
- Run `/list-agents` to see which sessions you can reach.

## Same context or fresh eyes?

- **Need the current chat's context?** Use `/subtask`. It starts a helper that knows everything said so far.
- **Need fresh eyes?** Start a new session. Always do this for review.

## Calling a role

- For a whole session: `claude --agent qa`
- Mid-chat, by name: `@agent-reviewer check the refund flow changes`

## Checking in from your phone

With Remote Control, your sessions show up in the Claude app, so you can unblock one away from your desk.

## Cost

Every session, subagent, and message between sessions uses tokens. Cloud review uses more.
But your review time is usually the bigger cost.

- Use a smaller, faster model for routine roles. Save the strongest model for review.
- Keep effort low on boring work.
- Track monthly token spend next to review hours. If both rise together, you added agents faster than structure.

## When to stick with one session

- **The codebase is small.** Two agents will keep stepping on each other.
- **The change touches everything.** A big refactor across shared files doesn't split well.
- **You can't review today.** Back-to-back meetings? Run one builder, or none.
- **You're still figuring out the problem.** Explore in one session first. Split the work once you know what to build.
