# Team handbook

Every session reads this file. Keep it short.
If you fix the same mistake twice, add a rule here.

## Team rules
- Branches: feat/<spec-id>-short-name
- One logical change per commit
- Open a draft PR when the spec is done. Never push to main.

## Done means
- Every acceptance point in the spec passes
- Tests added or updated for every behavior change
- No new dependencies without asking

## Never
- Touch /payments or /auth unless the spec names them
- Edit a migration that has already shipped
- Turn off a failing test to make CI pass
