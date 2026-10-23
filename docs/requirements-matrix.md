# Implementation map

| Specification area | Implementation | Main verification |
| --- | --- | --- |
| Foundation / authentication / RBAC | `mist/auth.py`, `main.py`, Compose, initial Alembic revision | Foundation and authorization pytest cases |
| Judge directory and history | `services.py`, judge endpoints, `Judges.tsx` | Filters, dynamic lists, bulk updates, merge history tests |
| CSV wizard | `imports.py`, `Imports.tsx` | Mapping, malformed input, counts, error export; full browser flow |
| Explainable duplicate review | `duplicate_match`, `merge_data`, `MergeFields` | All five levels, alternate emails, within-batch matches, preserved data |
| Saved dynamic lists | `SavedList`, saved-list endpoints, `SavedLists` | Mutation changes later campaign recipients |
| Campaign composition / preview | `campaigns.py`, `Campaigns.tsx` | DNC, template variables, email deduplication, per-recipient browser previews |
| Approval and cancellation | campaign transitions and backend grants | Unauthorized approval rejected; cancellation blocks claimed/queued jobs |
| PostgreSQL queue / mock provider | `worker.py` | Real SKIP LOCKED, stale recovery, bounded retries, receipt idempotency |
| Sandbox outbox | outbox APIs / `Outbox` | One message per campaign recipient and public ticket reply |
| Ticket desk | `tickets.py`, `Tickets.tsx` | Assignment, role scope, separate notes/replies, lifecycle, browser flow |
| Dashboard / audit | `dashboard.py`, audit APIs, `Overview.tsx` | Database metrics, permission scoping, audit events in integration/E2E |
| Operational controls | Docker health checks, Settings → System, retry simulation | Full stack startup and health checks |
| Samples / docs / tests | sample CSVs, README, docs, pytest/Vitest/Playwright | Repeatable documented commands |

Explicit design choices and bounded limitations are recorded in architecture.md
and README rather than hidden behind placeholder screens.
