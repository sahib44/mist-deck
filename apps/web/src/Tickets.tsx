import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams, useNavigate } from "react-router-dom";
import { Plus, Lock, Send, Forward, ShieldCheck } from "lucide-react";
import { useData, useAction, Page, Row, can, label, date, requestId } from "./api";
import { useUser } from "./App";
import { Heading, Panel, Loading, ErrorBox, Empty, Badge, Pagination, Field, Back, Modal } from "./ui";

const ticketStatuses = ["new", "in_progress", "waiting_on_organizer", "waiting_on_requester", "resolved", "closed"];

export function Tickets() {
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/tickets?" + params);
  const action = useAction();
  const [selected, setSelected] = useState<string[]>([]);
  const [bulk, setBulk] = useState(false);
  const [status, setStatus] = useState("");
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params); next.delete("page");
    value ? next.set(key, value) : next.delete(key); setParams(next); setSelected([]);
  }
  return <>
    <Heading title="Competitions tickets"><Link className="button primary" to="/tickets/new"><Plus size={16} /> New simulated ticket</Link></Heading>
    <div className="tabs">{[["", "All tickets"], ["open", "Open"], ["waiting", "Needs a reply"]].map(([value, title]) => <button key={value} className={(params.get("view") || "") === value ? "active" : ""} onClick={() => filter("view", value)}>{title}</button>)}</div>
    <section className="filter-panel"><div className="filter-row">
      <Field label="Search tickets"><input placeholder="Number, subject, name or email" value={params.get("q") || ""} onChange={event => filter("q", event.target.value)} /></Field>
      <Field label="Status"><select value={params.get("status") || ""} onChange={event => filter("status", event.target.value)}><option value="">All statuses</option>{ticketStatuses.map(value => <option key={value} value={value}>{label(value)}</option>)}</select></Field>
    </div></section>
    <div className="toolbar"><span>{query.data?.total ?? "—"} tickets</span><div className="actions">
      {!!selected.length && <button onClick={() => setBulk(true)}>Update {selected.length} selected tickets</button>}
      <select aria-label="Sort tickets" value={params.get("sort") || "newest"} onChange={event => filter("sort", event.target.value)}>{["newest", "oldest", "activity"].map(value => <option key={value} value={value}>{label(value)}</option>)}</select>
    </div></div>
    <ErrorBox error={query.error} />
    {query.isPending ? <Loading /> : <div className="table-wrap"><table><thead><tr>
      <th><input type="checkbox" aria-label="Select ticket page" checked={!!query.data?.items.length && query.data.items.every(row => selected.includes(row.id))} onChange={event => setSelected(event.target.checked ? query.data!.items.map(row => row.id) : [])} /></th><th>Ticket</th><th>Sender</th><th>Status</th><th>Last activity</th>
    </tr></thead><tbody>{query.data?.items.map(row => <tr key={row.id}>
      <td><input type="checkbox" aria-label={`Select ${row.public_number}`} checked={selected.includes(row.id)} onChange={event => setSelected(event.target.checked ? [...selected, row.id] : selected.filter(id => id !== row.id))} /></td>
      <td><Link to={`/tickets/${row.id}`}><small className="ticket-number">{row.public_number}</small><strong>{row.subject}</strong></Link></td><td>{row.requester_name}<small>{row.requester_email}</small></td><td><Badge value={row.status} /></td><td>{date(row.last_message_at)}</td>
    </tr>)}</tbody></table>{query.data?.total === 0 && <Empty>No tickets match this view.</Empty>}<Pagination data={query.data} onPage={page => filter("page", String(page))} /></div>}
    {bulk && <Modal title="Update selected tickets" onClose={() => setBulk(false)}><form onSubmit={async event => { event.preventDefault(); if (!confirm("Apply this status to all selected tickets?")) return; try { await action.mutateAsync({ path: "/tickets/bulk", body: { ids: selected, confirmed: true, status: { status } } }); setBulk(false); setSelected([]); } catch {} }}>
      <Field label="Change status"><select required value={status} onChange={event => setStatus(event.target.value)}><option value="">Choose a status</option>{["in_progress", "closed"].map(value => <option key={value} value={value}>{label(value)}</option>)}</select></Field><ErrorBox error={action.error} /><button className="primary" disabled={action.isPending}>Confirm bulk changes</button>
    </form></Modal>}
  </>;
}

export function TicketNew() {
  const action = useAction();
  const navigate = useNavigate();
  return <>
    <Back to="/tickets">Competitions tickets</Back><Heading title="Simulate a ticket email" />
    <Panel title="Incoming message"><form onSubmit={async event => {
      event.preventDefault(); const fd = new FormData(event.currentTarget);
      try { const result = await action.mutateAsync({ path: "/tickets", body: { requester_name: fd.get("name"), requester_email: fd.get("email"), subject: fd.get("subject"), body: fd.get("body") } }); navigate(`/tickets/${result.id}`); } catch {}
    }}>
      <div className="form-grid"><Field label="Requester name"><input name="name" required /></Field><Field label="Requester email"><input type="email" name="email" required /></Field></div>
      <Field label="Subject"><input name="subject" required /></Field><Field label="Message body"><textarea name="body" rows={7} required /></Field>
      <ErrorBox error={action.error} /><button className="primary" disabled={action.isPending}>Create simulated ticket</button>
    </form></Panel>
  </>;
}

export type TicketComposerState = {
  mode: "messages" | "notes";
  reply: string;
  note: string;
  resolution_note: string;
  target_status: string;
};
const emptyComposer: TicketComposerState = { mode: "messages", reply: "", note: "", resolution_note: "", target_status: "" };

export function ReplyComposer({
  draft, onChange, changingStatus, pending, error, onSend, onRequestApproval,
  needsApproval = false, approved = false, approvalPending = false, valid = true,
  focusToken = 0, sectionRef,
}: {
  draft: TicketComposerState;
  onChange: (draft: TicketComposerState) => void;
  changingStatus: boolean;
  pending: boolean;
  error: unknown;
  onSend: () => Promise<void>;
  onRequestApproval?: () => Promise<void>;
  needsApproval?: boolean;
  approved?: boolean;
  approvalPending?: boolean;
  valid?: boolean;
  focusToken?: number;
  sectionRef?: React.RefObject<HTMLElement | null>;
}) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const resolution = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!focusToken) return;
    sectionRef?.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    const target = changingStatus && draft.target_status === "resolved" ? resolution.current : textarea.current;
    target?.focus({ preventScroll: true });
  }, [focusToken]);
  const publicRequired = changingStatus && draft.target_status === "waiting_on_requester";
  const noteRequired = draft.mode === "notes" && (!changingStatus || draft.target_status === "waiting_on_organizer");
  const resolving = changingStatus && draft.target_status === "resolved";
  const buttonLabel = changingStatus
    ? draft.mode === "messages" && draft.reply.trim() ? "Update status and send reply" : draft.mode === "notes" && draft.note.trim() ? "Update status and save note" : "Update status"
    : draft.mode === "messages" ? "Send public sandbox reply" : "Save private internal note";
  const reviewable = !!(draft.mode === "messages" ? draft.reply.trim() || (resolving && draft.resolution_note.trim()) : draft.note.trim());
  return <section ref={sectionRef} className={`composer ${draft.mode === "notes" ? "private" : publicRequired ? "reply-required" : ""}`}>
    <div className="composer-topline">
      <div className="tabs">
        <button type="button" className={draft.mode === "messages" ? "active" : ""} disabled={pending} onClick={() => onChange({ ...draft, mode: "messages" })}><Send size={16} /> Public reply</button>
        <button type="button" className={draft.mode === "notes" ? "active" : ""} disabled={pending} onClick={() => onChange({ ...draft, mode: "notes" })}><Lock size={16} /> Internal note</button>
      </div>
      {onRequestApproval && <button type="button" className="chair-approval-button" onClick={() => void onRequestApproval()} disabled={pending || !reviewable || approvalPending || approved}><ShieldCheck size={16} />{approved ? "Draft approved" : approvalPending ? "Awaiting chair approval" : "Request chair approval"}</button>}
    </div>
    <p>{draft.mode === "notes" ? "Private to the team. This note does not create an email." : resolving ? "A reply to the requester is optional when resolving a ticket." : "The requester receives this public reply through the sandbox queue."}</p>
    {needsApproval && !approved && <p className="approval-hint">Request chair approval before sending. Changes to the draft or ticket require a fresh approval.</p>}
    {approved && <p className="approval-ready" role="status">The chair approved this exact draft. You can make the final send or save.</p>}
    <form onSubmit={event => { event.preventDefault(); void onSend(); }}>
      {resolving && <Field label="Resolution note *"><textarea aria-label="Resolution note" disabled={pending} ref={resolution} required rows={3} className="resolution-note-input" value={draft.resolution_note} onChange={event => onChange({ ...draft, resolution_note: event.target.value })} /></Field>}
      <Field label={`${draft.mode === "messages" ? "Public reply body" : "Private internal note"}${draft.mode === "messages" ? publicRequired ? " *" : resolving ? " (optional)" : "" : noteRequired ? " *" : " (optional)"}`}>
        <textarea ref={textarea} disabled={pending} aria-label={draft.mode === "messages" ? "Public reply body" : "Private internal note"} required={draft.mode === "messages" ? publicRequired || !changingStatus : noteRequired} rows={5} value={draft.mode === "messages" ? draft.reply : draft.note} onChange={event => onChange({ ...draft, [draft.mode === "messages" ? "reply" : "note"]: event.target.value })} />
      </Field>
      <ErrorBox error={error} />
      <button className={draft.mode === "messages" ? "primary" : ""} disabled={pending || !valid || (needsApproval && !approved)}>{draft.mode === "messages" ? <Send size={15} /> : <Lock size={15} />} {buttonLabel}</button>
    </form>
  </section>;
}

export function TicketDetail() {
  const { id = "" } = useParams();
  return <TicketWorkspace key={id} id={id} />;
}

function TicketWorkspace({ id }: { id: string }) {
  const user = useUser();
  const [searchParams] = useSearchParams();
  const query = useData<Row>(`/tickets/${id}`);
  const [messagePage, setMessagePage] = useState(1);
  const [notePage, setNotePage] = useState(1);
  const [activityPage, setActivityPage] = useState(1);
  const messages = useData<Page>(`/tickets/${id}/messages?page=${messagePage}`);
  const notes = useData<Page>(`/tickets/${id}/notes?page=${notePage}`);
  const activity = useData<Page>(`/tickets/${id}/activity?page=${activityPage}`);
  const reviews = useData<Page>(`/tickets/${id}/drafts`);
  const action = useAction();
  const storageKey = `mist-ticket-draft:${user?.id}:${id}`;
  const [draft, setDraft] = useState<TicketComposerState>(() => {
    try { return { ...emptyComposer, ...JSON.parse(sessionStorage.getItem(storageKey) || "{}") }; } catch { return { ...emptyComposer }; }
  });
  useEffect(() => { sessionStorage.setItem(storageKey, JSON.stringify(draft)); }, [draft, storageKey]);
  const [focusToken, setFocusToken] = useState(0);
  const composer = useRef<HTMLElement>(null);
  const approvalPanel = useRef<HTMLElement>(null);
  const [forwarding, setForwarding] = useState<Row | null>(null);
  const [notice, setNotice] = useState("");
  const [localError, setLocalError] = useState<unknown>();
  const sendRequest = useRef<{ signature: string; id: string } | null>(null);
  const reviewRequest = useRef<{ signature: string; id: string } | null>(null);
  const isChair = can(user, "ticket_approve");
  useEffect(() => { if (searchParams.get("draft") && reviews.data) approvalPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [searchParams.get("draft"), !!reviews.data]);
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorBox error={query.error} />;
  const ticket = query.data;
  const changingStatus = !!draft.target_status && draft.target_status !== ticket.status;
  const targetStatus = changingStatus ? draft.target_status : draft.mode === "messages" ? "waiting_on_requester" : "";
  const body = (draft.mode === "messages" ? draft.reply : draft.note).trim();
  const resolutionNote = changingStatus && draft.target_status === "resolved" ? draft.resolution_note.trim() : "";
  const matching = (review: Row) => review.created_by === user?.id && review.kind === draft.mode && review.body === body && review.target_status === targetStatus && review.resolution_note === resolutionNote && review.base_version === ticket.version;
  const approved = reviews.data?.items.find(review => review.status === "approved" && matching(review));
  const approvalPending = reviews.data?.items.some(review => review.status === "pending_approval" && matching(review)) || false;
  const includesReply = draft.mode === "messages" && !!draft.reply.trim();
  const needsApproval = includesReply && !isChair;
  const statusValid = !changingStatus ? false : draft.target_status === "waiting_on_requester" ? !!draft.reply.trim() && draft.mode === "messages" : draft.target_status === "waiting_on_organizer" ? !!draft.note.trim() && draft.mode === "notes" : draft.target_status === "resolved" ? !!resolutionNote : true;
  const normalValid = draft.mode === "notes" ? !!draft.note.trim() : !!draft.reply.trim() && ticket.status !== "closed";
  const valid = changingStatus ? statusValid : normalValid;
  function requestKey(ref: React.MutableRefObject<{ signature: string; id: string } | null>, payload: unknown) {
    const signature = JSON.stringify(payload);
    if (ref.current?.signature !== signature) ref.current = { signature, id: requestId() };
    return ref.current!.id;
  }
  function changeStatus(status: string) {
    setDraft(current => ({ ...current, target_status: status, mode: status === "waiting_on_organizer" ? "notes" : ["waiting_on_requester", "resolved"].includes(status) ? "messages" : current.mode }));
    setLocalError(undefined);
    if (["waiting_on_organizer", "waiting_on_requester", "resolved"].includes(status) && status !== ticket.status) setFocusToken(value => value + 1);
  }
  async function requestApproval() {
    const payload = { kind: draft.mode, body, target_status: targetStatus, resolution_note: resolutionNote, expected_version: ticket.version };
    try {
      const review = await action.mutateAsync({ path: `/tickets/${id}/drafts`, body: { ...payload, request_id: requestKey(reviewRequest, payload) } });
      setDraft(current => ({ ...current, [draft.mode === "messages" ? "reply" : "note"]: review.body, resolution_note: resolutionNote ? review.resolution_note : current.resolution_note }));
      reviewRequest.current = null;
      setNotice("Draft sent to the chair for approval. Approval will not send the email automatically.");
      setLocalError(undefined);
    } catch (error) { setLocalError(error); }
  }
  async function submit(statusOnly = false) {
    const progressOnly = statusOnly && changingStatus && draft.target_status === "in_progress";
    if (!valid && !progressOnly) { setLocalError("Complete the required reply or note before updating this ticket."); return; }
    if (needsApproval && !approved && !progressOnly) { setLocalError("Request chair approval before sending this reply."); return; }
    try {
      if (changingStatus) {
        const payload = { status: draft.target_status, reply_body: !progressOnly && includesReply ? draft.reply.trim() : "", internal_note: !progressOnly && draft.mode === "notes" ? draft.note.trim() : "", resolution_note: progressOnly ? "" : resolutionNote, approval_id: progressOnly ? null : approved?.id || null, expected_version: ticket.version };
        await action.mutateAsync({ path: `/tickets/${id}/status`, body: { ...payload, request_id: requestKey(sendRequest, payload) } });
      } else {
        const payload = { body, approval_id: approved?.id || null };
        await action.mutateAsync({ path: `/tickets/${id}/${draft.mode}`, body: { ...payload, request_id: requestKey(sendRequest, payload) } });
      }
      sendRequest.current = null;
      setDraft(current => ({ ...current, reply: !progressOnly && current.mode === "messages" ? "" : current.reply, note: !progressOnly && current.mode === "notes" ? "" : current.note, resolution_note: "", target_status: "" }));
      setNotePage(1); setMessagePage(1); setActivityPage(1); setLocalError(undefined);
      setNotice(progressOnly ? "Ticket marked In progress. Your draft is still here." : changingStatus ? "Ticket status and its reply or note were saved together." : draft.mode === "notes" ? "Private note saved." : "Approved reply queued in the sandbox outbox.");
    } catch (error) { setLocalError(error); }
  }
  function loadApproved(review: Row) {
    setDraft({ mode: review.kind, reply: review.kind === "messages" ? review.body : draft.reply, note: review.kind === "notes" ? review.body : draft.note, resolution_note: review.resolution_note, target_status: review.target_status && review.target_status !== ticket.status ? review.target_status : "" });
    setFocusToken(value => value + 1);
  }
  return <>
    <Back to="/tickets">Competitions tickets</Back>
    <Heading eyebrow={ticket.public_number} title={ticket.subject} description={`${ticket.requester_name} · ${ticket.requester_email}`}><Badge value={ticket.status} /></Heading>
    {notice && <div className="notice" role="status">{notice}</div>}
    {!!reviews.data?.items.length && <section ref={approvalPanel} className="panel ticket-approvals"><header><h2>Chair approval</h2></header>{reviews.data.items.map(review => <article id={`draft-${review.id}`} key={review.id} className={`ticket-review ${searchParams.get("draft") === review.id ? "highlighted-review" : ""}`}>
      <div className="message-heading"><strong>{review.author_name} · {review.kind === "notes" ? "Internal-note draft" : "Public-reply draft"}</strong><Badge value={review.status} /><small>{date(review.created_at)}</small></div>
      {review.target_status && <small>Proposed status: {label(review.target_status)}</small>}
      {review.body && <p className="message-body">{review.body}</p>}
      {review.resolution_note && <div className="review-resolution"><strong>Private resolution note</strong><p className="message-body">{review.resolution_note}</p></div>}
      {review.status === "pending_approval" && isChair && <button className="primary" disabled={action.isPending || review.base_version !== ticket.version} onClick={async () => { try { await action.mutateAsync({ path: `/tickets/${id}/drafts/${review.id}/approve` }); setNotice("Draft approved. The head has been notified and can make the final send or save."); } catch {} }}>Approve draft</button>}
      {review.status === "approved" && review.created_by === user?.id && review.base_version === ticket.version && <button onClick={() => loadApproved(review)}>Load approved draft</button>}
      {review.status === "superseded" && <small>This draft or its ticket changed; a fresh approval is needed.</small>}
    </article>)}<ErrorBox error={reviews.error || action.error} /></section>}
    <div className="ticket-layout"><div>
      <Panel title="Public conversation">
        {messages.isPending ? <Loading /> : messages.data?.items.map(message => <article key={message.id} className={`conversation ${message.message_type}`}>
          <header><span className="avatar">{message.sender_name.slice(0, 2)}</span><div><strong>{message.sender_name}</strong><small>{message.message_type === "staff_reply" ? "Team · public reply" : "Incoming email"}</small></div><time>{date(message.created_at)}</time></header>
          <p className="message-body">{message.body}</p>
          <div className="ticket-message-actions">{message.outbound_message_id && <span className="caption">Sandbox message created</span>}<button className="ticket-forward" onClick={() => { setForwarding(message); setNotice(""); }}><Forward size={14} /> Forward email</button></div>
        </article>)}
        <ErrorBox error={messages.error} /><Pagination data={messages.data} onPage={setMessagePage} />
      </Panel>
      <ReplyComposer draft={draft} onChange={setDraft} changingStatus={changingStatus} pending={action.isPending} error={localError || action.error} onSend={() => submit()} onRequestApproval={isChair ? undefined : requestApproval} needsApproval={needsApproval} approved={!!approved} approvalPending={approvalPending} valid={valid} focusToken={focusToken} sectionRef={composer} />
      <Panel title="Private internal notes" className="private-notes-panel" action={<Lock size={17} />}>
        <div className="private-notes">{notes.data?.items.length ? notes.data.items.map(note => <article key={note.id}><small>{date(note.created_at)}{note.kind === "resolution" ? " · Resolution" : ""}</small><p className="message-body">{note.body}</p></article>) : <Empty>No internal notes yet.</Empty>}</div>
        <ErrorBox error={notes.error} /><Pagination data={notes.data} onPage={setNotePage} />
      </Panel>
    </div><aside>
      <Panel title="Ticket details"><Field label="Ticket status"><select disabled={action.isPending} value={draft.target_status || ticket.status} onChange={event => changeStatus(event.target.value)}>{[ticket.status, ...ticket.allowed_transitions].map(value => <option key={value} value={value}>{label(value)}</option>)}</select></Field>
        <p className="caption">{draft.target_status === "waiting_on_requester" ? "A public reply and chair approval are required." : draft.target_status === "waiting_on_organizer" ? "The team owes the next step. Add a private internal note explaining it." : draft.target_status === "resolved" ? "A private resolution note is required. A requester reply is optional." : "In progress starts work without requiring a reply or note."}</p>
        <button type="button" onClick={() => void submit(true)} disabled={action.isPending || !changingStatus || (draft.target_status !== "in_progress" && (!statusValid || (needsApproval && !approved)))}>Update status</button>
        {ticket.auto_close_at && <p className="caption">Auto-closes after no requester reply by {date(ticket.auto_close_at)}.</p>}
        <ErrorBox error={localError || action.error} />
      </Panel>
      <Panel title="Activity timeline">{activity.data?.items.map(item => <div className="timeline-entry" key={item.id}><strong>{item.summary}</strong><small>{date(item.created_at)}</small></div>)}<Pagination data={activity.data} onPage={setActivityPage} /></Panel>
      {can(user, "outbox") && <Link className="button" to={`/outbox?ticket_id=${id}`}>View ticket outbox</Link>}
    </aside></div>
    {forwarding && <Modal title="Forward email" onClose={() => setForwarding(null)}><form onSubmit={async event => { event.preventDefault(); const fd = new FormData(event.currentTarget); try { await action.mutateAsync({ path: `/tickets/${id}/messages/${forwarding.id}/forward`, body: { recipient_email: fd.get("recipient_email"), note: fd.get("note") } }); setForwarding(null); setNotice("Forward queued in the sandbox outbox."); } catch {} }}>
      <Field label="Forward to"><input name="recipient_email" type="email" required /></Field><Field label="Note (optional)"><textarea name="note" rows={4} /></Field><ErrorBox error={action.error} /><button className="primary" disabled={action.isPending}>Queue sandbox forward</button>
    </form></Modal>}
  </>;
}
