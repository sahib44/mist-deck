import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Plus, ShieldCheck } from "lucide-react";
import { useData, Page, Row, can, label, date } from "./api";
import { useUser } from "./App";
import { Notifications } from "./Inbox";
import {
  Heading,
  Panel,
  Loading,
  ErrorBox,
  Empty,
  Badge,
  Pagination,
  JsonDetails,
  Modal,
} from "./ui";
export function Dashboard() {
  const query = useData("/dashboard");
  const user = useUser();
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorBox error={query.error} />;
  const data = query.data;
  const judgeMetrics = data.metrics.filter((m: any) => !m.link.startsWith("/tickets"));
  const ticketMetrics = data.metrics.filter((m: any) => m.link.startsWith("/tickets"));
  const judgeGroups = Object.entries(data.groups).filter(([name]) => !name.startsWith("Tickets"));
  const ticketGroups = Object.entries(data.groups).filter(([name]) => name.startsWith("Tickets"));
  const metrics = (items: any[]) => (
    <div className="metrics">
      {items.map((m) => (
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
  );
  const groups = (items: [string, unknown][]) => (
    <div className="two-col">
      {items.map(([name, values]) => (
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
  );
  return (
    <>
      <Heading title="Operations overview" eyebrow="WORKSPACE"><Notifications /></Heading>
      {(judgeMetrics.length > 0 || judgeGroups.length > 0) && (
        <section className="overview-section" aria-labelledby="judge-overview-heading">
          <div className="section-heading">
            <h2 id="judge-overview-heading">Judge handling</h2>
            {can(user, "campaigns") && (
              <Link className="button primary" to="/campaigns/new">
                <Plus size={16} /> Create campaign
              </Link>
            )}
          </div>
          {metrics(judgeMetrics)}
          {groups(judgeGroups)}
          {data.latest_import && (
            <Panel
              title="Latest import"
              action={<Link to={"/imports/" + data.latest_import.id}>View import →</Link>}
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
        </section>
      )}
      {(ticketMetrics.length > 0 || ticketGroups.length > 0) && (
        <section className="overview-section" aria-labelledby="ticket-overview-heading">
          <div className="section-heading">
            <h2 id="ticket-overview-heading">Competitions tickets</h2>
            {can(user, "tickets") && user?.role !== "support_staff" && (
              <Link className="button" to="/tickets/new">
                <Plus size={16} /> New ticket
              </Link>
            )}
          </div>
          {metrics(ticketMetrics)}
          {groups(ticketGroups)}
        </section>
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
