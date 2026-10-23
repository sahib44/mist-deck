import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Plus,
  Download,
  Bookmark,
  Send,
  SlidersHorizontal,
} from "lucide-react";
import { useData, useAction, api, Page, Row, can, label, date } from "./api";
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
  Modal,
  Back,
  JsonDetails,
} from "./ui";
export const statuses = [
  "prospective",
  "contacted",
  "interested",
  "confirmed",
  "declined",
  "inactive",
];
export function CatalogSelect({
  kind,
  value,
  onChange,
  caption,
  empty = "All",
}: {
  kind: string;
  value: string;
  onChange: (v: string) => void;
  caption: string;
  empty?: string;
}) {
  const query = useData<Page>("/catalogs/" + kind + "?page_size=100");
  return (
    <Field label={caption}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{empty}</option>
        {query.data?.items.map((r) => (
          <option value={r.name} key={r.id}>
            {r.name}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function Judges() {
  const user = useUser();
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/judges?" + params);
  const action = useAction();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>([]);
  const [columns, setColumns] = useState([
    "organization",
    "qualifications",
    "categories",
    "status",
  ]);
  const [showCols, setShowCols] = useState(false);
  const [modal, setModal] = useState("");
  const [name, setName] = useState("");
  const [bulkStatus, setBulkStatus] = useState("");
  const [bulkCategory, setBulkCategory] = useState("");
  const [bulkQualification, setBulkQualification] = useState("");
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  function filter(key: string, value: string) {
    params.delete("page");
    value ? params.set(key, value) : params.delete(key);
    setParams(params);
    setSelected([]);
  }
  const editable = can(user, "judges");
  return (
    <>
      <Heading
        eyebrow="RELATIONSHIPS / JUDGES"
        title="Judge directory"
        description="Find the right experience. Build the right connections."
      >
        {can(user, "imports") && (
          <Link className="button" to="/imports/new">
            Import CSV
          </Link>
        )}
        {editable && (
          <button className="primary" onClick={() => setModal("create")}>
            <Plus size={16} /> Add judge
          </button>
        )}
      </Heading>
      <div className="directory-summary">
        <strong>{query.data?.total ?? "—"}</strong> contacts in this view{" "}
        <span>•</span> Dynamic results from your current filters
      </div>
      <section className="filter-panel">
        <div className="filter-row">
          <Field label="Search contacts">
            <input
              placeholder="Name, email, organization, title…"
              value={params.get("q") || ""}
              onChange={(e) => filter("q", e.target.value)}
            />
          </Field>
          <CatalogSelect
            kind="qualifications"
            caption="Qualification"
            value={params.get("qualification") || ""}
            onChange={(v) => filter("qualification", v)}
          />
          <CatalogSelect
            kind="categories"
            caption="Category"
            value={params.get("category") || ""}
            onChange={(v) => filter("category", v)}
          />
          <Field label="Status">
            <select
              value={params.get("status") || ""}
              onChange={(e) => filter("status", e.target.value)}
            >
              <option value="">All statuses</option>
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <details>
          <summary>More filters</summary>
          <div className="filter-row">
            <Field label="Prior year">
              <input
                type="number"
                min="1900"
                max="2200"
                value={params.get("year") || ""}
                onChange={(e) => filter("year", e.target.value)}
              />
            </Field>
            <Field label="Prior outcome">
              <select
                value={params.get("outcome") || ""}
                onChange={(e) => filter("outcome", e.target.value)}
              >
                <option value="">All outcomes</option>
                {[
                  "invited",
                  "responded",
                  "confirmed",
                  "served",
                  "declined",
                  "no_response",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Contact preference">
              <select
                value={params.get("do_not_contact") || ""}
                onChange={(e) => filter("do_not_contact", e.target.value)}
              >
                <option value="">All contacts</option>
                <option value="false">Can contact</option>
                <option value="true">Do not contact</option>
              </select>
            </Field>
            <Field label="Not contacted since year">
              <input
                type="number"
                value={params.get("not_contacted_year") || ""}
                onChange={(e) => filter("not_contacted_year", e.target.value)}
              />
            </Field>
          </div>
        </details>
      </section>
      <div className="toolbar">
        <span>
          {selected.length
            ? `${selected.length} selected`
            : "All matching contacts"}
        </span>
        <div className="actions">
          {editable && (
            <button onClick={() => setModal("save")}>
              <Bookmark size={15} /> Save list
            </button>
          )}
          <button onClick={() => setShowCols(!showCols)}>
            <SlidersHorizontal size={15} /> Columns
          </button>
          <select
            aria-label="Sort judges"
            value={params.get("sort") || "name"}
            onChange={(e) => filter("sort", e.target.value)}
          >
            <option value="name">Name A–Z</option>
            <option value="organization">Organization</option>
            <option value="last_contacted">Last contacted</option>
            <option value="years">Years served</option>
          </select>
        </div>
      </div>
      {showCols && (
        <div className="column-options">
          {[
            "organization",
            "job_title",
            "qualifications",
            "categories",
            "status",
            "last_contacted_at",
            "years",
          ].map((c) => (
            <label className="check" key={c}>
              <input
                type="checkbox"
                checked={columns.includes(c)}
                onChange={(e) =>
                  setColumns(
                    e.target.checked
                      ? [...columns, c]
                      : columns.filter((x) => x !== c),
                  )
                }
              />
              {label(c)}
            </label>
          ))}
        </div>
      )}
      {selected.length > 0 && (
        <div className="selection-bar">
          <strong>{selected.length} contacts selected</strong>
          {editable && (
            <>
              <button onClick={() => setModal("bulk")}>Bulk update</button>
              <button
                onClick={() =>
                  navigate("/campaigns/new", { state: { judge_ids: selected } })
                }
              >
                <Send size={15} /> Create campaign
              </button>
            </>
          )}
          <button
            onClick={async () => {
              try {
                const r = await fetch("/api/judges/export", {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/json",
                    "X-MIST-Request": "1",
                  },
                  body: JSON.stringify({ ids: selected, confirmed: true }),
                });
                if (!r.ok) throw new Error("Export failed");
                const url = URL.createObjectURL(await r.blob());
                const a = document.createElement("a");
                a.href = url;
                a.download = "judges.csv";
                a.click();
                URL.revokeObjectURL(url);
              } catch (e) {
                setError(e);
              }
            }}
          >
            <Download size={15} /> Export CSV
          </button>
        </div>
      )}
      {notice && (
        <div role="status" className="notice">
          {notice}
        </div>
      )}
      <ErrorBox error={query.error || error} />
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
                    aria-label="Select this page"
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
                <th>Judge</th>
                {columns.map((c) => (
                  <th key={c}>{label(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((j) => (
                <tr key={j.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={"Select " + j.display_name}
                      checked={selected.includes(j.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, j.id]
                            : selected.filter((x) => x !== j.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <Link className="contact-name" to={"/judges/" + j.id}>
                      <span className="avatar">
                        {j.first_name?.[0]}
                        {j.last_name?.[0]}
                      </span>
                      <span>
                        <strong>{j.display_name}</strong>
                        <small>
                          {j.primary_email || "No email"}{" "}
                          {j.do_not_contact && "· Do not contact"}
                        </small>
                      </span>
                    </Link>
                  </td>
                  {columns.map((c) => (
                    <td key={c}>
                      {c === "status" ? (
                        <Badge value={j[c]} />
                      ) : Array.isArray(j[c]) ? (
                        <div className="tags">
                          {j[c].map((x: string) => (
                            <span key={x}>{x}</span>
                          ))}
                        </div>
                      ) : c === "last_contacted_at" ? (
                        date(j[c])
                      ) : (
                        j[c] || "—"
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && (
            <Empty>
              No contacts match. Adjust your filters or import a CSV.
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
      {modal === "create" && (
        <Modal title="Add judge" onClose={() => setModal("")}>
          <JudgeForm
            onSaved={(r) => {
              setModal("");
              navigate("/judges/" + r.id);
            }}
          />
        </Modal>
      )}
      {modal === "save" && (
        <Modal title="Save dynamic list" onClose={() => setModal("")}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                const filters = Object.fromEntries(params);
                delete filters.page;
                await action.mutateAsync({
                  path: "/saved-lists",
                  body: { name, filter_definition: filters },
                });
                setModal("");
                setNotice(
                  "Dynamic list saved. It will reflect future contact changes.",
                );
              } catch {}
            }}
          >
            <Field label="List name">
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <p>Stores your current filters, so the list stays up to date.</p>
            <ErrorBox error={action.error} />
            <button className="primary">Save dynamic list</button>
          </form>
        </Modal>
      )}
      {modal === "bulk" && (
        <Modal
          title={`Update ${selected.length} contacts`}
          onClose={() => setModal("")}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!confirm("Apply these changes to all selected contacts?"))
                return;
              try {
                await action.mutateAsync({
                  path: "/judges/bulk",
                  body: {
                    ids: selected,
                    confirmed: true,
                    status: bulkStatus || null,
                    category: bulkCategory || null,
                    qualification: bulkQualification || null,
                  },
                });
                setModal("");
                setNotice("Selected contacts updated.");
              } catch {}
            }}
          >
            <Field label="Set status">
              <select
                value={bulkStatus}
                onChange={(e) => setBulkStatus(e.target.value)}
              >
                <option value="">Leave unchanged</option>
                {statuses.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <CatalogSelect
              kind="categories"
              caption="Add category"
              value={bulkCategory}
              onChange={setBulkCategory}
              empty="Leave unchanged"
            />
            <CatalogSelect
              kind="qualifications"
              caption="Add qualification"
              value={bulkQualification}
              onChange={setBulkQualification}
              empty="Leave unchanged"
            />
            <ErrorBox error={action.error} />
            <button className="primary">Confirm bulk update</button>
          </form>
        </Modal>
      )}
    </>
  );
}
export function JudgeForm({
  judge,
  onSaved,
}: {
  judge?: Row;
  onSaved: (r: Row) => void;
}) {
  const action = useAction();
  const [error, setError] = useState<unknown>();
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        const body: Record<string, unknown> = {};
        for (const key of [
          "first_name",
          "last_name",
          "display_name",
          "primary_email",
          "alternate_email",
          "organization",
          "job_title",
          "phone",
          "status",
          "notes",
        ])
          body[key] = fd.get(key) || "";
        body.do_not_contact = fd.get("do_not_contact") === "on";
        for (const key of ["qualifications", "categories", "years"])
          body[key] = String(fd.get(key) || "")
            .split(";")
            .map((x) => x.trim())
            .filter(Boolean)
            .map((x) => (key === "years" ? Number(x) : x));
        try {
          onSaved(
            await action.mutateAsync({
              path: "/judges" + (judge ? "/" + judge.id : ""),
              method: judge ? "PATCH" : "POST",
              body,
            }),
          );
        } catch (e) {
          setError(e);
        }
      }}
    >
      <div className="form-grid">
        {[
          "first_name",
          "last_name",
          "display_name",
          "primary_email",
          "alternate_email",
          "organization",
          "job_title",
          "phone",
        ].map((k) => (
          <Field key={k} label={label(k)}>
            <input
              name={k}
              required={k === "display_name"}
              defaultValue={judge?.[k] || ""}
              type={k.includes("email") ? "email" : "text"}
            />
          </Field>
        ))}
        <Field label="Status">
          <select name="status" defaultValue={judge?.status || "prospective"}>
            {statuses.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
        {["qualifications", "categories", "years"].map((k) => (
          <Field key={k} label={label(k) + " (separate with ;)"}>
            <input name={k} defaultValue={judge?.[k]?.join("; ") || ""} />
          </Field>
        ))}
      </div>
      <Field label="Notes">
        <textarea name="notes" rows={4} defaultValue={judge?.notes || ""} />
      </Field>
      <label className="check">
        <input
          name="do_not_contact"
          type="checkbox"
          defaultChecked={judge?.do_not_contact}
        />
        Do not contact
      </label>
      <ErrorBox error={error} />
      <button className="primary" disabled={action.isPending}>
        Save judge
      </button>
    </form>
  );
}
export function JudgeDetail() {
  const { id } = useParams();
  const query = useData<Row>("/judges/" + id);
  const [tab, setTab] = useState("engagements");
  const [page, setPage] = useState(1);
  const history = useData<Page>(
    tab === "audit"
      ? `/judges/${id}/audit?page=${page}`
      : `/judges/${id}/history?kind=${tab}&page=${page}`,
  );
  const [editing, setEditing] = useState(false);
  const user = useUser();
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorBox error={query.error} />;
  const j = query.data;
  return (
    <>
      <Back to="/judges">Judge directory</Back>
      <Heading
        title={j.display_name}
        description={`${j.job_title || "Judge contact"}${j.organization ? " · " + j.organization : ""}`}
      >
        <Badge value={j.status} />
        {can(user, "judges") && (
          <button className="primary" onClick={() => setEditing(true)}>
            Edit contact
          </button>
        )}
      </Heading>
      <div className="two-col">
        <Panel title="Contact information">
          <dl>
            {[
              "primary_email",
              "alternate_email",
              "preserved_emails",
              "organization",
              "phone",
              "source",
            ].map((k) => (
              <div key={k}>
                <dt>{label(k)}</dt>
                <dd>{Array.isArray(j[k]) ? j[k].join(", ") : j[k] || "—"}</dd>
              </div>
            ))}
          </dl>
          {j.do_not_contact && (
            <div className="warning">
              Do not contact · excluded from outreach
            </div>
          )}
        </Panel>
        <Panel title="Experience & qualifications">
          <h3>Qualifications</h3>
          <div className="tags">
            {j.qualifications.map((v: string) => (
              <span key={v}>{v}</span>
            ))}
          </div>
          <h3>Eligible categories</h3>
          <div className="tags">
            {j.categories.map((v: string) => (
              <span key={v}>{v}</span>
            ))}
          </div>
          <h3>Notes</h3>
          <p className="message-body">{j.notes || "No notes yet."}</p>
        </Panel>
      </div>
      <div className="tabs">
        {[
          "engagements",
          "messages",
          "imports",
          "merges",
          ...(can(user, "judges") ? ["audit"] : []),
        ].map((t) => (
          <button
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => {
              setTab(t);
              setPage(1);
            }}
          >
            {label(t)}
          </button>
        ))}
      </div>
      <ErrorBox error={history.error} />
      {history.isPending ? (
        <Loading />
      ) : (
        <Panel title={label(tab)}>
          {history.data?.items.length ? (
            history.data.items.map((r) => (
              <details className="history-entry" key={r.id}>
                <summary>
                  {r.summary ||
                    r.subject ||
                    (r.event_year && `${r.event_year} · ${label(r.outcome)}`) ||
                    (r.row_number && `Import row ${r.row_number}`) ||
                    "Merge record"}{" "}
                  <small>{date(r.created_at)}</small>
                </summary>
                <JsonDetails data={r} />
              </details>
            ))
          ) : (
            <Empty />
          )}
          <Pagination data={history.data} onPage={setPage} />
        </Panel>
      )}
      {editing && (
        <Modal title="Edit judge contact" onClose={() => setEditing(false)}>
          <JudgeForm judge={j} onSaved={() => setEditing(false)} />
        </Modal>
      )}
    </>
  );
}
export function SavedLists() {
  const [page, setPage] = useState(1);
  const query = useData<Page>("/saved-lists?page=" + page);
  return (
    <>
      <Heading
        title="Saved lists"
        description="Reusable filters that stay current as your judge directory changes."
      >
        <Link className="button primary" to="/judges">
          Create from directory
        </Link>
      </Heading>
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="saved-list-grid">
          {query.data?.items.map((r) => (
            <Panel title={r.name} key={r.id}>
              <p>{r.description || "Dynamic judge list"}</p>
              <div className="tags">
                {Object.entries(r.filter_definition).map(([k, v]) => (
                  <span key={k}>
                    {label(k)}: {String(v)}
                  </span>
                ))}
              </div>
              <div className="actions">
                <Link
                  className="button"
                  to={"/judges?" + new URLSearchParams(r.filter_definition)}
                >
                  View contacts
                </Link>
                <Link
                  className="button primary"
                  to={"/campaigns/new?list=" + r.id}
                >
                  Create campaign
                </Link>
              </div>
            </Panel>
          ))}
        </div>
      )}
      {query.data?.total === 0 && (
        <Empty>
          Save a filtered view from the judge directory to create your first
          list.
        </Empty>
      )}
      <Pagination data={query.data} onPage={setPage} />
    </>
  );
}
