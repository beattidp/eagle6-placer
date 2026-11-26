---
name: session-handoff
description: Saves current session progress, blockers, and immediate next steps to STATE.md. Use when wrapping up a coding session, pausing work, or preparing a handoff for the next session.
---

# Session Handoff Protocol

When the user asks to wrap up, pause, or hand off the session, perform the following steps without writing any new feature code:

1. **Review Changes:** Check the conversation history and modified files from the current session.
2. **Update `STATE.md`:** Overwrite `STATE.md` in the project root (or `<folder>/STATE.md` when working inside a pushed sub-task such as `tools/`, leaving root `STATE.md` intact) with:
   - **Current Goal:** The active feature, bug fix, or milestone.
   - **Completed Recently:** Bullet points of verified progress from this session.
   - **In Progress / Blockers:** Unfinished edits, failing tests, or open questions.
   - **Exact Next Step:** The single most immediate file edit or terminal command to run when resuming.
   - **Active Files:** The exact file paths required to continue, so the next agent does not need to scan the repository.
3. **Enforce Brevity:** Keep `STATE.md` factual, scannable, and strictly under 150 lines.
4. **Confirm:** Reply with a one-sentence confirmation that `STATE.md` is updated and ready for the next session.
