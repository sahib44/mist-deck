import { useEffect, useState } from "react";
import {
  Link,
  useParams,
  useNavigate,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import { Plus, Send, Mail, ShieldCheck } from "lucide-react";
import { useData, useAction, api, Page, Row, can, label, date } from "./api";
import { useUser } from "./App";
import { RecipientPicker, EmailRecipient } from "./Recipients";
import { Conversations, SimulateIncoming } from "./Inbox";
import {
  Heading,
  Panel,
  Loading,
  ErrorBox,
  Empty,
  Badge,
  Pagination,
  Field,
  Modal,
  Back,
  ConfirmButton,
} from "./ui";
export function Campaigns() {
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/campaigns?" + params);
  return (
    <>
      <Heading
        title="Outreach campaigns"

      >
        <SimulateIncoming />
        <Link className="button primary" to="/campaigns/new">
          <Plus size={16} /> Create campaign
        </Link>
      </Heading>
      <div className="toolbar">
        <input aria-label="Search outreach campaigns" placeholder="Search campaigns, names, or emails" value={params.get("q") || ""} onChange={e => { const next = new URLSearchParams(params); next.delete("page"); e.target.value ? next.set("q", e.target.value) : next.delete("q"); setParams(next); }} />
        <select
          aria-label="Campaign status"
          value={params.get("status") || ""}
          onChange={e => { const next = new URLSearchParams(params); next.delete("page"); e.target.value ? next.set("status", e.target.value) : next.delete("status"); setParams(next); }}
        >
          <option value="">All campaigns</option>
          {[
            "draft",
            "pending_approval",
            "approved",
            "queued",
            "sending",
            "completed",
            "partially_failed",
            "cancelled",
          ].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      <Conversations search={params.get("q") || ""} judgeId={params.get("judge") || ""} />
      <h2 className="campaign-list-heading">Campaigns</h2>
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Status</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.name}</strong>
                    <small>{r.subject_template}</small>
                  </td>
                  <td>
                    <Badge value={r.status} />
                  </td>
                  <td>{date(r.created_at)}</td>
                  <td>
                    <Link className="button" to={"/campaigns/" + r.id}>
                      Open campaign
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && (
            <Empty>
              No campaigns match this view. Create a campaign to add recipients.
            </Empty>
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
    </>
  );
}
export function CampaignNew() {
  const [params] = useSearchParams();
  const pilotId = params.get("competition_id") || params.get("pilot_id");
  const pilot = useData<Row>(`/competitions/${pilotId}`, !!pilotId);
  const location = useLocation();
  const ids: string[] = location.state?.judge_ids || [];
  const [recipients, setRecipients] = useState<EmailRecipient[]>([]);
  const initial = useData<Row[]>(`/recipient-search?ids=${ids.join(",")}`, ids.length > 0);
  const [initialized, setInitialized] = useState(false);
  useEffect(() => {
    if (!initialized && initial.data) {
      setRecipients(initial.data.map(item => ({ key: item.id, judge_id: item.id, name: item.name, email: item.email })));
      setInitialized(true);
    }
  }, [initial.data, initialized]);
  const action = useAction();
  const navigate = useNavigate();
  const [excluded, setExcluded] = useState<any[]>([]);
  const [created, setCreated] = useState<Row | null>(null);
  const [fileError, setFileError] = useState<unknown>();
  return (
    <>
      <Back to={pilotId && pilot.data ? `/competitions/${pilot.data.category_slug}/${pilotId}` : "/campaigns"}>{pilotId ? "Competition" : "Campaigns"}</Back>
      <Heading
        title={pilotId ? `Compose for ${pilot.data?.name || "competition"}` : "Compose an invitation"}
        description="Each recipient receives a separate sandbox message."
      />
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          try {
            const result = await action.mutateAsync({
              path: "/campaigns",
              body: {
                name: fd.get("name"),
                subject_template: fd.get("subject"),
                body_template: fd.get("body"),
                judge_ids: recipients.filter(r => r.judge_id).map(r => r.judge_id),
                recipients: recipients.filter(r => !r.judge_id).map(r => ({ email: r.email, name: r.name, add_to_directory: !!r.add_to_directory })),
                pilot_competition_id: pilotId,
                variables: {
                  event_name: fd.get("event_name"),
                  event_date: fd.get("event_date"),
                  response_deadline: fd.get("response_deadline"),
                },
              },
            });
            try {
              for (const file of fd.getAll("attachments")) {
                if (!(file instanceof File) || !file.name) continue;
                const upload = new FormData();
                upload.set("file", file);
                await api(`/campaigns/${result.id}/attachments`, "POST", upload);
              }
            } catch (cause) {
              setFileError(cause);
              setCreated(result);
              return;
            }
            if (result.excluded.length) {
              setExcluded(result.excluded);
              setCreated(result);
            } else navigate("/campaigns/" + result.id);
          } catch {}
        }}
      >
        <div className="compose-grid">
          <Panel title="Campaign details">
            <Field label="Campaign name">
              <input
                name="name"
                required
                placeholder="Arts judges · Spring invitation"
              />
            </Field>
            <h3>Recipients</h3>
            <RecipientPicker recipients={recipients} onChange={setRecipients} />
            <ErrorBox error={initial.error} />
            <div className="form-grid">
              <Field label="Event name">
                <input
                  name="event_name"
                  defaultValue={pilot.data?.name || "MIST NJ · Sandbox Event"}
                />
              </Field>
              <Field label="Event date">
                <input type="date" name="event_date" />
              </Field>
              <Field label="Response deadline">
                <input type="date" name="response_deadline" />
              </Field>
            </div>
          </Panel>
          <Panel title="Message">
            <Field label="Subject">
              <input
                name="subject"
                required
                defaultValue="An invitation to judge {{event_name}}"
              />
            </Field>
            <Field label="Email body">
              <textarea
                rows={12}
                required
                name="body"
                defaultValue={
                  "Hello {{first_name}},\n\nWe would love to invite you to judge {{category_name}} at {{event_name}} on {{event_date}}.\n\nPlease respond by {{response_deadline}}.\n\nThank you,\nThe MIST NJ team"
                }
              />
            </Field>
            <Field label="Attachments (optional; up to five files, 5 MB each)">
              <input name="attachments" type="file" multiple accept=".pdf,.docx,.png,.jpg,.jpeg,.txt,.csv" />
            </Field>
            <div className="template-help">
              <strong>Personalization variables</strong>
              <div className="tags">
                {[
                  "judge_name",
                  "first_name",
                  "category_name",
                  "organization",
                  "event_name",
                  "event_date",
                  "response_deadline",
                ].map((v) => (
                  <code key={v}>{"{{" + v + "}}"}</code>
                ))}
              </div>
            </div>
          </Panel>
        </div>
        <div className="review-callout">
          <ShieldCheck size={22} />
          <p>
            Do-not-contact records and invalid emails are excluded. Recipients
            are deduplicated before you preview and request approval. Delivery stays in the sandbox outbox.
          </p>
        </div>
        <ErrorBox error={action.error || fileError} />
        <div className="form-footer">
          <Link to="/campaigns">Cancel</Link>
          <button className="primary" disabled={action.isPending || !!created || !recipients.length || (ids.length > 0 && !initialized)}>
            <Mail size={16} /> Create draft & preview
          </button>
        </div>
      </form>
      {created && (
        <Modal
          title="Review recipient exclusions"
          onClose={() => navigate("/campaigns/" + created.id)}
        >
          <p>{created.recipient_count} eligible recipients remain.</p>
          {!!fileError && <p>The draft was created, but an attachment failed. Open the draft to retry the upload.</p>}
          {excluded.map((r, i) => (
            <p key={i}>
              {r.judge_name}: {r.reason}
            </p>
          ))}
          <Link className="button primary" to={"/campaigns/" + created.id}>
            Continue to preview
          </Link>
        </Modal>
      )}
    </>
  );
}
export function RecipientPreview({ recipients }: { recipients: Row[] }) {
  const [selected, setSelected] = useState<string>("");
  const recipient = recipients.find((r) => r.id === selected) || recipients[0];
  return recipient ? (
    <div className="preview-layout">
      <div className="recipient-list">
        {recipients.map((r) => (
          <button
            key={r.id}
            className={r.id === recipient.id ? "selected" : ""}
            onClick={() => setSelected(r.id)}
          >
            <Mail size={16} />
            <span>
              {r.recipient_name || r.recipient_email}
              <small>{r.recipient_email} · {label(r.status)}</small>
              {r.failure_reason && <small className="delivery-failure">{r.failure_reason}</small>}
            </span>
          </button>
        ))}
      </div>
      <article className="email-preview">
        <div className="email-meta">
          <span>TO</span>
          <strong>{recipient.recipient_email}</strong>
          <small>One recipient · No Cc or Bcc</small>
        </div>
        <h3>{recipient.rendered_subject}</h3>
        <p className="message-body">{recipient.rendered_body}</p>
      </article>
    </div>
  ) : (
    <Empty />
  );
}
export function CampaignDetail() {
  const { id } = useParams();
  const query = useData<Row>("/campaigns/" + id);
  const [page, setPage] = useState(1);
  const previews = useData<Page>(`/campaigns/${id}/preview?page=${page}`);
  const action = useAction();
  const [fileError, setFileError] = useState<unknown>();
  const user = useUser();
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorBox error={query.error} />;
  const c = query.data;
  return (
    <>
      <Back to="/campaigns">Campaigns</Back>
      <Heading
        title={c.name}
        description="Review each invitation before it enters the sandbox queue."
      >
        <Badge value={c.status} />
      </Heading>
      <div className="campaign-summary">
        <div>
          <strong>{c.recipient_count}</strong>
          <span>individual emails</span>
        </div>
        {Object.entries(c.counts || {}).map(([key, value]) => (
          <div key={key}>
            <strong>{String(value)}</strong>
            <span>{label(key)}</span>
          </div>
        ))}
        <div>
          <ShieldCheck size={24} />
          <span>Sandbox delivery only</span>
        </div>
      </div>
      <ErrorBox error={action.error} />
      {!!c.failed_recipients?.length && <div className="error-box" role="alert"><strong>Delivery failed for:</strong>{c.failed_recipients.map((recipient: Row) => <p key={recipient.id}>{recipient.recipient_name} · {recipient.recipient_email}: {recipient.failure_reason}</p>)}</div>}
      <Panel title="Attachments">
        {c.attachments?.length ? <ul className="attachment-list">{c.attachments.map((file: Row) => <li key={file.id}><a href={`/api/campaigns/${id}/attachments/${file.id}`}>{file.filename}</a> <small>({Math.ceil(file.size / 1024)} KB)</small>{c.status === "draft" && can(user, "delete") && <button onClick={() => action.mutate({ path: `/campaigns/${id}/attachments/${file.id}`, method: "DELETE" })}>Remove</button>}</li>)}</ul> : <p className="caption">No files attached.</p>}
        {c.status === "draft" && <Field label="Add file (PDF, DOCX, PNG, JPG, TXT, or CSV; 5 MB max)"><input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg,.txt,.csv" onChange={async e => { const file = e.target.files?.[0]; if (!file) return; const body = new FormData(); body.set("file", file); try { await api(`/campaigns/${id}/attachments`, "POST", body); setFileError(undefined); query.refetch(); e.target.value = ""; } catch (cause) { setFileError(cause); } }} /></Field>}
        <ErrorBox error={fileError} />
      </Panel>
      <div className="toolbar">
        <div className="actions">
          {c.status === "draft" && (
            <button
              className="primary"
              onClick={() =>
                action.mutate({ path: "/campaigns/" + id + "/submit" })
              }
            >
              Submit for approval
            </button>
          )}
          {c.status === "pending_approval" && can(user, "approve") && (
            <ConfirmButton
              question={`Approve ${c.recipient_count} individual sandbox emails?`}
              onConfirm={() =>
                action.mutate({ path: "/campaigns/" + id + "/approve" })
              }
            >
              Approve campaign
            </ConfirmButton>
          )}
          {c.status === "approved" && (
            <ConfirmButton
              question={`Queue ${c.recipient_count} individual sandbox messages?`}
              onConfirm={() =>
                action.mutate({ path: "/campaigns/" + id + "/queue" })
              }
            >
              Queue sandbox delivery
            </ConfirmButton>
          )}
          {!["completed", "partially_failed", "cancelled"].includes(c.status) &&
            can(user, "approve") && (
              <ConfirmButton
                question="Cancel this campaign and stop all unsent messages?"
                onConfirm={() =>
                  action.mutate({ path: "/campaigns/" + id + "/cancel" })
                }
              >
                Cancel campaign
              </ConfirmButton>
            )}
        </div>
        <Link className="button" to={"/outbox?campaign_id=" + id}>
          View sandbox outbox
        </Link>
      </div>
      <Panel title="Recipient-by-recipient preview">
        <ErrorBox error={previews.error} />
        {previews.isPending ? (
          <Loading />
        ) : (
          <RecipientPreview recipients={previews.data?.items || []} />
        )}
        <Pagination data={previews.data} onPage={setPage} />
      </Panel>
    </>
  );
}
export function Outbox() {
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/outbox?" + params);
  const action = useAction();
  const user = useUser();
  const [selected, setSelected] = useState<Row | null>(null);
  const [forwarding, setForwarding] = useState(false);
  const [forwardNotice, setForwardNotice] = useState("");
  const current =
    query.data?.items.find((r) => r.id === selected?.id) || selected;
  return (
    <>
      <Heading
        title="Sandbox outbox"
        description="Every outbound message, safely captured in your local database."
      />
      <div className="review-callout outbox-reassurance">
        <ShieldCheck size={22} />
        <p>
          No email leaves this application. Delivery receipts below represent
          database captures by the mock provider.
        </p>
      </div>
      <div className="toolbar">
        <input
          aria-label="Search messages"
          placeholder="Search recipient or subject…"
          value={params.get("q") || ""}
          onChange={(e) => {
            params.set("q", e.target.value);
            params.delete("page");
            setParams(params);
          }}
        />
        <select
          aria-label="Message status"
          value={params.get("status") || ""}
          onChange={(e) => {
            params.set("status", e.target.value);
            params.delete("page");
            setParams(params);
          }}
        >
          <option value="">All statuses</option>
          {["queued", "sending", "sent", "failed", "cancelled"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      <ErrorBox error={query.error || action.error} />
      {forwardNotice && <div role="status" className="notice">{forwardNotice}</div>}
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Recipient & subject</th>
                <th>Related to</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Completed</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.recipient_email}</strong>
                    <small>{r.subject}</small>
                  </td>
                  <td>
                    {r.related_ticket_id ? (
                      <Link to={"/tickets/" + r.related_ticket_id}>
                        Support ticket
                      </Link>
                    ) : (
                      "Campaign"
                    )}
                  </td>
                  <td>
                    <Badge value={r.status} />
                  </td>
                  <td>{r.attempt_count} / 3</td>
                  <td>{date(r.completed_at)}</td>
                  <td>
                    <button onClick={() => { setSelected(r); setForwarding(false); }}>Read message</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && (
            <Empty>No sandbox messages match this view.</Empty>
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
      {current && (
        <Modal title="Sandbox message" onClose={() => setSelected(null)}>
          <div className="email-meta">
            <span>TO</span>
            <strong>{current.recipient_email}</strong>
            <Badge value={current.status} />
          </div>
          <h3>{current.subject}</h3>
          <p className="message-body">{current.body_text}</p>
          {!!current.attachments?.length && <div className="attachment-list"><strong>Attachments</strong>{current.attachments.map((file: Row) => <a key={file.id} href={`/api/outbox/${current.id}/attachments/${file.id}`}>{file.filename}</a>)}</div>}
          <dl>
            <div>
              <dt>Created</dt>
              <dd>{date(current.created_at)}</dd>
            </div>
            <div>
              <dt>Completed</dt>
              <dd>{date(current.completed_at)}</dd>
            </div>
            <div>
              <dt>Receipt</dt>
              <dd>{current.provider_message_id || "Pending"}</dd>
            </div>
            <div>
              <dt>Attempts</dt>
              <dd>{current.attempt_count}</dd>
            </div>
          </dl>
          {current.last_error && <ErrorBox error={current.last_error} />}
          <ErrorBox error={action.error} />
          {current.status === "sent" && can(user, "outbox") && <button onClick={() => setForwarding(!forwarding)}>{forwarding ? "Cancel forward" : "Forward message"}</button>}
          {forwarding && <form onSubmit={async e => { e.preventDefault(); const values = new FormData(e.currentTarget); try { await action.mutateAsync({ path: `/outbox/${current.id}/forward`, body: { recipient_email: values.get("recipient_email"), note: values.get("note") } }); setForwardNotice("Forward queued in the sandbox outbox."); setForwarding(false); setSelected(null); } catch {} }}>
            <Field label="Forward to"><input name="recipient_email" type="email" required placeholder="registration@example.com" /></Field>
            <Field label="Note (optional)"><textarea name="note" rows={3} /></Field>
            <p className="caption">The original message and its attachments will be included. Delivery stays in the sandbox.</p>
            <button className="primary" disabled={action.isPending}>Queue sandbox forward</button>
          </form>}
          {can(user, "jobs") &&
            ["queued", "failed"].includes(current.status) && (
              <div className="actions">
                <button
                  onClick={() =>
                    action.mutate({
                      path: "/outbox/" + current.id + "/failure",
                      body: { enabled: !current.simulate_failure },
                    })
                  }
                >
                  {current.simulate_failure ? "Disable" : "Enable"} failure
                  simulation
                </button>
                {current.status === "failed" && (
                  <button
                    onClick={() =>
                      action.mutate({
                        path: "/outbox/" + current.id + "/retry",
                      })
                    }
                  >
                    Retry failed message
                  </button>
                )}
              </div>
            )}
        </Modal>
      )}
    </>
  );
}
