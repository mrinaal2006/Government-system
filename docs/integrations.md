# Source integrations

No live integration with any government system exists. Each source channel is
`not_configured` until an integration is built and authorised.

## Available now

* **File import** (all channels): authorised CSV (UTF-8) or XLSX exports. Required columns
  `external_id`, `description`; optional `subject, received_at, category_code, priority,
  block_lgd_code, block_name, village_lgd_code, village_name, location_text, complainant_name,
  complainant_mobile, complainant_address`. Each file is stored, hashed (the same file cannot be
  imported twice per source) and processed row by row: rows with an `external_id` already
  imported are counted as duplicates, unknown codes are reported and left blank (never guessed).
* **Development adapter**: synthetic labelled records, disabled outside development.

## Adding a live integration

Implement `SourceAdapter` (`backend/app/modules/intake/adapters.py`): a `name` and a
`records()` iterator yielding `ExternalRecord`s. Process them with `process_batch`, which
already provides provenance, duplicate prevention and audit. Before enabling, document here:

1. The legal/administrative authority for data sharing (order or MoU reference).
2. Authentication method and where credentials are stored (secret manager, never in code).
3. Data fields received, especially personal data, and the retention applied.
4. Rate limits, polling schedule, error handling and the contact for the source system.
5. Test evidence against the source's sandbox, if one exists.

Then set the channel's integration mode to `live_api` under Configuration → Grievance sources.
