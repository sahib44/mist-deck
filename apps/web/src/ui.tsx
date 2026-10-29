import {
  ReactNode,
  ReactElement,
  cloneElement,
  isValidElement,
  useId,
  useEffect,
  useRef,
} from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowLeft, ArrowRight, X } from "lucide-react";
import { Page, label } from "./api";
export function ErrorBox({ error }: { error: unknown }) {
  return error ? (
    <div role="alert" className="error">
      <AlertCircle size={18} />
      {error instanceof Error ? error.message : String(error)}
    </div>
  ) : null;
}
export function Loading() {
  return (
    <div role="status" className="loading">
      Loading records…
    </div>
  );
}
export function Empty({
  children = "No records match this view.",
}: {
  children?: ReactNode;
}) {
  return <div className="empty">{children}</div>;
}
export function Badge({ value }: { value: string }) {
  return <span className={"badge " + value}>{label(value)}</span>;
}
export function Heading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow || "MIST NJ / OPERATIONS"}</div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="actions">{children}</div>
    </div>
  );
}
export function Field({
  label: caption,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{caption}</label>
      {isValidElement(children)
        ? cloneElement(children as ReactElement<{ id?: string }>, { id })
        : children}
    </div>
  );
}
export function Pagination({
  data,
  onPage,
}: {
  data: Page | undefined;
  onPage: (n: number) => void;
}) {
  if (!data) return null;
  return (
    <div className="pagination">
      <span>
        {data.total} records · Page {data.page} of{" "}
        {Math.max(1, Math.ceil(data.total / data.page_size))}
      </span>
      <div>
        <button
          aria-label="Previous page"
          disabled={data.page <= 1}
          onClick={() => onPage(data.page - 1)}
        >
          <ArrowLeft size={16} />
        </button>
        <button
          aria-label="Next page"
          disabled={data.page * data.page_size >= data.total}
          onClick={() => onPage(data.page + 1)}
        >
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
export function Panel({
  title,
  children,
  action,
  className = "",
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header>
        <h2>{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog ref={ref} onCancel={onClose}>
      <header>
        <h2>{title}</h2>
        <button onClick={onClose} aria-label="Close dialog">
          <X size={18} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function ConfirmButton({
  children,
  onConfirm,
  question,
  disabled = false,
}: {
  children: ReactNode;
  onConfirm: () => void;
  question: string;
  disabled?: boolean;
}) {
  return (
    <button
      disabled={disabled}
      onClick={() => {
        if (window.confirm(question)) onConfirm();
      }}
    >
      {children}
    </button>
  );
}
export function JsonDetails({ data }: { data: unknown }) {
  return <pre className="json">{JSON.stringify(data, null, 2)}</pre>;
}
export function Back({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="back" to={to}>
      <ArrowLeft size={15} />
      {children}
    </Link>
  );
}


export function HistoryBack() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const fallback = location.pathname === "/outbox" && params.get("ticket_id") ? `/tickets/${params.get("ticket_id")}` : "/dashboard";
  const hasHistory = typeof window.history.state?.idx === "number" && window.history.state.idx > 0;
  return <button type="button" className="history-back" aria-label="Go back" title="Back to the previous page" disabled={!hasHistory && location.pathname === fallback} onClick={() => hasHistory ? navigate(-1) : navigate(fallback)}><ArrowLeft size={17} /><span>Back</span></button>;
}
