# Documentation Guidelines — `.claude/`

This file documents conventions for the `.claude/` directory: context files
loaded into AI-assisted development sessions.  Project-wide documentation
conventions (format, tooling, contribution workflow) belong in the project wiki,
which is available as a git submodule at `wiki/`.

---

## Format

All files in `.claude/` are **Markdown**.  This is a Claude Code requirement:
the tool reads `.claude/` files directly and expects Markdown syntax.

The rest of the project uses **org-mode** for documentation.

---

## Contents of `.claude/`

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project overview and entry point; read first at the start of every session |
| `guidelines/documentation.md` | This file |
| `guidelines/collaboration-protocol.org` | defines protocol for collaboration; read at start of every session |

Design documents (architecture, algorithms, deferred work) belong in the
project wiki, not in `.claude/`.

---

## Writing style

These files are read by AI assistants, not primarily by human contributors.
Write accordingly:

- **Be specific.** Name files, functions, and commands explicitly.
- **Include the *why*.** Explain the reasoning behind decisions, not just the
  decisions themselves.  An AI that understands *why* can generalize to edge
  cases; one that only knows *what* cannot.
- **Don't duplicate the code.** If something is obvious from reading the
  source, don't repeat it here.  Reserve these files for things not derivable
  from the code or git history.
- **Don't duplicate commit messages.** Rationale for specific changes belongs
  in commit messages, not in context documents.

---

## When to update

Update `.claude/` files when:

- A file referenced here is renamed, moved, or deleted
- The repository layout changes significantly
- A new tool, language, or convention is adopted
- Deferred work is completed or its status changes
- An AI assistant makes a mistake that better context would have prevented

---

## What doesn't belong here

| Content | Where it goes |
|---------|--------------|
| Project-wide documentation conventions | `wiki/` |
| Contribution workflow | `wiki/` |
| Architecture and algorithm design documents | `wiki/` |
| Commit-level rationale | Commit messages |
| Code-level explanation | Inline comments |
