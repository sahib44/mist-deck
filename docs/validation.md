# Validation record

Revalidated locally on 2026-10-27 with Docker Desktop (Linux ARM64 containers).

| Check | Result |
| --- | --- |
| PostgreSQL backend unit/integration tests | **53 passed** |
| Frontend Vitest / React Testing Library | **11 passed** |
| Playwright organizer journeys | **5 passed**, including recipient chips, judge reply alerts, notification navigation, member/chair permissions, and password-confirmed directory clearing |
| TypeScript strict compilation | Passed |
| Vite production build | Passed |
| Docker Compose build and startup | Passed |
| Alembic schema consistency | `No new upgrade operations detected.` |
| API, database, worker, frontend health | Healthy |
| npm dependency audit during clean install | 1 high-severity advisory reported; not remediated in this feature |
| Desktop / tablet visual review | Passed after correcting collapsed-navigation visibility |

The full browser run imported the fabricated duplicate CSV, resolved exact and
possible matches, committed 2 new / 6 updated / 2 skipped rows, selected directory
judges, reviewed recipient exclusions, previewed and approved individual messages, and
observed sandbox delivery. It then created a shared ticket, verified that a
private note produced no outbound message, sent a public sandbox reply, resolved
the ticket, signed out, signed in as director, and inspected the audit trail.

Screenshots in `docs/screenshots` show an earlier isolated E2E workspace. The
tests use fabricated contacts and a separate database; they do not reset the
main workspace. No real email or external email provider was used by tests.

The pilot browser scenario created a fabricated competition and three contacts,
marked them accepted, filtered and selected them, attached a text file, then
verified three separate mock outbox records and a sandbox forward. It checked
the competition-based directory. Backend tests cover attachment validation and
download, the forwarded attachment reference, written qualification and ordered
sheet export, private document access, follow-up filters, and automatic status
movement after a completed sandbox message.

The competition test verified the six category folders, fixed Arts competitions,
the seeded Culinary Arts pilot, the permanent-entry delete guard, three-step
pilot deletion, and a visible deletion-history row with the deleting actor.

Test startup resets only the explicitly named `mist_e2e` database. Backend tests
use `mist_test`; neither test path resets the main application database.

One non-failing dependency deprecation warning remains in the backend test client
(Starlette's AnyIO BlockingPortal alias). It does not affect application runtime
or any assertions. The npm audit result applies to the JavaScript dependency
lockfile; no claim of a full production/container security certification is made.

Known MVP boundaries and implementation choices are documented in README and
architecture.md. Production deployment and real email remain out of scope.


The shared-team browser journey used the member account to add competition judges,
remove/re-add recipient chips, add a one-off recipient without creating a judge,
search campaigns by recipient email, receive a simulated judge reply, follow unread
markers from category to competition to judge, and clear those markers by opening
the conversation. A nonjudge sender became a ticket. The chair then downloaded a
sheet backup, failed an incorrect password check, and successfully cleared all
judges with the correct password while retaining mail history.

The main local workspace was separately backed up and reset at the user's explicit
request after these tests. Accounts and competition definitions were retained;
judges, imports, campaigns, outbound/inbound messages, tickets and notifications
were cleared. Private snapshots and test credentials are Git-ignored.


The simplified ticket journey verifies the four-field incoming-email form, absence
of assignment/committee/category/priority controls, shared team visibility, and
forwarding of only public content. Browser checks compare note-panel and textarea
backgrounds to the normal conversation surface and verify yellow inner/outer
borders in both light and dark themes.


The status-review browser journey marks a new ticket In progress, verifies its
notification clears, checks its presence in Needs a reply, saves notes newest
first, chooses Waiting on requester, verifies the required public reply and blocked
status action, preserves that draft through outbox/Back navigation, requests chair
approval, follows the chair's notification to approve, returns via the head's
approval notification, and makes the final send. It then records the required
Awaiting organizer note and resolves with a private resolution note and no email.
Backend clock-controlled checks cover seven-day auto-closure and incoming replies
reopening tickets without closing untouched work.
