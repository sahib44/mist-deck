import { useState } from "react";
import { useData, Row } from "./api";
import { Field } from "./ui";

export type EmailRecipient = { key: string; judge_id?: string; name: string; email: string; add_to_directory?: boolean };
export function RecipientChips({ recipients, onChange }: { recipients: EmailRecipient[]; onChange: (recipients: EmailRecipient[]) => void }) {
  return <div className="recipient-chips" aria-label="Selected recipients">{recipients.map(recipient => <span className="recipient-chip" key={recipient.key} title={recipient.email}>
    <span>{recipient.name || recipient.email}<small>{recipient.name && recipient.name !== recipient.email ? recipient.email : ""}</small></span>
    <button type="button" aria-label={`Remove ${recipient.name || recipient.email}`} onClick={() => onChange(recipients.filter(item => item.key !== recipient.key))}>×</button>
  </span>)}</div>;
}
export function RecipientPicker({ recipients, onChange }: { recipients: EmailRecipient[]; onChange: (recipients: EmailRecipient[]) => void }) {
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [save, setSave] = useState(false);
  const query = useData<Row[]>(`/recipient-search?q=${encodeURIComponent(search)}`, search.trim().length > 0);
  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(search.trim());
  const suggestions = (query.data || []).filter(item => !recipients.some(r => r.judge_id === item.id || r.email.toLowerCase() === item.email.toLowerCase()));
  const reset = () => { setSearch(""); setName(""); setSave(false); };
  function addEmail() {
    const email = search.trim().toLowerCase();
    if (!validEmail || recipients.some(r => r.email.toLowerCase() === email)) return;
    const match = query.data?.find(item => item.email.toLowerCase() === email);
    onChange([...recipients, match ? { key: match.id, judge_id: match.id, name: match.name, email: match.email } : { key: email, name: name.trim() || email, email, add_to_directory: save }]);
    reset();
  }
  return <div className="recipient-picker">
    <RecipientChips recipients={recipients} onChange={onChange} />
    <Field label="Find or add a recipient"><input autoComplete="off" value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); if (validEmail) addEmail(); } }} placeholder="Search a name or enter an email address" /></Field>
    {search.trim() && <div className="recipient-options">
      {suggestions.map(item => <button type="button" key={item.id} disabled={!item.email || item.do_not_contact} onClick={() => { onChange([...recipients, { key: item.id, judge_id: item.id, name: item.name, email: item.email }]); reset(); }}><strong>{item.name}</strong><small>{item.email || "No email address"}{item.do_not_contact ? " · Do not contact" : ""}</small></button>)}
      {!suggestions.length && !query.isPending && <p className="caption">No matching judge. Enter a valid email address to add a recipient.</p>}
      {validEmail && !recipients.some(r => r.email.toLowerCase() === search.trim().toLowerCase()) && <div className="recipient-direct">
        <Field label="Recipient name (optional)"><input value={name} onChange={event => setName(event.target.value)} /></Field>
        <label className="check-label"><input type="checkbox" checked={save} onChange={event => setSave(event.target.checked)} /> Add this person to judge directory</label>
        <button type="button" onClick={addEmail}>Add {search.trim()}</button>
      </div>}
      {query.error && <p role="alert">Recipient search is unavailable. Try again.</p>}
    </div>}
  </div>;
}
