---
name: resume-session
description: Rapidly restores context at the start of a session by reading STATE.md and active files without scanning the full codebase. Use when starting a new session, resuming work, or catching up on a project.
---

# Session Resume Protocol

When the user asks to resume work, catch up, or start a session, execute these steps immediately in order:

1. **Read State First:** Read `STATE.md` in the project root (and check for any pushed `<folder>/STATE.md` such as `tools/STATE.md` if resuming an active sub-task). Do NOT run directory listings, broad searches, or full-repo scans.
2. **Inspect Active Files Only:** Read only the specific file paths listed under the `Active Files` section of `STATE.md`.
3. **Check Working Tree (Optional):** If `STATE.md` mentions uncommitted changes or failing tests, run a lightweight status check (such as `git status -s`) to confirm the workspace matches the recorded state.
4. **Brief Summary & Action:** Give a 3-bullet summary of where work stopped, highlight any active blockers, and ask for confirmation to execute the **Exact Next Step** (or begin immediately if the user already asked you to proceed).
