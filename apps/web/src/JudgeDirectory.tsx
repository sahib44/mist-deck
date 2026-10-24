import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Download } from "lucide-react";
import { useData, Page, Row, label, date } from "./api";
import { Badge, Empty, ErrorBox, Field, Heading, Loading, Pagination } from "./ui";

type Category = { slug: string; name: string };

export function JudgeDirectory() {
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/judge-directory?" + params);
  const categories = useData<Category[]>("/competitions/categories");
  const competitions = useData<Page>(`/competitions?category_slug=${params.get("category_slug") || ""}&page_size=100`);
  const [error, setError] = useState<unknown>();
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.delete("page");
    if (key === "category_slug") next.delete("competition_id");
    value ? next.set(key, value) : next.delete(key);
    setParams(next);
  }
  async function download() {
    try {
      const exportParams = new URLSearchParams(params);
      exportParams.delete("page");
      const response = await fetch("/api/judge-directory/export?" + exportParams, { credentials: "same-origin" });
      if (!response.ok) throw new Error("The judge sheet could not be exported.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "mist-deck-judges.csv";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) { setError(cause); }
  }
  return <>
    <Heading title="Judge directory">
      <Link className="button" to="/contacts">Contact tools</Link>
      <button className="primary" onClick={download}><Download size={16} /> Export sheet</button>
    </Heading>
    <div className="directory-summary"><strong>{query.data?.total ?? "—"}</strong> competition assignments and unassigned contacts</div>
    <section className="filter-panel"><div className="filter-row">
      <Field label="Search"><input value={params.get("q") || ""} onChange={e => filter("q", e.target.value)} placeholder="Name, email, phone, competition…" /></Field>
      <Field label="Main category"><select value={params.get("category_slug") || ""} onChange={e => filter("category_slug", e.target.value)}><option value="">All categories</option>{categories.data?.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></Field>
      <Field label="Competition"><select value={params.get("competition_id") || ""} onChange={e => filter("competition_id", e.target.value)}><option value="">All competitions</option>{competitions.data?.items.map((c: Row) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
      <Field label="Response"><select value={params.get("status") || ""} onChange={e => filter("status", e.target.value)}><option value="">All responses</option>{["to_contact", "awaiting_response", "accepted", "declined"].map(s => <option key={s} value={s}>{label(s)}</option>)}</select></Field>
    </div></section>
    <ErrorBox error={query.error || error} />
    {query.isPending ? <Loading /> : <div className="table-wrap"><table><thead><tr><th>Response</th><th>Name</th><th>Contact</th><th>Competition</th><th>Qualification</th><th>Added</th></tr></thead><tbody>
      {query.data?.items.map((row: Row) => <tr key={row.id}><td><Badge value={row.status} /></td><td><Link to={`/judges/${row.judge_id}`}>{row.name}</Link></td><td>{row.email || "—"}{row.phone && <small>{row.phone}</small>}</td><td>{row.competition_id ? <Link to={`/competitions/${row.category_slug}/${row.competition_id}`}>{row.competition}</Link> : "Unassigned"}<small>{row.category !== "Unassigned" ? row.category : ""}</small></td><td className="directory-qualification">{row.qualification || "—"}</td><td>{date(row.added_at)}</td></tr>)}
    </tbody></table>{query.data?.total === 0 && <Empty>No judges match these filters.</Empty>}<Pagination data={query.data} onPage={page => filter("page", String(page))} /></div>}
  </>;
}
