import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Download, Mail, Plus, Trash2 } from "lucide-react";
import { api, useAction, useData, Page, Row, can, label, date } from "./api";
import { useUser } from "./App";
import { UnreadMarker } from "./Inbox";
import { Badge, Empty, ErrorBox, Field, Heading, Loading, Modal, Pagination } from "./ui";

type Category = { slug: string; name: string };
const statuses = ["to_contact", "awaiting_response", "accepted", "declined"];
async function downloadSheet(path: string, filename: string) {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) throw new Error("The judge sheet could not be exported.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function JudgeDirectory() {
  const [params, setParams] = useSearchParams();
  const user = useUser();
  const navigate = useNavigate();
  const action = useAction();
  const query = useData<Page>("/judge-directory?" + params);
  const categories = useData<Category[]>("/competitions/categories");
  const competitions = useData<Page>(`/competitions?category_slug=${params.get("category_slug") || ""}&page_size=100`);
  const [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<Row | null>(null);
  const [adding, setAdding] = useState(false);
  const [clearStep, setClearStep] = useState(0);
  const [password, setPassword] = useState("");
  const [backup, setBackup] = useState<Row | null>(null);
  const [cleared, setCleared] = useState<Row | null>(null);
  const [clearing, setClearing] = useState(false);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params); next.delete("page"); setSelected([]);
    if (key === "category_slug") next.delete("competition_id");
    value ? next.set(key, value) : next.delete(key); setParams(next);
  }
  async function download() {
    try { const exportParams = new URLSearchParams(params); exportParams.delete("page"); await downloadSheet("/api/judge-directory/export?" + exportParams, "mist-deck-judges.csv"); } catch (cause) { setError(cause); }
  }
  const visibleIds = [...new Set((query.data?.items || []).map(row => row.judge_id as string))];
  return <>
    <Heading title="Judge directory">
      <button onClick={() => { setEditing(null); setAdding(true); }}><Plus size={16} /> Add judge</button>
      <button className="primary" onClick={download}><Download size={16} /> Export sheet</button>
      {can(user, "delete") && <button className="pilot-delete" onClick={() => { setClearStep(1); setBackup(null); setPassword(""); setError(undefined); }}><Trash2 size={16} /> Clear all judges</button>}
    </Heading>
    <div className="directory-summary"><strong>{query.data?.total ?? "—"}</strong> competition assignments and unassigned contacts</div>
    {cleared && <div className="notice" role="status">All {cleared.cleared} judges were cleared. <a href={cleared.backup_url}>Download the saved backup</a></div>}
    <section className="filter-panel"><div className="filter-row">
      <Field label="Search"><input value={params.get("q") || ""} onChange={e => filter("q", e.target.value)} placeholder="Name, email, phone, competition…" /></Field>
      <Field label="Main category"><select value={params.get("category_slug") || ""} onChange={e => filter("category_slug", e.target.value)}><option value="">All categories</option>{categories.data?.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></Field>
      <Field label="Competition"><select value={params.get("competition_id") || ""} onChange={e => filter("competition_id", e.target.value)}><option value="">All competitions</option>{competitions.data?.items.map((c: Row) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
      <Field label="Response"><select value={params.get("status") || ""} onChange={e => filter("status", e.target.value)}><option value="">All responses</option>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select></Field>
    </div></section>
    {!!selected.length && <div className="selection-bar"><strong>{selected.length} judges selected</strong><button onClick={() => navigate("/campaigns/new", { state: { judge_ids: selected } })}><Mail size={16} /> Email selected</button><button onClick={() => setSelected([])}>Clear selection</button></div>}
    <ErrorBox error={query.error || error || action.error} />
    {query.isPending ? <Loading /> : <div className="table-wrap"><table><thead><tr><th><input aria-label="Select visible judges" type="checkbox" checked={!!visibleIds.length && visibleIds.every(id => selected.includes(id))} onChange={event => setSelected(event.target.checked ? visibleIds : [])} /></th><th>Response</th><th>Name</th><th>Contact</th><th>Competition</th><th>Qualification</th><th>Added</th><th /></tr></thead><tbody>
      {query.data?.items.map((row: Row) => <tr key={row.id}><td><input type="checkbox" aria-label={`Select ${row.name}`} checked={selected.includes(row.judge_id)} onChange={event => setSelected(event.target.checked ? [...selected, row.judge_id] : selected.filter(id => id !== row.judge_id))} /></td><td><select aria-label={`Response for ${row.name}`} value={row.status} onChange={event => action.mutate({ path: row.competition_id ? `/competitions/${row.competition_id}/judges/${row.id}` : `/judge-directory/${row.judge_id}/status`, method: "PATCH", body: { status: event.target.value } })}>{statuses.map(status => <option value={status} key={status}>{label(status)}</option>)}</select></td><td><Link to={`/campaigns/conversations/judges/${row.judge_id}`}>{row.name}</Link> <UnreadMarker count={row.unread_count} /></td><td>{row.email || "—"}{row.phone && <small>{row.phone}</small>}</td><td>{row.competition_id ? <Link to={`/competitions/${row.category_slug}/${row.competition_id}`}>{row.competition}</Link> : "Unassigned"}<small>{row.category !== "Unassigned" ? row.category : ""}</small></td><td className="directory-qualification">{row.qualification || "—"}</td><td>{date(row.added_at)}</td><td><button onClick={async () => { try { setEditing(await api(`/judges/${row.judge_id}`)); setAdding(true); } catch (cause) { setError(cause); } }}>Edit</button></td></tr>)}
    </tbody></table>{query.data?.total === 0 && <Empty>No judges match these filters.</Empty>}<Pagination data={query.data} onPage={page => filter("page", String(page))} /></div>}
    {adding && <Modal title={editing ? "Edit judge" : "Add judge"} onClose={() => setAdding(false)}><form onSubmit={async event => {
      event.preventDefault(); const fd = new FormData(event.currentTarget); const name = String(fd.get("name") || "").trim(); const email = String(fd.get("email") || "").trim(); const phone = String(fd.get("phone") || "").trim();
      if (!email && !phone) { setError("Enter an email address or phone number."); return; }
      try { await action.mutateAsync({ path: editing ? `/judges/${editing.id}` : "/judges", method: editing ? "PATCH" : "POST", body: { display_name: name, first_name: name.split(" ")[0], last_name: name.split(" ").slice(1).join(" "), primary_email: email, phone, notes: fd.get("qualification"), alternate_email: editing?.alternate_email || "", organization: editing?.organization || "", job_title: editing?.job_title || "", status: editing?.status || "to_contact", do_not_contact: editing?.do_not_contact || false, categories: editing?.categories || [], qualifications: editing?.qualifications || [], years: editing?.years || [] } }); setAdding(false); setError(undefined); } catch {}
    }}>
      <Field label="Name"><input name="name" required maxLength={400} defaultValue={editing?.display_name || ""} /></Field><Field label="Email"><input name="email" type="email" defaultValue={editing?.primary_email || ""} /></Field><Field label="Phone"><input name="phone" type="tel" defaultValue={editing?.phone || ""} /></Field><Field label="Why this judge is qualified (optional)"><textarea name="qualification" defaultValue={editing?.notes || ""} /></Field>
      <ErrorBox error={action.error || error} /><button className="primary" disabled={action.isPending}>Save judge</button>
    </form></Modal>}
    {clearStep > 0 && <Modal title="Clear all judges" onClose={() => { if (!clearing) { setClearStep(0); setPassword(""); } }}>
      {clearStep === 1 && <><p>Are you sure you want to clear every judge from the directory and every competition?</p><div className="form-footer"><button onClick={() => setClearStep(0)}>Cancel</button><button className="pilot-delete" onClick={() => setClearStep(2)}>Yes, continue</button></div></>}
      {clearStep === 2 && <><p>Are you really sure? A sheet backup will be saved and downloaded before deletion. Competition definitions and email history will remain.</p><div className="form-footer"><button disabled={clearing} onClick={() => setClearStep(0)}>Cancel</button><button className="pilot-delete" disabled={clearing} onClick={async () => { setClearing(true); try { const saved = await action.mutateAsync({ path: "/judge-directory/clear/prepare" }); await downloadSheet(saved.download_url, "mist-deck-judges-backup.csv"); setBackup(saved); setClearStep(3); } catch (cause) { setError(cause); } finally { setClearing(false); } }}>{clearing ? "Saving backup…" : "Save backup and continue"}</button></div></>}
      {clearStep === 3 && <form onSubmit={async event => { event.preventDefault(); if (!backup) return; setClearing(true); try { const result = await action.mutateAsync({ path: "/judge-directory/clear", body: { confirmed_first: true, confirmed_second: true, password, backup_id: backup.id } }); setCleared(result); setClearStep(0); setPassword(""); setSelected([]); } catch (cause) { setError(cause); } finally { setClearing(false); } }}><p>The sheet backup contains {backup?.judge_count} judges. Enter your signed-in account password to clear them.</p><Field label="Chair or director password"><input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></Field><div className="form-footer"><button disabled={clearing} type="button" onClick={() => { setClearStep(0); setPassword(""); }}>Cancel</button><button className="pilot-delete" disabled={clearing || !password}>Clear all judges</button></div></form>}
      <ErrorBox error={error || action.error} />
    </Modal>}
  </>;
}
