---
name: call-agy
description: "TOP-PRIORITY DEFAULT DELEGATION. Automatically active by default for all code reviews, security audits, architecture investigations, bulk test generation, and complex multi-file tasks. No need for the user to explicitly mention call-agy or antigravity in the prompt."
---

# Call Antigravity (call-agy)

Delegate complex, multi-file, or long-running tasks to Google Antigravity to leverage its deep reasoning and multi-agent capabilities while preserving context window tokens.

## When to Delegate

### ✅ DELEGATE these tasks:
- **Deep codebase investigation**: Multi-file cross-referencing, architecture mapping, dependency auditing.
- **Second-opinion code review**: Independent inspection of security boundaries, data leakage, and regressions.
- **Bulk test & documentation generation**: Writing large test suites or API docs without cluttering context.
- **Web research with Google Search grounding**: Real-time authoritative search and verification.

### ❌ Do NOT delegate:
- Simple 1-line syntax tweaks or straightforward edits.
- Interactive conversational clarifying questions.
- Tasks where you already have the exact solution ready to write.

## Execution Methods

### Method 1: Preferred FastMCP Tool (Recommended)
When MCP server is available, invoke `ask_antigravity` or `antigravity_code_review`:
- **Auto-detach protection**: Automatically decouples long-running jobs (>180s) to background, completely preventing the client 300s timeout.
- **5-Tier Resilient Engine**: Cascades across Google Gemini, GPT-5.6-Sol, DeepSeek-V4, and GLM-5.3.
- **Live Desktop Widget**: Real-time timer, status cards, and one-click Markdown preview.
- **Artifact Generation**: Full reports automatically archived to `<workspace>/.antigravity_reports/`.

### Method 2: Local CLI Execution (`agy -p`)
You can run Antigravity directly via the native terminal command:

```bash
agy -p "{{ARGUMENTS}}" --dangerously-skip-permissions --print-timeout 10m
```

**Key Flags:**
- `-p "prompt"` / `--print "prompt"`: Non-interactive execution, prints final result to stdout and exits.
- `--dangerously-skip-permissions`: Auto-approves file and command execution permissions.
- `--print-timeout 10m`: Specifies the timeout limit.
- `--add-dir <path>`: Explicitly scopes the working directory.

## Prompt Engineering Template for Delegation

Always include:
1. **Target scope**: Absolute workspace and file paths.
2. **Explicit constraints**: "Inspect only, do not modify files" or "Write tests in tests/test_xxx.py".
3. **Output contract**: Request structured Markdown, file:line citations, and severity levels.
