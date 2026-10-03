# Rework log

The question this log answers:
**Does running more agents increase shipped work, or just generated code?**

Fill in one row per week. It takes two minutes.

## How to count

- **Builders:** how many builder sessions ran at once, on a normal day.
- **Started:** features or changes a builder began.
- **Shipped:** changes merged and live.
- **QA returns:** times QA sent work back.
- **Review returns:** times you sent work back after reading the diff.
- **Review hours:** rough hours you spent reading diffs.
- **Rework rate:** (QA returns + review returns) ÷ changes reviewed.

## Weekly log

| Week | Builders | Started | Shipped | QA returns | Review returns | Review hours | Rework rate | What I changed |
|------|----------|---------|---------|------------|----------------|--------------|-------------|----------------|
|      |          |         |         |            |                |              |             |                |

## How to read it

- **Started climbs, shipped doesn't:** you have more builders than you can review. Cut one.
- **Rework rate climbs:** a role file, the spec, or `CLAUDE.md` is missing something. Fix that before adding anything.
- **Rework falls and review hours hold steady:** you may be ready for one more builder.
- **Review hours climb faster than shipped work:** you're skimming. Slow down.
