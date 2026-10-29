import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bell, Mail, Plus } from "lucide-react";
import { useData, useAction, Page, Row, date, requestId } from "./api";
import { Back, Badge, Empty, ErrorBox, Field, Heading, Loading, Modal, Pagination, Panel } from "./ui";

export function UnreadMarker({ count = 0 }: { count?: number }) {
  return count > 0 ? <span className="unread-marker" title={`${count} unread ${count === 1 ? "reply" : "replies"}`} aria-label={`${count} unread ${count === 1 ? "reply" : "replies"}`}>!</span> : null;
}
export function Notifications() {
  const query = useData<{ unread_count: number; items: Row[] }>("/notifications");
  const action = useAction();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  return <>
    <button className="notification-button" onClick={() => setOpen(true)} aria-label={`Notifications (${query.data?.unread_count || 0} unread)`}><Bell size={18} /> Notifications{(query.data?.unread_count || 0) > 0 && <span className="notification-count">{query.data?.unread_count}</span>}</button>
    {open && <Modal title="Notifications" onClose={() => setOpen(false)}><ErrorBox error={query.error || action.error} />
      {query.isPending ? <Loading /> : !query.data?.items.length ? <Empty>No notifications yet.</Empty> : <div className="notification-list">{query.data.items.map(item => <button className={!item.read_at ? "notification-item unread" : "notification-item"} key={item.id} onClick={async () => {
        try { await action.mutateAsync({ path: `/notifications/${item.id}/read` }); setOpen(false); navigate(item.href); } catch {}
      }}><strong>{item.title}</strong><span>{item.body}</span><small>{date(item.created_at)}{!item.read_at ? " · Unread" : ""}</small></button>)}</div>}
    </Modal>}
  </>;
}

export function Conversations({ search = "", judgeId = "" }: { search?: string; judgeId?: string }) {
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [search, judgeId]);
  const query = useData<Page>(`/conversations?q=${encodeURIComponent(search)}${judgeId ? `&judge_id=${judgeId}` : ""}&page=${page}`);
  return <Panel title="Judge conversations" action={judgeId ? <Link to="/campaigns">Show all conversations</Link> : undefined}>
    <ErrorBox error={query.error} />
    {query.isPending ? <Loading /> : !query.data?.items.length ? <Empty>No conversations match this view.</Empty> : <div className="conversation-list">{query.data.items.map(item => <Link className={item.unread_count ? "conversation-row unread" : "conversation-row"} to={`/campaigns/conversations/judges/${item.id}`} key={item.id}><Mail size={18} /><span><strong>{item.name} <UnreadMarker count={item.unread_count} /></strong><small>{item.email}</small></span><span>{item.unread_count ? `${item.unread_count} new ${item.unread_count === 1 ? "message" : "messages"}` : "Open conversation"}<small>{date(item.last_message_at)}</small></span></Link>)}</div>}
    <Pagination data={query.data} onPage={setPage} />
  </Panel>;
}

export function JudgeConversation() {
  const { id = "" } = useParams();
  const [page, setPage] = useState(1);
  const query = useData<Row>(`/conversations/judges/${id}?page=${page}`);
  const action = useAction();
  const marked = useRef("");
  const [openedUnread, setOpenedUnread] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!query.data?.unread_count || !query.data.read_through || marked.current === query.data.read_through) return;
    marked.current = query.data.read_through;
    setOpenedUnread(current => new Set([...current, ...query.data!.messages.filter((message: Row) => message.direction === "incoming" && !message.read_at).map((message: Row) => message.id)]));
    action.mutate({ path: `/conversations/judges/${id}/read`, body: { read_through: query.data.read_through } }, { onError: () => { marked.current = ""; } });
  }, [id, query.data]);
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorBox error={query.error} />;
  const data = query.data;
  return <>
    <Back to="/campaigns">Campaigns</Back>
    <Heading title={data.judge.name} description={[data.judge.email, data.judge.phone].filter(Boolean).join(" · ")}><Link className="button primary" to="/campaigns/new" state={{ judge_ids: [id] }}><Plus size={16} /> Compose email</Link></Heading>
    <ErrorBox error={action.error} />
    <div className="conversation-thread">{data.messages.map((message: Row) => <article key={message.id} className={`conversation-message ${message.direction}${openedUnread.has(message.id) ? " newly-opened" : ""}`}>
      <div className="message-heading"><strong>{message.direction === "incoming" ? data.judge.name : "MIST Deck"}</strong><Badge value={message.status} /><small>{date(message.created_at)}</small></div>
      <small>{message.direction === "incoming" ? "From" : "To"}: {message.email}</small><h3>{message.subject}</h3><p className="message-body">{message.body}</p>{message.campaign_id && <Link to={`/campaigns/${message.campaign_id}`}>View campaign</Link>}
    </article>)}{!data.messages.length && <Empty>No email history yet.</Empty>}</div>
    <Pagination data={{ items: data.messages, total: data.total, page: data.page, page_size: data.page_size }} onPage={setPage} />
  </>;
}

export function SimulateIncoming() {
  const [open, setOpen] = useState(false);
  const action = useAction();
  const navigate = useNavigate();
  const [pendingId, setPendingId] = useState(requestId());
  return <>
    <button onClick={() => { setPendingId(requestId()); setOpen(true); }}>Simulate incoming email</button>
    {open && <Modal title="Simulate incoming email" onClose={() => setOpen(false)}><p className="caption">Use this to test replies and ticket notifications. A real mailbox is not connected.</p><form onSubmit={async event => {
      event.preventDefault(); const fd = new FormData(event.currentTarget);
      try { const result = await action.mutateAsync({ path: "/inbox/simulate", body: { sender_name: fd.get("sender_name"), sender_email: fd.get("sender_email"), subject: fd.get("subject"), body: fd.get("body"), request_id: pendingId } }); setOpen(false); navigate(result.judge_id ? `/campaigns?judge=${result.judge_id}` : result.href); } catch {}
    }}>
      <Field label="Sender name"><input name="sender_name" /></Field><Field label="Sender email"><input name="sender_email" type="email" required /></Field><Field label="Subject"><input name="subject" required /></Field><Field label="Message"><textarea name="body" required rows={5} /></Field>
      <ErrorBox error={action.error} /><button className="primary" disabled={action.isPending}>Receive sandbox email</button>
    </form></Modal>}
  </>;
}
