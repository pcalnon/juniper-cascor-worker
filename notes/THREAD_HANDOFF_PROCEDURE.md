# Thread Handoff Procedure

**Purpose**: Preserve context fidelity during long-running sessions by proactively handing off to a new thread before context compaction degrades output quality.
**Project**: juniper-cascor-worker
**Last Updated**: 2026-02-25

---

## Why Handoff Over Compaction

Thread compaction summarizes prior context to free token capacity. This introduces **information loss** — subtle details about decisions made, edge cases discovered, partial progress, and the reasoning behind specific implementation choices get compressed or dropped. A **proactive handoff** transfers a curated, high-signal summary to a fresh thread with full context capacity.

---

## When to Initiate a Handoff

Trigger a handoff when **any** of the following conditions are met:

| Condition | Indicator |
| --------- | --------- |
| **Context saturation** | Thread has performed 15+ tool calls or edited 5+ files |
| **Phase boundary** | A logical phase of work is complete |
| **Degraded recall** | The agent re-reads a file it already read, or asks a question it already resolved |
| **Multi-module transition** | Moving between major components |
| **User request** | User says "hand off", "new thread", or similar |

**Do NOT handoff** when:
- The task is nearly complete (< 2 remaining steps)
- The current thread is still sharp and producing correct output
- The work is tightly coupled and splitting would lose critical in-flight state

---

## Handoff Protocol

### Step 1: Checkpoint Current State

Inventory:
1. What was the original task?
2. What has been completed?
3. What remains?
4. What was discovered?
5. What files are in play?

### Step 2: Compose the Handoff Goal

```
Continue [TASK DESCRIPTION].

Completed so far:
- [Concrete item 1]
- [Concrete item 2]

Remaining work:
- [Specific next step 1]
- [Specific next step 2]

Key context:
- [Important discovery or constraint]
- [File X was modified to do Y]
- [Approach Z was rejected because...]
```

**Rules**: Be specific, include file paths, state decisions made, mention test status, keep under ~500 words.

### Step 3: Present to User

Output the handoff goal and recommend starting a new thread with that goal as the initial prompt.

---

## Best Practices

1. **Handoff early, not late** — A handoff at 70% context usage is better than compaction at 95%
2. **Include the verification command** — `pytest tests/ -v`
3. **Don't duplicate CLAUDE.md content** — The new thread already has it
4. **State the git status** — Branch, staged files, uncommitted work
