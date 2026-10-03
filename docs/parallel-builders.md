# Running many builders without conflicts

The limit in this playbook is on **review units**, not agents.
A review unit is one coherent change you can understand, check, and take responsibility for as a whole.
Many builders can feed one review unit if the work is split well.

For how to split the work, see [Claude Code: Subagents vs Agent Teams](https://vinayroy.substack.com/p/claude-code-subagents-vs-agent-teams-54cacb96f6c0).

## Ten tactics, most useful first

1. **Split by ownership.** Give each builder its own folders or files, and write it in the spec. Nobody touches another builder's files.
2. **Enforce it, don't just ask.** Prompts drift. Use [`scripts/check-owner.sh`](../scripts/check-owner.sh) as a `PreToolUse` hook on `Edit|Write`. Exit code 2 stops the edit and tells the agent why.
3. **Lock the contract first.** One builder writes the shared parts first: API shapes, types, the database schema. Review and freeze them. Then build in parallel.
4. **Give busy files one owner.** Routes, config, `package.json`, lockfiles, migrations. One owner each. Everyone else asks that owner for changes.
5. **Set the order up front.** If B depends on A, say so. Agent teams support task dependencies. With separate sessions, write the order into the spec.
6. **Keep changes small and merge often.** Small commits, frequent rebases on main. Small merges mean small conflicts.
7. **Add an integrator.** One session merges the branches, fixes conflicts, and runs the full test suite on the combined code.
8. **Announce contract changes.** When a shared shape changes, message every affected session right away.
9. **Test the whole, not just the parts.** Each branch can pass alone and still break together. Run integration tests on the merged code.
10. **Review once.** Many builders, one combined change, one review unit.

**Short version:** split the work, freeze the shared parts, and put it together in one place.
