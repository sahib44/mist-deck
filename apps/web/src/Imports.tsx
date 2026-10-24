import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { Upload, ArrowRight, Check, FileText } from "lucide-react";
import { useData, useAction, Page, Row, label, date } from "./api";
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
} from "./ui";
export const importFields = [
  "first_name",
  "last_name",
  "display_name",
  "primary_email",
  "alternate_email",
  "organization",
  "job_title",
  "phone",
  "qualifications",
  "categories",
  "years",
  "status",
  "do_not_contact",
  "notes",
];
export function validateMapping(mapping: Record<string, string>) {
  const used = Object.values(mapping).filter(Boolean);
  if (new Set(used).size !== used.length)
    return "Each CSV column can only be mapped once.";
  if (
    !["primary_email", "display_name", "first_name", "last_name"].some(
      (k) => mapping[k],
    )
  )
    return "Map at least one name or email field.";
  return "";
}
export function ImportSteps({ step }: { step: number }) {
  return (
    <ol className="steps">
      {["Upload CSV", "Map columns", "Analyze & review", "Commit import"].map(
        (s, i) => (
          <li
            key={s}
            className={
              step === i + 1 ? "current" : step > i + 1 ? "complete" : ""
            }
          >
            <span>{step > i + 1 ? <Check size={16} /> : i + 1}</span>
            {s}
          </li>
        ),
      )}
    </ol>
  );
}
export function Imports() {
  const [page, setPage] = useState(1);
  const query = useData<Page>("/imports?page=" + page);
  return (
    <>
      <Heading
        title="Imports"
        description="Bring historical judge records into one shared directory."
      >
        <Link className="button primary" to="/imports/new">
          <Upload size={16} /> Import CSV
        </Link>
      </Heading>
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Rows</th>
                <th>Created / Updated / Skipped</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={"/imports/" + r.id}>
                      <FileText size={16} /> {r.filename}
                    </Link>
                  </td>
                  <td>
                    <Badge value={r.status} />
                  </td>
                  <td>{r.total_rows}</td>
                  <td>
                    {r.created_count} / {r.updated_count} / {r.skipped_count}
                  </td>
                  <td>{date(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && (
            <Empty>Upload your first CSV to get started.</Empty>
          )}
          <Pagination data={query.data} onPage={setPage} />
        </div>
      )}
    </>
  );
}
export function ImportWizard() {
  const { id } = useParams();
  const navigate = useNavigate();
  const batch = useData<Row>("/imports/" + id, !!id);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>();
  const [reviewed, setReviewed] = useState(false);
  const [page, setPage] = useState(1);
  const [resolution, setResolution] = useState("");
  const action = useAction();
  const rows = useData<Page>(
    `/imports/${id}/rows?page=${page}&resolution=${resolution}`,
    !!id && ["analyzed", "committed"].includes(batch.data?.status),
  );
  const [showCommit, setShowCommit] = useState(false);
  useEffect(() => {
    if (batch.data) setMapping(batch.data.mapping);
  }, [batch.data?.id]);
  const status = batch.data?.status;
  const step = !id
    ? 1
    : ["uploaded", "mapped"].includes(status)
      ? 2
      : status === "committed" || showCommit
        ? 4
        : 3;
  async function run(path: string, body?: unknown, method = "POST") {
    setError(undefined);
    try {
      return await action.mutateAsync({ path, body, method });
    } catch (e) {
      setError(e);
      return null;
    }
  }
  return (
    <>
      <Back to="/imports">All imports</Back>
      <Heading
        title={
          status === "committed" ? "Import complete" : "Import judge records"
        }
        description="Upload, map, review, then bring verified records into your directory."
      />
      <ImportSteps step={step} />
      <ErrorBox error={error || batch.error} />
      {id && batch.isPending ? (
        <Loading />
      ) : step === 1 ? (
        <Panel title="Upload a CSV file">
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!file) return;
              const fd = new FormData();
              fd.append("file", file);
              const result = await run("/imports", fd);
              if (result) navigate("/imports/" + result.id);
            }}
          >
            <div className="upload-zone">
              <Upload size={32} />
              <h3>Choose your judge CSV</h3>
              <p>
                UTF-8 · comma, semicolon, or tab separated · default limit 2 MB
                / 5,000 rows
              </p>
              <input
                aria-label="CSV file"
                type="file"
                accept=".csv"
                required
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>
            <div className="form-footer">
              <span>
                Contact records stay in the local database. Email delivery stays in the sandbox.
              </span>
              <button className="primary" disabled={!file || action.isPending}>
                Upload and continue <ArrowRight size={16} />
              </button>
            </div>
          </form>
        </Panel>
      ) : step === 2 ? (
        <Panel title="Match CSV columns to contact fields">
          <div className="summary-strip">
            <strong>{batch.data?.filename}</strong>
            <span>{batch.data?.total_rows} rows</span>
            <span>{batch.data?.metadata_json.size} bytes</span>
            <span>{batch.data?.metadata_json.encoding}</span>
            <span>
              Delimiter: {JSON.stringify(batch.data?.metadata_json.delimiter)}
            </span>
          </div>
          <p>
            Review the automatic matches. Leave fields unmapped to ignore those
            columns.
          </p>
          <div className="mapping-grid">
            {importFields.map((field) => (
              <Field key={field} label={label(field)}>
                <select
                  value={mapping[field] || ""}
                  onChange={(e) =>
                    setMapping({ ...mapping, [field]: e.target.value })
                  }
                >
                  <option value="">Ignore / not mapped</option>
                  {batch.data?.metadata_json.headers.map((h: string) => (
                    <option key={h}>{h}</option>
                  ))}
                </select>
              </Field>
            ))}
          </div>
          <div className="form-footer">
            <span>Original rows are preserved for audit.</span>
            <button
              className="primary"
              disabled={action.isPending}
              onClick={async () => {
                const validation = validateMapping(mapping);
                if (validation) {
                  setError(validation);
                  return;
                }
                if (
                  await run("/imports/" + id + "/mapping", { mapping }, "PUT")
                )
                  await run("/imports/" + id + "/analyze");
              }}
            >
              Analyze rows <ArrowRight size={16} />
            </button>
          </div>
        </Panel>
      ) : step === 3 ? (
        <>
          <div className="count-strip">
            {Object.entries(batch.data?.counts || {}).map(([key, value]) => (
              <button
                key={key}
                className={resolution === key ? "active" : ""}
                onClick={() => {
                  setResolution(resolution === key ? "" : key);
                  setPage(1);
                }}
              >
                <strong>{String(value)}</strong>
                {label(key)}
              </button>
            ))}
          </div>
          <div className="review-callout">
            <div>
              <h3>Review duplicate matches before importing</h3>
              <p>
                Exact emails and supported name matches need your decision.
                Name-only suggestions never merge automatically.
              </p>
            </div>
            <Link className="button" to={"/duplicates?batch_id=" + id}>
              Review duplicates
            </Link>
          </div>
          <Panel
            title="Row analysis"
            action={
              <select
                aria-label="Filter row classification"
                value={resolution}
                onChange={(e) => {
                  setResolution(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All rows</option>
                {[
                  "create",
                  "update",
                  "duplicate_review",
                  "invalid",
                  "skip",
                ].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            }
          >
            {rows.isPending ? (
              <Loading />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Judge</th>
                      <th>Email</th>
                      <th>Decision</th>
                      <th>Validation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.data?.items.map((r) => (
                      <tr key={r.id}>
                        <td>{r.row_number}</td>
                        <td>{r.normalized_data.display_name || "—"}</td>
                        <td>{r.normalized_data.primary_email || "—"}</td>
                        <td>
                          <Badge value={r.resolution} />
                        </td>
                        <td>{r.validation_errors.join("; ") || "Valid"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination data={rows.data} onPage={setPage} />
              </div>
            )}
            <div className="form-footer">
              <a href={"/api/imports/" + id + "/errors"}>Download error CSV</a>
              <button
                className="primary"
                disabled={!!batch.data?.counts?.duplicate_review}
                onClick={() => setShowCommit(true)}
              >
                Continue to commit <ArrowRight size={16} />
              </button>
            </div>
          </Panel>
        </>
      ) : status === "committed" ? (
        <Panel title="Import results">
          <div className="count-strip">
            {["created_count", "updated_count", "skipped_count"].map((k) => (
              <div key={k}>
                <strong>{batch.data?.[k]}</strong>
                {label(k)}
              </div>
            ))}
          </div>
          <p>
            Completed {date(batch.data?.completed_at)}. Original data and merge
            decisions are preserved in the audit trail.
          </p>
          <div className="actions">
            <Link className="button primary" to="/judges">
              View judge directory
            </Link>
            <a className="button" href={"/api/imports/" + id + "/errors"}>
              Download error CSV
            </a>
          </div>
        </Panel>
      ) : (
        <Panel title="Confirm import">
          <p>
            Ready to create {batch.data?.counts?.create || 0} contacts and
            update {batch.data?.counts?.update || 0}. Invalid and skipped rows
            will be retained without modifying contacts.
          </p>
          <label className="check">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I reviewed the analysis and approve these changes.
          </label>
          <div className="form-footer">
            <button onClick={() => setShowCommit(false)}>
              Back to analysis
            </button>
            <button
              className="primary"
              disabled={!reviewed || action.isPending}
              onClick={() =>
                run("/imports/" + id + "/commit", { confirmed: true })
              }
            >
              Commit import
            </button>
          </div>
        </Panel>
      )}
    </>
  );
}
export function Duplicates() {
  const [params, setParams] = useSearchParams();
  const query = useData<Page>("/duplicates?" + params);
  return (
    <>
      <Heading
        title="Duplicate review"
        description="Review the evidence. Choose what belongs together."
      />
      {params.get("batch_id") && (
        <Back to={"/imports/" + params.get("batch_id")}>Return to import</Back>
      )}
      <ErrorBox error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Match</th>
                <th>Why it was flagged</th>
                <th>Confidence</th>
                <th>Decision</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {query.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{label(r.match_type)}</strong>
                  </td>
                  <td>{r.explanation}</td>
                  <td>{Math.round(r.confidence_score * 100)}%</td>
                  <td>
                    <Badge value={r.resolution} />
                  </td>
                  <td>
                    <Link className="button" to={"/duplicates/" + r.id}>
                      Review match
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data?.total === 0 && (
            <Empty>No pending duplicate matches in this view.</Empty>
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
export function MergeFields({
  existing,
  incoming,
  decisions,
  onChange,
}: {
  existing: Row | Record<string, any>;
  incoming: Record<string, any>;
  decisions: Record<string, string>;
  onChange: (d: Record<string, string>) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="merge-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Existing value</th>
            <th>Incoming value</th>
            <th>Keep</th>
          </tr>
        </thead>
        <tbody>
          {importFields
            .filter(
              (k) =>
                !["qualifications", "categories", "years", "notes"].includes(k),
            )
            .map((k) => (
              <tr key={k}>
                <th>{label(k)}</th>
                <td>{String(existing[k] ?? "—")}</td>
                <td>{String(incoming[k] ?? "—")}</td>
                <td>
                  {k === "do_not_contact" ? (
                    <span>Preserve suppression</span>
                  ) : (
                    <select
                      aria-label={"Keep " + label(k)}
                      value={decisions[k] || "existing"}
                      onChange={(e) =>
                        onChange({ ...decisions, [k]: e.target.value })
                      }
                    >
                      <option value="existing">Existing</option>
                      <option value="incoming">Incoming</option>
                    </select>
                  )}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
export function DuplicateDetail() {
  const { id } = useParams();
  const query = useData<Row>("/duplicates/" + id);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState(false);
  const [decision, setDecision] = useState("merge");
  const action = useAction();
  const navigate = useNavigate();
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorBox error={query.error} />;
  const d = query.data;
  return (
    <>
      <Back to={"/duplicates?batch_id=" + d.batch_id}>Duplicate review</Back>
      <Heading
        title="Compare & resolve"
        description={`Import row ${d.row_number} · ${d.explanation}`}
      />
      <div className="review-callout">
        <div>
          <strong>
            {label(d.match_type)} · {Math.round(d.confidence_score * 100)}%
            confidence
          </strong>
          <p>
            {d.confidence_score < 0.7
              ? "A similar name alone does not establish identity. Keep separate unless you have supporting evidence."
              : "Select the surviving field values. Merges take effect when the import is committed."}
          </p>
        </div>
      </div>
      <MergeFields
        existing={d.existing}
        incoming={d.incoming}
        decisions={decisions}
        onChange={setDecisions}
      />
      <Panel title="Data preserved during merge">
        <div className="two-col">
          {["qualifications", "categories", "years", "notes"].map((k) => (
            <div key={k}>
              <h3>{label(k)}</h3>
              <p className="message-body">
                Existing:{" "}
                {Array.isArray(d.existing[k])
                  ? d.existing[k].join(", ")
                  : d.existing[k] || "—"}
              </p>
              <p className="message-body">
                Incoming:{" "}
                {Array.isArray(d.incoming[k])
                  ? d.incoming[k].join(", ")
                  : d.incoming[k] || "—"}
              </p>
            </div>
          ))}
        </div>
        <p>
          Unique qualifications, categories, notes, and history are combined.
          Additional email addresses and all original scalar values remain in
          the merge record.
        </p>
      </Panel>
      <Panel title="Your decision">
        <Field label="Resolution">
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
          >
            <option value="merge">Merge into existing contact</option>
            <option value="create">Keep as a separate contact</option>
            <option value="skip">Skip incoming row</option>
          </select>
        </Field>
        <label className="check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I reviewed the matching evidence and field selections.
        </label>
        <ErrorBox error={action.error} />
        <button
          className="primary"
          disabled={!confirmed || action.isPending}
          onClick={async () => {
            try {
              await action.mutateAsync({
                path: "/duplicates/" + id + "/resolve",
                body: { decision, field_decisions: decisions, confirmed: true },
              });
              navigate("/duplicates?batch_id=" + d.batch_id);
            } catch {}
          }}
        >
          Confirm resolution
        </button>
      </Panel>
    </>
  );
}
