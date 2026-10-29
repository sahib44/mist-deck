import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FileText, Mail, Plus, Trash2, Upload, Users } from "lucide-react";
import { useAction, useData, Page, Row, can, date } from "./api";
import { useUser } from "./App";
import { UnreadMarker } from "./Inbox";
import { Back, Empty, ErrorBox, Field, Heading, Loading, Modal, Pagination, Panel } from "./ui";

const stages = [
  ["", "All judges"],
  ["to_contact", "To contact"],
  ["awaiting_response", "Awaiting response"],
  ["accepted", "Accepted"],
  ["declined", "Declined"],
] as const;

type Category = { slug: string; name: string; competition_count: number; unread_count: number };

export function Competitions() {
  const categories = useData<Category[]>("/competitions/categories");
  const user = useUser();
  return <>
    <Heading eyebrow="JUDGE HANDLING" title="Competitions">{(can(user, "judges") || can(user, "audit")) && <Link className="button" to="/competitions/deletions">Deleted pilots</Link>}</Heading>
    <ErrorBox error={categories.error} />
    {categories.isPending ? <Loading /> : <div className="pilot-grid">
      {categories.data?.map((category) => <Link className="pilot-card" to={`/competitions/${category.slug}`} key={category.slug}>
        <span className="pilot-card-icon"><Users size={20} /></span>
        <strong>{category.name} <UnreadMarker count={category.unread_count} /></strong>
        <small>{category.competition_count} competitions</small>
      </Link>)}
    </div>}
  </>;
}

export function DeletedCompetitions() {
  const [page, setPage] = useState(1);
  const query = useData<Page>(`/competitions/deletions?page=${page}`);
  return <>
    <Back to="/competitions">Competitions</Back>
    <Heading title="Deleted pilots" />
    <ErrorBox error={query.error} />
    {query.isPending ? <Loading /> : <div className="table-wrap"><table><thead><tr><th>Pilot</th><th>Category</th><th>Year</th><th>Deleted by</th><th>Deleted</th></tr></thead><tbody>
      {query.data?.items.map((row: Row) => <tr key={row.id}><td>{row.name}</td><td>{row.category_name}</td><td>{row.event_year}</td><td>{row.deleted_by_name}</td><td>{date(row.deleted_at)}</td></tr>)}
    </tbody></table>{query.data?.total === 0 && <Empty>No pilots have been deleted.</Empty>}<Pagination data={query.data} onPage={setPage} /></div>}
  </>;
}

export function CompetitionCategory() {
  const { category = "" } = useParams();
  const categories = useData<Category[]>("/competitions/categories");
  const categoryName = categories.data?.find((item) => item.slug === category)?.name || "Competitions";
  const query = useData<Page>(`/competitions?category_slug=${encodeURIComponent(category)}&page_size=100`);
  const existing = useData<Page>("/judges?page_size=100");
  const action = useAction();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  return (
    <>
      <Back to="/competitions">Competitions</Back>
      <Heading eyebrow="COMPETITIONS" title={categoryName}>
        <button className="primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> Add pilot competition
        </button>
      </Heading>
      <ErrorBox error={query.error} />
      {query.isPending ? <Loading /> : query.data?.items.length ? (
        <div className="pilot-grid">
          {query.data.items.map((pilot) => (
            <Link className="pilot-card" to={`/competitions/${category}/${pilot.id}`} key={pilot.id}>
              <span className="pilot-card-icon"><Users size={20} /></span>
              {pilot.is_pilot && <span className="pilot-card-year">PILOT · {pilot.event_year}</span>}
              <strong>{pilot.name} <UnreadMarker count={pilot.unread_count} /></strong>
              <span>{Object.values(pilot.counts || {}).reduce((sum: number, n: any) => sum + Number(n), 0)} judges</span>
              <small>{pilot.documents?.length || 0} documents</small>
            </Link>
          ))}
        </div>
      ) : <Empty>No competitions in this category yet.</Empty>}
      {creating && (
        <Modal title="Add pilot competition" onClose={() => setCreating(false)}>
          <form onSubmit={async (event) => {
            event.preventDefault();
            const body = new FormData(event.currentTarget);
            body.set("judge_ids", JSON.stringify(chosen));
            body.set("category_slug", category);
            try {
              const result = await action.mutateAsync({ path: "/competitions", body });
              navigate(`/competitions/${category}/${result.id}`);
            } catch {}
          }}>
            <Field label="Competition name"><input name="name" required maxLength={200} /></Field>
            <Field label="Event year"><input name="event_year" type="number" min="2000" max="2200" required /></Field>
            <Field label="Rules (optional PDF or DOCX)"><input name="rules" type="file" accept=".pdf,.docx" /></Field>
            <Field label="Procedures (optional PDF or DOCX)"><input name="procedures" type="file" accept=".pdf,.docx" /></Field>
            <details className="pilot-existing">
              <summary>Add existing judges (optional) · {chosen.length} selected</summary>
              <div className="pilot-existing-list">
                {existing.data?.items.map((judge) => (
                  <label key={judge.id}>
                    <input type="checkbox" checked={chosen.includes(judge.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, judge.id] : chosen.filter((id) => id !== judge.id))} />
                    <span>{judge.display_name}<small>{judge.primary_email || judge.phone || "No contact method"}</small></span>
                  </label>
                ))}
              </div>
            </details>
            <p className="caption">Documents stay in the local database. No email is sent when you create a pilot.</p>
            <ErrorBox error={action.error} />
            <div className="form-footer"><button type="button" onClick={() => setCreating(false)}>Cancel</button><button className="primary" disabled={action.isPending}>Create pilot</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}

export function PilotDetail() {
  const user = useUser();
  const { id = "" } = useParams();
  const pilot = useData<Row>(`/competitions/${id}`);
  const action = useAction();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [existingMode, setExistingMode] = useState(false);
  const [existingSearch, setExistingSearch] = useState("");
  const [existingId, setExistingId] = useState("");
  const [documentKind, setDocumentKind] = useState("");
  const [deleteStep, setDeleteStep] = useState(0);
  const [deleteName, setDeleteName] = useState("");
  const [localError, setLocalError] = useState<unknown>();
  const existing = useData<Page>(`/judges?page_size=25&q=${encodeURIComponent(existingSearch)}`, adding && existingMode);
  const params = new URLSearchParams({ page: String(page), page_size: "100" });
  if (status) params.set("status", status);
  if (overdue) params.set("overdue_days", "7");
  if (search) params.set("q", search);
  const nominations = useData<Page>(`/competitions/${id}/judges?${params}`);
  if (pilot.isPending) return <Loading />;
  if (!pilot.data) return <ErrorBox error={pilot.error} />;
  const details = pilot.data;
  const documents = Object.fromEntries((details.documents || []).map((doc: Row) => [doc.kind, doc]));
  const visible = nominations.data?.items || [];
  const selectedJudges = visible.filter((nomination) => selected.includes(nomination.id));
  const mailReady = selectedJudges.filter((nomination) => nomination.judge.primary_email && !nomination.judge.do_not_contact && nomination.status !== "declined");
  function changeFilter(nextStatus: string, nextOverdue: boolean) {
    setStatus(nextStatus); setOverdue(nextOverdue); setPage(1); setSelected([]);
  }
  return (
    <>
      <Back to={`/competitions/${details.category_slug}`}>Competitions</Back>
      <Heading eyebrow={details.is_pilot ? `PILOT · ${details.event_year}` : `COMPETITION · ${details.event_year}`} title={details.name}>
        <button className="primary" onClick={() => setAdding(true)}><Plus size={16} /> Add judge</button>
        {details.is_pilot && can(user, "delete") && <button className="pilot-delete" onClick={() => setDeleteStep(1)}><Trash2 size={16} /> Delete pilot</button>}
      </Heading>
      <div className="pilot-summary">
        <button onClick={() => changeFilter("", false)} className={!status && !overdue ? "active" : ""}><strong>{Object.values(details.counts || {}).reduce((sum: number, n: any) => sum + Number(n), 0)}</strong><span>All judges</span></button>
        {stages.slice(1).map(([key, title]) => <button key={key} onClick={() => changeFilter(status === key && !overdue ? "" : key, false)} className={status === key && !overdue ? "active" : ""}><strong>{details.counts?.[key] || 0}</strong><span>{title}</span></button>)}
      </div>
      <div className="two-col">
        {(["rules", "procedures"] as const).map((kind) => (
          <Panel key={kind} title={kind === "rules" ? "Rules" : "Procedures"}>
            {documents[kind] ? (
              <div className="pilot-document">
                <FileText size={20} />
                <a href={`/api/competitions/${id}/documents/${kind}`} target="_blank" rel="noreferrer">{documents[kind].filename}</a>
              </div>
            ) : <p>No {kind} uploaded yet.</p>}
            <button onClick={() => setDocumentKind(kind)}><Upload size={15} /> {documents[kind] ? "Replace" : "Upload"} {kind}</button>
          </Panel>
        ))}
      </div>
      <Panel title="Judges" action={<span className="caption">{nominations.data?.total ?? 0} in this view</span>}>
        <div className="pilot-filters">
          <Field label="Response status"><select value={status} onChange={(e) => changeFilter(e.target.value, false)}>{stages.map(([key, title]) => <option value={key} key={key}>{title}</option>)}</select></Field>
          <Field label="Search judges"><input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); setSelected([]); }} placeholder="Name or email" /></Field>
          <label className="pilot-overdue"><input type="checkbox" checked={overdue} onChange={(e) => changeFilter(e.target.checked ? "awaiting_response" : "", e.target.checked)} /> Waiting 7+ days</label>
        </div>
        <p className="caption">A completed sandbox message moves a judge from To contact to Awaiting response. No external email is sent.</p>
        {selected.length > 0 && <div className="selection-bar"><strong>{selected.length} selected</strong><button disabled={!mailReady.length} onClick={() => {
          if (mailReady.length !== selected.length) { setLocalError("Only selected judges with an email who have not declined or opted out can receive a sandbox draft."); return; }
          navigate(`/campaigns/new?competition_id=${id}`, { state: { judge_ids: mailReady.map((n) => n.judge.id) } });
        }}><Mail size={16} /> Email selected ({mailReady.length})</button></div>}
        <ErrorBox error={nominations.error || action.error || localError} />
        {nominations.isPending ? <Loading /> : visible.length ? (
          <div className="pilot-judge-list">
            <label className="pilot-select-all"><input type="checkbox" aria-label="Select visible judges" checked={visible.every((n) => selected.includes(n.id))} onChange={(e) => setSelected(e.target.checked ? visible.map((n) => n.id) : [])} /> Select visible judges</label>
            {visible.map((nomination) => (
              <article className="pilot-judge" key={nomination.id}>
                <input type="checkbox" aria-label={`Select ${nomination.judge.display_name}`} checked={selected.includes(nomination.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, nomination.id] : selected.filter((x) => x !== nomination.id))} />
                <div className="pilot-judge-main">
                  <Link to={`/campaigns/conversations/judges/${nomination.judge.id}`}><strong>{nomination.judge.display_name}</strong></Link> <UnreadMarker count={nomination.unread_count} />
                  <small>{nomination.judge.primary_email || "No email"}{nomination.judge.phone ? ` · ${nomination.judge.phone}` : ""}</small>
                  {(nomination.qualification_text || !!nomination.judge.qualifications?.length) && <p className="caption">{nomination.qualification_text || nomination.judge.qualifications.join("; ")}</p>}
                  {nomination.last_contacted_at && <small>Awaiting since {date(nomination.last_contacted_at)}</small>}
                </div>
                <Field label="Response"><select value={nomination.status} onChange={(e) => { setSelected((current) => current.filter((selectedId) => selectedId !== nomination.id)); action.mutate({ path: `/competitions/${id}/judges/${nomination.id}`, method: "PATCH", body: { status: e.target.value } }); }}>{stages.slice(1).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></Field>
              </article>
            ))}
            <Pagination data={nominations.data} onPage={(next) => { setPage(next); setSelected([]); }} />
          </div>
        ) : <Empty>No judges match this view.</Empty>}
      </Panel>
      {adding && <Modal title="Add judge to competition" onClose={() => { setAdding(false); setExistingMode(false); }}>
        <form onSubmit={async (event) => {
          event.preventDefault();
          const fd = new FormData(event.currentTarget);
          try {
            await action.mutateAsync({ path: `/competitions/${id}/judges`, body: {
              name: existingMode ? "Existing judge" : fd.get("name"),
              email: existingMode ? "" : fd.get("email"),
              phone: existingMode ? "" : fd.get("phone"),
              qualifications: existingMode ? "" : fd.get("qualifications"),
              existing_judge_id: existingMode ? existingId : null,
            }});
            setAdding(false); setExistingMode(false); setExistingId("");
          } catch {}
        }}>
          <div className="tabs"><button type="button" className={!existingMode ? "active" : ""} onClick={() => setExistingMode(false)}>New judge</button><button type="button" className={existingMode ? "active" : ""} onClick={() => setExistingMode(true)}>Existing contact</button></div>
          {existingMode ? <>
            <Field label="Search directory"><input value={existingSearch} onChange={(e) => setExistingSearch(e.target.value)} placeholder="Name or email" /></Field>
            <Field label="Judge contact"><select required value={existingId} onChange={(e) => setExistingId(e.target.value)}><option value="">Choose a contact</option>{existing.data?.items.map((judge) => <option key={judge.id} value={judge.id}>{judge.display_name} · {judge.primary_email || judge.phone}</option>)}</select></Field>
          </> : <>
            <Field label="Name"><input name="name" required maxLength={400} /></Field>
            <div className="form-grid"><Field label="Email"><input name="email" type="email" maxLength={254} /></Field><Field label="Phone"><input name="phone" type="tel" maxLength={50} /></Field></div>
            <p className="caption">At least one contact method is required. Email is required to create a sandbox message.</p>
            <Field label="Why this judge is qualified (optional)"><textarea name="qualifications" rows={3} maxLength={2000} /></Field>
          </>}
          <ErrorBox error={action.error} />
          <div className="form-footer"><button type="button" onClick={() => setAdding(false)}>Cancel</button><button className="primary" disabled={action.isPending || (existingMode && !existingId)}>Add judge</button></div>
        </form>
      </Modal>}
      {documentKind && <Modal title={`Upload ${documentKind}`} onClose={() => setDocumentKind("")}>
        <form onSubmit={async (event) => {
          event.preventDefault();
          const body = new FormData(event.currentTarget);
          try { await action.mutateAsync({ path: `/competitions/${id}/documents/${documentKind}`, method: "PUT", body }); setDocumentKind(""); } catch {}
        }}>
          <Field label="PDF or DOCX (up to 5 MB)"><input type="file" name="file" accept=".pdf,.docx" required /></Field>
          <ErrorBox error={action.error} />
          <button className="primary" disabled={action.isPending}>Save document</button>
        </form>
      </Modal>}
      {deleteStep > 0 && <Modal title="Delete pilot competition" onClose={() => { setDeleteStep(0); setDeleteName(""); }}>
        {deleteStep === 1 && <><p>Are you sure you want to delete <strong>{details.name}</strong>?</p><div className="form-footer"><button onClick={() => setDeleteStep(0)}>Cancel</button><button className="pilot-delete" onClick={() => setDeleteStep(2)}>Yes, continue</button></div></>}
        {deleteStep === 2 && <><p>Are you really sure? This pilot will disappear from competition lists. Its deletion remains in the audit trail.</p><div className="form-footer"><button onClick={() => setDeleteStep(0)}>Cancel</button><button className="pilot-delete" onClick={() => setDeleteStep(3)}>Continue to final confirmation</button></div></>}
        {deleteStep === 3 && <form onSubmit={async (event) => { event.preventDefault(); try { await action.mutateAsync({ path: `/competitions/${id}`, method: "DELETE", body: { confirmed_first: true, confirmed_second: true, exact_name: deleteName } }); navigate(`/competitions/${details.category_slug}`); } catch {} }}>
          <p>Type <strong>{details.name}</strong> exactly to delete this pilot.</p>
          <Field label="Competition name"><input value={deleteName} onChange={(event) => setDeleteName(event.target.value)} autoComplete="off" required /></Field>
          <ErrorBox error={action.error} />
          <div className="form-footer"><button type="button" onClick={() => setDeleteStep(0)}>Cancel</button><button className="pilot-delete" disabled={deleteName !== details.name || action.isPending}>Delete pilot</button></div>
        </form>}
      </Modal>}
    </>
  );
}
