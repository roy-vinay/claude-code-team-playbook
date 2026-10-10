---
description: Start a ticket by claiming the code it will touch, before editing anything
argument-hint: <TICKET-ID>
---

You are starting ticket $ARGUMENTS. Do not edit any file until the claim below is accepted.

1. Read the ticket's spec in `specs/` (or ask the user for the ticket text if there is none).
2. Read the code it involves. List what you expect to change:
   - folders your ticket owns outright, as `path/`
   - single files, as `path/to/file.py`
   - in a hot file (see `hot_files` in `.claims.toml`), only the functions you will change, as `path/to/file.py::function_name`
   List shared code you will only *read* separately; reading needs no claim.
3. Claim it, with a one-line reason:
   `claims/claims propose --ticket $ARGUMENTS --reason "<why>" <target> <target> ...`
4. If the result is ACCEPTED, start work on branch `feat/$ARGUMENTS-<short-name>` and run
   `claims/claims export --ticket $ARGUMENTS -o .claims/$ARGUMENTS.json`, then commit that file with your first change.
5. If the result is PENDING, stop. Tell the user exactly what you asked for and who was asked.
   Check again with `claims/claims status --ticket $ARGUMENTS`. Do not build a workaround in the meantime.
6. If you later find you need something outside your claim, stop and propose it before touching it.
   Explain what you need, who owns it, and what you have and have not changed so far.
7. When the work is merged, run `claims/claims release --ticket $ARGUMENTS`.
