import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Plus, ShieldCheck } from "lucide-react";
import { useData, useAction, Page, Row, can, label, date } from "./api";
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
  JsonDetails,
  Modal,
} from "./ui";
export function Dashboard() {
  const query = useData("/dashboard");
  const user = useUser();
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorBox error={query.error} />;
  const data = query.data;
  return (
    <>
      <Heading
        eyebrow="YOUR WORKSPACE AT A GLANCE"
        title="Operations overview"
        description="The people, conversations, and next steps that need your attention."
      >
        {can(user, "tickets") && user?.role !== "support_staff" && (
          <Link className="button" to="/tickets/new">
            <Plus size={16} /> New ticket
          </Link>
        )}
        {can(user, "campaigns") && (
          <Link className="button primary" to="/campaigns/new">
            <Plus size={16} /> Create campaign
          </Link>
        )}
      </Heading>
      <div className="overview-banner">
        <div>
          <span className="eyebrow">MIST NJ · ORGANIZER WORKSPACE</span>
          <h2>A clearer view of what’s next.</h2>
          <p>Keep judge outreach and competitor support moving together.</p>
        </div>
        <div className="banner-mark">
          <ShieldCheck size={30} />
          <span>
            Every message stays
            <br />
            inside your sandbox.
          </span>
        </div>
      </div>
      <div className="metrics">
        {data.metrics.map((m: any) => (
          <Link key={m.label} to={m.link} className="metric">
            <span>
              {m.label}
              <ArrowUpRight size={17} />
            </span>
            <strong>{m.value}</strong>
            <small>View records</small>
          </Link>
        ))}
      </div>
      <div className="two-col">
        {Object.entries(data.groups).map(([name, values]) => (
          <Panel key={name} title={name}>
            {(values as any[]).length ? (
              (values as any[]).map((v) => (
                <Link className="stat-row" key={v.label} to={v.link}>
                  <span>{label(v.label)}</span>
                  <strong>{v.value}</strong>
                  <ArrowUpRight size={15} />
                </Link>
              ))
            ) : (
              <Empty />
            )}
          </Panel>
        ))}
      </div>
      {data.latest_import && (
        <Panel
          title="Latest import"
          action={
            <Link to={"/imports/" + data.latest_import.id}>View import →</Link>
          }
        >
          <div className="summary-strip">
            <strong>{data.latest_import.filename}</strong>
            <Badge value={data.latest_import.status} />
            <span>{data.latest_import.created_count} created</span>
            <span>{data.latest_import.updated_count} updated</span>
            <span>{data.latest_import.skipped_count} skipped</span>
          </div>
        </Panel>
      )}
      {can(user, "audit") && (
        <Panel
          title="Recent activity"
          action={<Link to="/audit">Open audit trail →</Link>}
        >
          {data.recent_activity.length ? (
            data.recent_activity.map((a: Row) => (
              <Link to={"/audit?q=" + a.action} key={a.id} className="activity">
                <span className="activity-icon">
                  <ShieldCheck size={16} />
                </span>
                <div>
                  <strong>{a.summary}</strong>
                  <small>{label(a.action)}</small>
                </div>
                <time>{date(a.created_at)}</time>
              </Link>
            ))
          ) : (
            <Empty />
          )}
        </Panel>
      )}
      <p className="caption">{data.overdue_definition}</p>
    </>
  );
}
export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/audit-events?" + params);
  const [selected, setSelected] = useState<Row | null>(null);
  return (
    <>
      <Heading
        title="Audit trail"
        description="A traceable record of important actions across your workspace."
      />
      <div className="toolbar">
        <input
          aria-label="Search audit events"
          placeholder="Search actions or summaries…"
          value={params.get("q") || ""}
          onChange={(e) => setParams({ q: e.target.value })}
        />
      </div>
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Summary</th>
                <th>Recorded</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Badge value={r.action} />
                  </td>
                  <td>{r.summary}</td>
                  <td>{date(r.created_at)}</td>
                  <td>
                    <button onClick={() => setSelected(r)}>Inspect</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && <Empty />}
          <Pagination
            data={query.data}
            onPage={(n) => {
              params.set("page", String(n));
              setParams(params);
            }}
          />
        </div>
      )}
      {selected && (
        <Modal title="Audit event" onClose={() => setSelected(null)}>
          <JsonDetails data={selected} />
        </Modal>
      )}
    </>
  );
}
export function SettingsPage() {
  const { kind = "categories" } = useParams();
  const user = useUser();
  const [page, setPage] = useState(1);
  const query = useData<Page>(
    (kind === "users" ? "/users" : "/catalogs/" + kind) + "?page=" + page,
    kind !== "system",
  );
  const action = useAction();
  const [edit, setEdit] = useState<Row | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [active, setActive] = useState(true);
  const [role, setRole] = useState("support_staff");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  function start(row?: Row) {
    setEdit(row || { id: "" });
    setName(row?.name || "");
    setDescription(row?.description || "");
    setActive(row?.is_active ?? true);
    setRole(row?.role || "support_staff");
    setPermissions(row?.permissions || []);
  }
  return (
    <>
      <Heading
        title="Workspace settings"
        description="Manage shared categories, qualifications, and organizer access."
      />
      <div className="tabs">
        {[
          "categories",
          "qualifications",
          "committees",
          ...(can(user, "users") ? ["users"] : []),
          ...(can(user, "jobs") ? ["system"] : []),
        ].map((k) => (
          <Link
            className={kind === k ? "active" : ""}
            to={"/settings/" + k}
            key={k}
            onClick={() => setPage(1)}
          >
            {label(k)}
          </Link>
        ))}
      </div>
      {kind === "system" ? (
        <SystemSettings />
      ) : kind === "users" && !can(user, "users") ? (
        <ErrorBox error="Only directors can manage user roles." />
      ) : (
        <>
          <div className="section-heading">
            <h2>{label(kind)}</h2>
            {kind !== "users" && (
              <button className="primary" onClick={() => start()}>
                <Plus size={16} /> Add {kind === "categories" ? "category" : kind.slice(0, -1)}
              </button>
            )}
          </div>
          {notice && (
            <p role="status" className="notice">
              {notice}
            </p>
          )}
          <ErrorBox error={query.error} />
          {query.isPending ? (
            <Loading />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>{kind === "users" ? "Role" : "Description"}</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {query.data?.items.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <strong>{r.name || r.full_name}</strong>
                        {r.email && <small>{r.email}</small>}
                      </td>
                      <td>{label(r.role || r.description)}</td>
                      <td>
                        <Badge value={r.is_active ? "active" : "inactive"} />
                      </td>
                      <td>
                        <button onClick={() => start(r)}>Edit</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination data={query.data} onPage={setPage} />
            </div>
          )}
          {edit && (
            <Modal
              title={
                kind === "users"
                  ? "Manage organizer access"
                  : edit.id
                    ? "Edit catalog entry"
                    : "Add catalog entry"
              }
              onClose={() => setEdit(null)}
            >
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await action.mutateAsync({
                      path:
                        kind === "users"
                          ? "/users/" + edit.id
                          : "/catalogs/" +
                            kind +
                            (edit.id ? "/" + edit.id : ""),
                      method: edit.id ? "PATCH" : "POST",
                      body:
                        kind === "users"
                          ? { role, permissions, is_active: active }
                          : { name, description, is_active: active },
                    });
                    setEdit(null);
                    setNotice("Changes saved.");
                  } catch {}
                }}
              >
                {kind === "users" ? (
                  <>
                    <Field label="Role">
                      <select
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                      >
                        {[
                          "director",
                          "technology_administrator",
                          "competitions_administrator",
                          "support_staff",
                        ].map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                    </Field>
                    {["campaign_approver", "private_tickets"].map((p) => (
                      <label className="check" key={p}>
                        <input
                          type="checkbox"
                          checked={permissions.includes(p)}
                          onChange={(e) =>
                            setPermissions(
                              e.target.checked
                                ? [...permissions, p]
                                : permissions.filter((x) => x !== p),
                            )
                          }
                        />
                        {label(p)}
                      </label>
                    ))}
                  </>
                ) : (
                  <>
                    <Field label="Name">
                      <input
                        required
                        maxLength={200}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </Field>
                    <Field label="Description">
                      <textarea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                      />
                    </Field>
                  </>
                )}
                <label className="check">
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={(e) => setActive(e.target.checked)}
                  />
                  Active
                </label>
                <ErrorBox error={action.error} />
                <button className="primary" disabled={action.isPending}>
                  Save changes
                </button>
              </form>
            </Modal>
          )}
        </>
      )}
    </>
  );
}

function SystemSettings() {
  const query = useData("/system");
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorBox error={query.error} />;
  const d = query.data;
  return (
    <>
      <Panel title="System health">
        <div className="summary-strip">
          {["api", "database", "worker"].map((k) => (
            <div key={k}>
              <strong>{label(k)}</strong> <Badge value={d[k]} />
            </div>
          ))}
        </div>
        <p>
          Configuration comes from environment variables. Update your local .env
          and restart services to change import limits or development
          credentials.
        </p>
        <dl>
          {[
            "email_provider",
            "sandbox_enforced",
            "max_import_bytes",
            "max_import_rows",
            "retry_limit",
            "stale_claim_minutes",
          ].map((k) => (
            <div key={k}>
              <dt>{label(k)}</dt>
              <dd>{String(d[k])}</dd>
            </div>
          ))}
        </dl>
      </Panel>
      <Panel title="Outbound job queue">
        {Object.entries(d.queue).length ? (
          Object.entries(d.queue).map(([k, v]) => (
            <Link className="stat-row" to={"/outbox?status=" + k} key={k}>
              <span>{label(k)}</span>
              <strong>{String(v)}</strong>
            </Link>
          ))
        ) : (
          <Empty>No jobs have been queued.</Empty>
        )}
      </Panel>
    </>
  );
}
