---
name: pi05-stage-sync
description: Complete, document, validate, and publish milestone-sized implementation, migration, repair, or acceptance work in laog3550/robot-pika-piper-pi05. Use throughout a concrete PI05 stage task so existing changes are identified before work and a reviewed stage branch and PR can be produced after validation. Do not use for planning, explanations, read-only review, status questions, diagnosis-only requests, or work outside this repository.
---

# PI05 Stage Sync

Manage one auditable PI05 delivery stage from preflight through a GitHub pull
request. Keep automatic invocation enabled, but treat publication as the final
step of an implementation task, never as a background process.

## Start the stage

1. Confirm the task has a concrete deliverable and acceptance condition. Do not
   publish plans, explanations, reviews, status checks, or diagnosis-only work.
2. Run `scripts/preflight.py --mode start <repo-root>`. Stop if the repository
   identity or base ref is wrong. Record the reported HEAD and pre-existing
   changed paths; never claim or overwrite those changes.
3. Fetch `origin/main` and use the available GitHub integration to check for an
   open `stage/*` pull request. Do not begin a new stage branch until it is
   merged or closed.
4. Read [references/workflow.md](references/workflow.md), then allocate or reuse
   the stage number from `docs/status.md`. Create `stage/SNN-<lowercase-slug>`
   from the latest `origin/main`.

## Finish and publish

Publish without another confirmation when the user asked Codex to implement a
matching stage task and all gates below pass. The user's request authorizes a
new stage branch and PR only; it does not authorize merging, tagging, releasing,
force-pushing, or changing unrelated files.

1. Run the checks appropriate to the change. A failed required check blocks
   publication. Never report hardware validation without an actual test record.
2. Update `docs/status.md` and create or update
   `docs/stages/SNN-<slug>.md` according to the workflow reference. Update the
   root README only when setup, public interfaces, repository layout, or overall
   progress changed.
3. List the exact stage paths in a temporary scope file, one repository-relative
   path per line. Run `scripts/preflight.py --mode publish --scope-file <file>
   <repo-root>` and inspect the full diff. Stop for out-of-scope changes,
   sensitive data, generated artifacts, unexplained binaries, or unclear source
   licensing.
4. Stage only the reviewed paths with explicit `git add -- <path>...`. Never use
   `git add -A`, `git add .`, stash, destructive checkout/reset, rebase, or force
   push. Commit once as `stage(SNN): <Chinese stage summary>`.
5. Push the stage branch and create one PR targeting `main`. Do not enable
   auto-merge. Use the PR format in the workflow reference.
6. Read back the remote commit and PR. Report branch, commit, PR URL, validation
   level, and remaining limitations.

## Stop conditions

Keep local work intact and report recovery steps instead of publishing when:

- the repository is not `laog3550/robot-pika-piper-pi05`;
- a previous stage PR is open, `origin/main` diverged, or a merge is required;
- a stage path was already modified before the task or unrelated paths changed;
- required validation failed or a safety issue remains;
- a credential, private device value, build product, bag/log, or unlicensed
  copied source is present;
- work that changes physical robot behavior lacks real hardware evidence. Mark
  such work `等待真机验收`; do not call it hardware-accepted.
