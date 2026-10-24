# Test plan

## Layers

- **PostgreSQL unit/integration (pytest):** isolated ephemeral database, real
  migrations and constraints, real FastAPI requests, real mock worker.
- **Frontend (Vitest + React Testing Library):** wizard states, column mapping,
  field decisions, recipient-by-recipient previews, public/private composer
  isolation, role controls, loading/error announcements.
- **End-to-end (Playwright Chromium):** real nginx, API, worker and PostgreSQL in a
  separate Compose project. The browser maps and commits the duplicate CSV, saves
  an Arts list, previews/approves a campaign, observes one delivery per recipient,
  creates/assigns a ticket, adds a private note and public reply, resolves it, and
  verifies audit events. A second scenario creates a pilot, adds judges, updates
  responses, filters them, attaches a file, forwards a sandbox message, checks
  the directory and separate mock receipts. A third checks permanent competition
  protection, the three-step pilot delete flow, and the deletion log. Database assertions
  supplement visible UI assertions.
- **Build:** strict TypeScript compilation, Vite production bundle, fresh Docker
  startup, Alembic migration check, service health checks, desktop/tablet screenshots.

Exact commands live in the repository README and `scripts/test.sh`.

## Backend checks

- Trim/lowercase email without altering dots/plus aliases.
- Unicode case folding, punctuation and whitespace normalization.
- All five duplicate levels, reverse alternate-email overlap, no name-only merge.
- Mapping requires identity and rejects ambiguous mappings; malformed/empty CSV.
- Full import counts and error export, replay-safe commit, within-batch duplicates.
- Merge snapshots preserve alternate values; qualifications, categories, notes and
  history remain linked; campaign history is not orphaned.
- Dynamic saved lists change when matching contacts change.
- DNC exclusion, different-ID email deduplication, unknown template rejection.
- Approval permission enforced; one outbound row per recipient; repeated queue
  and delivery cannot duplicate receipts.
- Actual row locks verify `SKIP LOCKED`; retry limits, stale-owner protection,
  recovery, cancellation and late suppression are tested.
- Ticket internal notes create zero messages; public replies create one and are
  idempotent on request UUID; assignment and lifecycle updates are audited.
- Pilot nominations track response and contact timing independently per
  competition; seven-day follow-ups, phone-only contacts, document access and
  pilot recipient scoping are covered.
- Seeded competition folders and fixed competition entries are present; deletion
  is forbidden for fixed entries and audited for pilots.
- Directory rows expose per-competition response and written qualification;
  sheet export preserves added order and the category/competition hierarchy.
- Draft attachments validate type and size, remain available through the mock
  outbox, and follow sandbox-only forwards without external delivery.
- Support staff cannot read judges/imports/other tickets or reassign; competition
  access is scoped; technology cannot obtain private content via tickets/outbox/audit.
- Passwords are Argon2id hashes; unauthorized requests fail; mutation CSRF header
  required; CSV formula prefixes are escaped on export.

## Sample cases

See README's per-line duplicate outcome table. Tests use only the two supplied
fabricated CSVs and reserved test email addresses. Import counts assume the
development seed is intact.
The end-to-end runner resets only the dedicated `mist_e2e` database before each
run, without resetting the user's main database. This preserves the original
exact/possible duplicate scenarios on repeat runs.

## Manual exploratory checklist

- Keyboard-only login, navigation, selects, dialogs and composers; Escape closes
  dialogs; focus stays contained and returns after closing.
- Desktop and tablet: table scroll remains inside its container, text is legible,
  navigation can be opened on narrow screens, and forms remain usable.
- Empty filter results, missing records, access-denied routes and validation errors.
- Change CSV delimiter, leave optional columns unmapped, inspect UTF-8 error,
  test configured file/row limits, download errors and selected-contact exports.
- Review every side of a duplicate; choose incoming organization but preserve
  existing name; inspect merge and audit snapshots afterward.
- Toggle DNC after approval but before queueing/delivery; verify no message is sent.
- Stop worker, queue messages, enable failure simulation, restart worker, observe
  three failures, disable simulation, retry. Stop worker after claim and confirm
  stale recovery after five minutes.
- Log in as each seeded role; directly request unauthorized endpoints as well as
  checking hidden controls. Grant/revoke private ticket access as director.
- Preserve a draft public reply while switching to internal-note mode. Saving the
  note must not send the public draft or create an outbox record.
- Reopen resolved/closed tickets through the permitted lifecycle; invalid direct
  transitions must fail without partially updating a bulk request.

## Results

The current verification results are recorded in `docs/validation.md` after the
final run. A passing test suite confirms the exercised local workflows; it does
not certify production readiness or a future external email provider.
