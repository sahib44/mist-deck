# Validation record

Revalidated locally on 2026-10-23 with Docker Desktop (Linux ARM64 containers).

| Check | Result |
| --- | --- |
| PostgreSQL backend unit/integration tests | **25 passed** |
| Frontend Vitest / React Testing Library | **7 passed** |
| Full Playwright organizer journey | **1 passed**, including tablet navigation |
| TypeScript strict compilation | Passed |
| Vite production build | Passed |
| Docker Compose build and startup | Passed |
| Alembic schema consistency | `No new upgrade operations detected.` |
| API, database, worker, frontend health | Healthy |
| npm dependency audit during clean install | 0 reported vulnerabilities |
| Desktop / tablet visual review | Passed after correcting collapsed-navigation visibility |

The full browser run imported the fabricated duplicate CSV, resolved exact and
possible matches, committed 2 new / 6 updated / 2 skipped rows, filtered Arts
judges, saved a dynamic list, previewed and approved individual messages, and
observed sandbox delivery. It then created and assigned a ticket, verified that a
private note produced no outbound message, sent a public sandbox reply, resolved
the ticket, signed out, signed in as director, and inspected the audit trail.

Screenshots in `docs/screenshots` show the isolated E2E workspace after that
scenario. The main workspace remains a clean seed of 24 fabricated judge records.
No real email, real personal data, or external email provider was used.

Test startup resets only the explicitly named `mist_e2e` database. Backend tests
use `mist_test`; neither test path resets the main application database.

One non-failing dependency deprecation warning remains in the backend test client
(Starlette's AnyIO BlockingPortal alias). It does not affect application runtime
or any assertions. The npm audit result applies to the JavaScript dependency
lockfile; no claim of a full production/container security certification is made.

Known MVP boundaries and implementation choices are documented in README and
architecture.md. Production deployment and real email remain out of scope.
