# Archived ChatGPT legacy DOCX migration

This namespace contains the completed historical DOCX -> canonical JSON migration support for the ChatGPT provider.

It is deliberately inside the ChatGPT provider because the migration is not a core engine capability and must not constrain future providers such as Discord.

## Canonical promotion

`promote_turns.py` converts the validated `legacy-docx-turns.json` collection into one provider-neutral canonical `.json.xz` file per conversation. It does **not** read historical DOCX files.

Default input:

```text
%USERPROFILE%\Documents\ChatGPT Archive\legacy\reconstruction\legacy-docx-turns.json
```

Default output:

```text
%USERPROFILE%\Documents\ChatGPT Archive\downloads\gpt\legacy-docx\
```

Run from the repository root:

```powershell
py -m gpt_exporter.providers.gpt.archive.legacy_docx.promote_turns
```

The promotion preserves stable conversation IDs (`legacy-docx-<source-sha256>`), title/date/category hints, all normalized turns including `unknown`, and migration provenance. Every written file is read back and role/message counts are verified before success is reported.

The generic index path can rebuild these promoted conversations directly from canonical JSON/XZ, with no DOCX lookup or SHA verification against an external source file.

## Cutover verification

After promotion, verify the real archive with a completely temporary SQLite rebuild:

```powershell
py -m gpt_exporter.providers.gpt.archive.legacy_docx.verify_cutover
```

The verifier reads only the archive `downloads` JSON/XZ tree. It does not use the historical DOCX directory and does not modify the real SQLite database. PASS requires:

```text
Legacy conversations: 42
Legacy messages:      654
Roles:                user=304, assistant=311, unknown=39
Canonical GPT sources: 42
DOCX dependencies:      0
```

## Close-out criterion

The old DOCX parser/Word-IR/role-inference/reconstruction/audit pipeline becomes removable from active runtime once the real 42-conversation promotion and temporary rebuild both pass.

After that validation:

- historical DOCX files are no longer a runtime/rebuild dependency;
- `gpt_exporter/legacy/` and root-level legacy migration scripts can be archived here or removed from the active product;
- the provider-neutral core contains no `legacy_docx` concepts;
- normal ChatGPT operation uses provider JSON/canonical data only;
- deleting this archive namespace must not affect normal runtime behavior.
