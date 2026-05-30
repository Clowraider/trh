---
name: template-safe-edit
description: "Trigger: templates, Jinja, HTML edits, panel UI changes. Edit template files with Python patching and mandatory before/after verification."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Use this skill when modifying `templates/*.html` or other Jinja templates.

## Hard Rules

- Do not trust a single edit call as proof.
- Apply template edits with a Python script (`pathlib`) that performs exact replacements.
- Always verify **before** and **after** state.
- Always compile the edited template with Jinja after changes.

## Execution Steps

1. Capture evidence before edit:
   - `nl -ba <file> | sed -n '<start>,<end>p'`
   - `rg -n '<critical pattern>' <file>`
2. Apply replacement using Python:
   - read file
   - `str.replace(...)`
   - assert change occurred (`UPDATED` vs `NO_CHANGE`)
   - write file
3. Capture evidence after edit:
   - same `nl` and `rg` checks
   - confirm broken pattern removed / expected pattern present
4. Compile template:
   - `python3 - <<'PY' ... env.get_template('...') ... PY`
   - require `JINJA_COMPILE_OK`
5. Report: include before/after proof lines and compile result.

## Output Contract

Return:
- file path edited
- before evidence
- after evidence
- Jinja compile status
- any remaining risk
