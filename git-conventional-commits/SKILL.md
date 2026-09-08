---
name: git-conventional-commits
description: Generate, revise, review, and validate Git commit messages according to Conventional Commits 1.0.0. Use when the user asks for a commit message, requests a Git commit, wants staged or working-tree changes summarized as a commit, or asks whether a commit message follows the Conventional Commits specification.
---

# Conventional Commits

Generate accurate Conventional Commit messages from the actual change set. Follow repository-specific commit rules when they are stricter than this skill.

## Source of Truth

Read `references/specification-v1.0.0.md` when validating edge cases, explaining the standard, or handling bodies, footers, or breaking changes. It contains the normative Conventional Commits 1.0.0 rules copied from the official specification.

## Workflow

1. Read repository instructions that govern commits, including `AGENTS.md`, contributing documentation, and commit-lint configuration when present.
2. Inspect the relevant changes before drafting:
   - For a requested commit, inspect `git status --short` and `git diff --cached`.
   - If nothing is staged, do not silently infer that all working-tree changes belong in one commit. Follow the user's requested scope or ask only when the intended change set is materially ambiguous.
   - For message-only requests, use the diff, summary, or change description supplied by the user.
3. Inspect recent commit subjects when needed to infer repository-specific types, scopes, language, and capitalization.
4. Determine the change's primary intent, then choose the type and optional scope.
5. Identify whether the change breaks a public API, configuration contract, data format, or other compatibility promise.
6. Draft the smallest message that accurately covers the entire selected change set.
7. Validate the message against the checklist below before returning it or using it in `git commit`.

Do not create a commit unless the user explicitly requests one.

## Message Structure

Use this structure:

```text
<type>[optional scope][optional !]: <description>

[optional body]

[optional footer(s)]
```

The description is required. Separate a body from the header with one blank line. Separate footers from the body with one blank line.

## Type Selection

- Use `feat` for a new user-visible or API capability.
- Use `fix` for a bug fix.
- Use repository-defined types when available.
- When the repository has no type policy, these common types may be used: `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, and `revert`.
- Choose the type from intent, not merely from the files changed. A test added with a bug fix normally remains `fix`, while test-only maintenance may be `test`.
- Do not label behavior-changing work as `chore` merely because no narrower type is obvious.
- If unrelated intents cannot be represented honestly by one header, recommend splitting the changes into separate commits instead of inventing a vague message.

## Scope Selection

- Add a scope only when it supplies useful context.
- Use a short noun naming the affected package, component, subsystem, or feature.
- Prefer established scopes from recent repository history or commit-lint configuration.
- Omit the scope when the change is repository-wide or no stable scope is evident.

## Breaking Changes

Mark a breaking change with `!` immediately before `:` or with a `BREAKING CHANGE: <description>` footer. Use both when the repository convention requires both or when the footer is needed to explain migration impact.

Do not infer a breaking change solely from a large diff. Verify that an external compatibility contract changed. Never invent migration details.

## Writing Defaults

Unless repository instructions or the user specify otherwise:

- Write the type in lowercase.
- Write the description in concise imperative English.
- Start the description with lowercase text unless a proper noun or identifier requires otherwise.
- Omit a trailing period from the header.
- Keep the header at or below 72 characters when practical.
- Use the body to explain motivation, context, and important consequences rather than restating the diff.
- Use footer tokens compatible with Git trailers, such as `Refs: #123` or `Reviewed-by: Name`.

These are consistency defaults, not requirements of Conventional Commits 1.0.0.

## Validation Checklist

Confirm all of the following:

- The header has a type, optional parenthesized scope, optional `!`, then `: ` and a non-empty description.
- `feat` is used for a feature and `fix` for a bug fix.
- The message describes all and only the selected changes.
- The scope, if present, is a noun describing a section of the codebase.
- A breaking change is marked in the header or footer.
- `BREAKING CHANGE` is uppercase when used as a footer token.
- Body and footers have the required blank-line separation.
- Every footer has a valid token and separator.
- No issue number, breaking impact, or implementation claim has been invented.

## Output

For a message-generation request, return only the proposed commit message in a `text` code block unless the user asks for reasoning or alternatives.

For a validation request, state whether the message is valid, identify the exact violated rule, and provide one corrected message when needed.
