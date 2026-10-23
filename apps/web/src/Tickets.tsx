import { useState } from "react";
import {
  Link,
  useParams,
  useSearchParams,
  useNavigate,
} from "react-router-dom";
import { Plus, Lock, Send } from "lucide-react";
import {
  useData,
  useAction,
  Page,
  Row,
  can,
  label,
  date,
  requestId,
} from "./api";
import { useUser } from "./App";
import {
  Heading,
  Panel,
  Loading,
  ErrorBox,
  Empty,
  Badge,
  Pagination,
  Field,
  Back,
  Modal,
} from "./ui";
export function IdSelect({
  kind,
  caption,
  value,
  onChange,
  empty = "None",
}: {
  kind: string;
  caption: string;
  value: string;
  onChange: (v: string) => void;
  empty?: string;
}) {
  const query = useData<Page>(
    kind === "users"
      ? "/users?page_size=100"
      : "/catalogs/" + kind + "?page_size=100",
  );
  return (
    <Field label={caption}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{empty}</option>
        {query.data?.items
          .filter(
            (r) =>
              r.is_active &&
              (kind !== "users" ||
                [
                  "director",
                  "support_staff",
                  "competitions_administrator",
                ].includes(r.role) ||
                r.permissions.includes("private_tickets")),
          )
          .map((r) => (
            <option key={r.id} value={r.id}>
              {r.name || r.full_name}
            </option>
          ))}
      </select>
    </Field>
  );
}
export function Tickets() {
  const user = useUser();
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/tickets?" + params);
  const action = useAction();
  const [selected, setSelected] = useState<string[]>([]);
  const [bulk, setBulk] = useState(false);
  const [assignee, setAssignee] = useState("");
  const [committee, setCommittee] = useState("");
  const [status, setStatus] = useState("");
  function filter(key: string, value: string) {
    params.delete("page");
    value ? params.set(key, value) : params.delete(key);
    setParams(params);
    setSelected([]);
  }
  return (
    <>
      <Heading
        eyebrow="CONVERSATIONS / SUPPORT"
        title="Support desk"
        description="One shared queue. Clear ownership. Thoughtful replies."
      >
        {user?.role !== "support_staff" && (
          <Link className="button primary" to="/tickets/new">
            <Plus size={16} /> New simulated ticket
          </Link>
        )}
      </Heading>
      <div className="tabs">
        {[
          ["", "All tickets"],
          ["mine", "My open tickets"],
          ["unassigned", "Unassigned"],
          ["waiting", "Waiting on organizer"],
        ].map(([v, t]) => (
          <button
            className={(params.get("view") || "") === v ? "active" : ""}
            key={v}
            onClick={() => filter("view", v)}
          >
            {t}
          </button>
        ))}
      </div>
      <section className="filter-panel">
        <div className="filter-row">
          <Field label="Search tickets">
            <input
              placeholder="Number, subject, requester…"
              value={params.get("q") || ""}
              onChange={(e) => filter("q", e.target.value)}
            />
          </Field>
          <Field label="Status">
            <select
              value={params.get("status") || ""}
              onChange={(e) => filter("status", e.target.value)}
            >
              <option value="">All statuses</option>
              {[
                "new",
                "assigned",
                "waiting_on_organizer",
                "waiting_on_requester",
                "resolved",
                "closed",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="Priority">
            <select
              value={params.get("priority") || ""}
              onChange={(e) => filter("priority", e.target.value)}
            >
              <option value="">All priorities</option>
              {["low", "normal", "high", "urgent"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <IdSelect
            kind="committees"
            caption="Committee"
            value={params.get("committee_id") || ""}
            onChange={(v) => filter("committee_id", v)}
            empty="All committees"
          />
        </div>
        <details>
          <summary>More filters</summary>
          <div className="filter-row">
            <IdSelect
              kind="categories"
              caption="Category"
              value={params.get("category_id") || ""}
              onChange={(v) => filter("category_id", v)}
              empty="All categories"
            />
            <IdSelect
              kind="users"
              caption="Assignee"
              value={params.get("assigned_user_id") || ""}
              onChange={(v) => filter("assigned_user_id", v)}
              empty="All organizers"
            />
          </div>
        </details>
      </section>
      <div className="toolbar">
        <span>{query.data?.total ?? "—"} tickets</span>
        <div className="actions">
          {selected.length > 0 && (
            <button onClick={() => setBulk(true)}>
              Update {selected.length} selected tickets
            </button>
          )}
          <select
            aria-label="Sort tickets"
            value={params.get("sort") || "newest"}
            onChange={(e) => filter("sort", e.target.value)}
          >
            {["newest", "oldest", "priority", "activity"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="Select ticket page"
                    checked={
                      !!query.data?.items.length &&
                      query.data.items.every((r) => selected.includes(r.id))
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? query.data!.items.map((r) => r.id)
                          : [],
                      )
                    }
                  />
                </th>
                <th>Ticket</th>
                <th>Requester</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={"Select " + r.public_number}
                      checked={selected.includes(r.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, r.id]
                            : selected.filter((x) => x !== r.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <Link to={"/tickets/" + r.id}>
                      <small className="ticket-number">{r.public_number}</small>
                      <strong>{r.subject}</strong>
                    </Link>
                  </td>
                  <td>
                    {r.requester_name}
                    <small>{r.requester_email}</small>
                  </td>
                  <td>
                    <Badge value={r.status} />
                  </td>
                  <td>
                    <Badge value={r.priority} />
                  </td>
                  <td>{date(r.last_message_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && (
            <Empty>No tickets match this view.</Empty>
          )}
          <Pagination
            data={query.data}
            onPage={(n) => {
              params.set("page", String(n));
              setParams(params);
            }}
          />
        </div>
      )}
      {bulk && (
        <Modal title="Update selected tickets" onClose={() => setBulk(false)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!confirm("Apply these changes to all selected tickets?"))
                return;
              try {
                await action.mutateAsync({
                  path: "/tickets/bulk",
                  body: {
                    ids: selected,
                    confirmed: true,
                    assignment:
                      assignee || committee
                        ? {
                            assigned_user_id: assignee || null,
                            committee_id: committee || null,
                          }
                        : null,
                    status: status ? { status } : null,
                  },
                });
                setBulk(false);
              } catch {}
            }}
          >
            {user?.role !== "support_staff" && (
              <>
                <IdSelect
                  kind="users"
                  caption="Assign organizer"
                  value={assignee}
                  onChange={setAssignee}
                />
                <IdSelect
                  kind="committees"
                  caption="Assign committee"
                  value={committee}
                  onChange={setCommittee}
                />
              </>
            )}
            <Field label="Change status">
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">Leave unchanged</option>
                {[
                  "assigned",
                  "waiting_on_organizer",
                  "waiting_on_requester",
                  "resolved",
                  "closed",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <ErrorBox error={action.error} />
            <button className="primary">Confirm bulk changes</button>
          </form>
        </Modal>
      )}
    </>
  );
}
export function TicketNew() {
  const action = useAction();
  const navigate = useNavigate();
  const [committee, setCommittee] = useState("");
  const [category, setCategory] = useState("");
  return (
    <>
      <Back to="/tickets">Support desk</Back>
      <Heading
        title="Simulate a competitor email"
        description="Create a support ticket using a fabricated requester and reserved test address."
      />
      <Panel title="Incoming message">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            try {
              const r = await action.mutateAsync({
                path: "/tickets",
                body: {
                  requester_name: fd.get("name"),
                  requester_email: fd.get("email"),
                  subject: fd.get("subject"),
                  body: fd.get("body"),
                  priority: fd.get("priority"),
                  committee_id: committee || null,
                  category_id: category || null,
                },
              });
              navigate("/tickets/" + r.id);
            } catch {}
          }}
        >
          <div className="form-grid">
            <Field label="Requester name">
              <input name="name" required placeholder="Fictional Competitor" />
            </Field>
            <Field label="Requester email">
              <input
                type="email"
                name="email"
                required
                placeholder="competitor@example.com"
              />
            </Field>
          </div>
          <Field label="Subject">
            <input name="subject" required />
          </Field>
          <Field label="Message body">
            <textarea name="body" rows={7} required />
          </Field>
          <div className="filter-row">
            <IdSelect
              kind="committees"
              caption="Committee"
              value={committee}
              onChange={setCommittee}
            />
            <IdSelect
              kind="categories"
              caption="Category"
              value={category}
              onChange={setCategory}
            />
            <Field label="Priority">
              <select name="priority" defaultValue="normal">
                {["low", "normal", "high", "urgent"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
          </div>
          <ErrorBox error={action.error} />
          <button className="primary" disabled={action.isPending}>
            Create simulated ticket
          </button>
        </form>
      </Panel>
    </>
  );
}
export function ReplyComposer({
  onSend,
  pending,
  error,
}: {
  onSend: (kind: "messages" | "notes", body: string) => Promise<void>;
  pending: boolean;
  error: unknown;
}) {
  const [mode, setMode] = useState<"messages" | "notes">("messages");
  const [reply, setReply] = useState("");
  const [note, setNote] = useState("");
  const [localError, setLocalError] = useState<unknown>();
  return (
    <section className={"composer " + (mode === "notes" ? "private" : "")}>
      <div className="tabs">
        <button
          type="button"
          className={mode === "messages" ? "active" : ""}
          onClick={() => setMode("messages")}
        >
          <Send size={16} /> Public reply
        </button>
        <button
          type="button"
          className={mode === "notes" ? "active" : ""}
          onClick={() => setMode("notes")}
        >
          <Lock size={16} /> Internal note
        </button>
      </div>
      <p>
        {mode === "messages"
          ? "Visible in the conversation and queued as a sandbox email to the requester."
          : "Private to authorized organizers. This will never create an email."}
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setLocalError(undefined);
          try {
            await onSend(mode, mode === "messages" ? reply : note);
            mode === "messages" ? setReply("") : setNote("");
          } catch (e) {
            setLocalError(e);
          }
        }}
      >
        <Field
          label={
            mode === "messages" ? "Public reply body" : "Private internal note"
          }
        >
          <textarea
            required
            rows={5}
            value={mode === "messages" ? reply : note}
            onChange={(e) =>
              mode === "messages"
                ? setReply(e.target.value)
                : setNote(e.target.value)
            }
          />
        </Field>
        <ErrorBox error={localError || error} />
        <button
          className={mode === "messages" ? "primary" : ""}
          disabled={pending}
        >
          {mode === "messages" ? <Send size={15} /> : <Lock size={15} />}{" "}
          {mode === "messages"
            ? "Send public sandbox reply"
            : "Save private internal note"}
        </button>
      </form>
    </section>
  );
}
export function TicketDetail() {
  const { id } = useParams();
  const query = useData<Row>("/tickets/" + id);
  const [messagePage, setMessagePage] = useState(1);
  const [notePage, setNotePage] = useState(1);
  const [activityPage, setActivityPage] = useState(1);
  const messages = useData<Page>(`/tickets/${id}/messages?page=${messagePage}`);
  const notes = useData<Page>(`/tickets/${id}/notes?page=${notePage}`);
  const activity = useData<Page>(
    `/tickets/${id}/activity?page=${activityPage}`,
  );
  const action = useAction();
  const user = useUser();
  const [assignee, setAssignee] = useState<string | undefined>();
  const [committee, setCommittee] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [newStatus, setNewStatus] = useState("");
  const [priority, setPriority] = useState<string | undefined>();
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorBox error={query.error} />;
  const t = query.data;
  return (
    <>
      <Back to="/tickets">Support desk</Back>
      <Heading
        eyebrow={t.public_number + " / SUPPORT TICKET"}
        title={t.subject}
        description={`${t.requester_name} · ${t.requester_email}`}
      >
        <Badge value={t.status} />
        <Badge value={t.priority} />
      </Heading>
      <div className="ticket-layout">
        <div>
          <Panel title="Public conversation">
            {messages.isPending ? (
              <Loading />
            ) : (
              messages.data?.items.map((m) => (
                <article
                  key={m.id}
                  className={"conversation " + m.message_type}
                >
                  <header>
                    <span className="avatar">{m.sender_name.slice(0, 2)}</span>
                    <div>
                      <strong>{m.sender_name}</strong>
                      <small>
                        {m.message_type === "staff_reply"
                          ? "Organizer · public reply"
                          : "Requester · simulated email"}
                      </small>
                    </div>
                    <time>{date(m.created_at)}</time>
                  </header>
                  <p className="message-body">{m.body}</p>
                  {m.outbound_message_id && (
                    <span className="caption">Sandbox message created</span>
                  )}
                </article>
              ))
            )}
            <ErrorBox error={messages.error} />
            <Pagination data={messages.data} onPage={setMessagePage} />
          </Panel>
          <ReplyComposer
            pending={action.isPending}
            error={action.error}
            onSend={async (kind, body) => {
              await action.mutateAsync({
                path: `/tickets/${id}/${kind}`,
                body: { body, request_id: requestId() },
              });
            }}
          />
          <Panel title="Private internal notes" action={<Lock size={17} />}>
            <div className="private-notes">
              {notes.data?.items.length ? (
                notes.data.items.map((n) => (
                  <article key={n.id}>
                    <small>{date(n.created_at)}</small>
                    <p className="message-body">{n.body}</p>
                  </article>
                ))
              ) : (
                <Empty>No internal notes yet.</Empty>
              )}
            </div>
            <ErrorBox error={notes.error} />
            <Pagination data={notes.data} onPage={setNotePage} />
          </Panel>
        </div>
        <aside>
          <Panel title="Ticket details">
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await action.mutateAsync({
                    path: "/tickets/" + id + "/assign",
                    body: {
                      assigned_user_id:
                        (assignee ?? t.assigned_user_id) || null,
                      committee_id: (committee ?? t.committee_id) || null,
                      category_id: (category ?? t.category_id) || null,
                    },
                  });
                } catch {}
              }}
            >
              <IdSelect
                kind="users"
                caption="Assigned organizer"
                value={assignee ?? t.assigned_user_id ?? ""}
                onChange={setAssignee}
              />
              <IdSelect
                kind="categories"
                caption="Competition category"
                value={category ?? t.category_id ?? ""}
                onChange={setCategory}
              />
              <IdSelect
                kind="committees"
                caption="Committee"
                value={committee ?? t.committee_id ?? ""}
                onChange={setCommittee}
              />
              {user?.role !== "support_staff" && (
                <button disabled={action.isPending}>Save assignment</button>
              )}
            </form>
            <hr />
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await action.mutateAsync({
                    path: "/tickets/" + id + "/status",
                    body: {
                      status: newStatus || t.status,
                      priority: priority || t.priority,
                    },
                  });
                  setNewStatus("");
                } catch {}
              }}
            >
              <Field label="Ticket status">
                <select
                  value={newStatus || t.status}
                  onChange={(e) => setNewStatus(e.target.value)}
                >
                  {[t.status, ...t.allowed_transitions].map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Ticket priority">
                <select
                  value={priority ?? t.priority}
                  onChange={(e) => setPriority(e.target.value)}
                >
                  {["low", "normal", "high", "urgent"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <button disabled={action.isPending}>Update status</button>
            </form>
            <ErrorBox error={action.error} />
          </Panel>
          <Panel title="Activity timeline">
            {activity.data?.items.map((a) => (
              <div className="timeline-entry" key={a.id}>
                <strong>{a.summary}</strong>
                <small>{date(a.created_at)}</small>
              </div>
            ))}
            <Pagination data={activity.data} onPage={setActivityPage} />
          </Panel>
          {can(user, "outbox") && (
            <Link className="button" to={"/outbox?ticket_id=" + id}>
              View ticket outbox
            </Link>
          )}
        </aside>
      </div>
    </>
  );
}
