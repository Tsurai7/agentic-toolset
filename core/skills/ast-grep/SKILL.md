---
name: ast-grep
description: >-
  Search and rewrite source code structurally with ast-grep (AST patterns)
  instead of regex grep. Use whenever searching for a code construct — calls,
  signatures, JSX, imports, error handling — in a supported language.
---

# ast-grep over grep

For **structural** code questions, search by syntax tree with `ast-grep`, not by regex.
Regex matches text; `ast-grep` matches code structure, so it ignores comments,
strings, and formatting differences, and won't produce false hits.

## Default

- **Code structure → `ast-grep`.** Use it for any query about a code construct
  (function calls, definitions, signatures, JSX elements, imports, `catch`
  blocks, decorators, etc.).
- **Text → Grep.** A literal string, identifier, log line, config key, or prose —
  in code files or not — is a text question; use the native Grep tool.

## Usage

```bash
# Find a pattern ($A, $$$ are metavariables: single node / variadic)
ast-grep -p 'useState($A)' -l ts
ast-grep -p 'func ($R *Repo) Save($$$)' -l go
ast-grep -p 'catch ($E) { $$$ }' -l js

# Scope to a path, list files only
ast-grep -p 'console.log($$$)' src/ -l ts

# Structural rewrite (preview, then apply with -U)
ast-grep -p 'foo($A)' -r 'bar($A)' -l ts
```

Run `ast-grep` (not the `sg` alias — `sg` collides with other tools on some
systems).

## When grep is still right

- A literal string, log message, or config key (no code structure involved)
- A file/identifier needle when you already know the exact text
- Files in a language `ast-grep` cannot parse
