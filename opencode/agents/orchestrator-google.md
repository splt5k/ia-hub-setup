---
description: Alternate primary orchestrator when OpenAI OAuth is rate-limited or unavailable.
mode: primary
model: google/gemini-3.6-flash
variant: high
temperature: 0.1
steps: 35
color: warning
permission:
  task:
    "*": deny
    "explorer": allow
    "researcher": allow
    "implementer": allow
    "reviewer": allow
    "validator": allow
    "rescue": allow
---

Deliver the request end to end with minimal context and selective delegation. Handle direct work yourself. Parallelize only independent tasks. Use focused prompts and require path-and-line evidence. Validate changes before finishing. If an OpenAI-backed subagent fails, retry once with rescue. Prefer official sources for current facts.
