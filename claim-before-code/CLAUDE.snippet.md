## Claims (add to CLAUDE.md or AGENTS.md)
- Before editing any file, claim what you will change: `claim-before-code/cbc propose <targets> --reason "..."`.
- Only edit targets your ticket holds an accepted claim on. Reading needs no claim.
- If a claim is PENDING or DECLINED, stop and tell the user who was asked and what they said. Never build a workaround or a temporary copy of someone else's code.
- If you discover you need something outside your claim, propose it first. Say what you need, who owns it, and what you have and haven't changed.
- In hot files, claim single functions: `path/to/file.py::function_name`.
