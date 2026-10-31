import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadFile, errMsg } from "../api";
import { usePermission } from "../auth";
import { Badge, Empty, ErrorBox, fmtDate, Loading, PageHeader, useLoad } from "../components/ui";
import type { ApprovalItem, EmployeeDocument } from "../types";

const TYPES = [
  ["work_certificate", "Work certificate (attestation de travail)"],
  ["salary_certificate", "Salary certificate (attestation de salaire)"],
  ["leave_confirmation", "Leave confirmation"],
] as const;

const PURPOSES = [
  ["bank", "Bank / loan"],
  ["visa", "Visa / embassy"],
  ["administration", "Public administration"],
  ["other", "Other"],
] as const;

export default function EmployeeDocs() {
  const docs = useLoad(() => api<EmployeeDocument[]>("/documents/mine"));
  const canAsk = usePermission("answer_desk.ask");
  const [type, setType] = useState<string>(TYPES[0][0]);
  const [purpose, setPurpose] = useState<string>("bank");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function request(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const params = type === "leave_confirmation" ? { start, end } : { purpose };
    try {
      const item = await api<ApprovalItem>("/documents/request", { body: { type, params } });
      setNotice(`Request sent (${item.id}). HR will release it with one click once it has been checked.`);
      docs.reload();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  async function download(d: EmployeeDocument) {
    setError(null);
    try {
      await downloadFile(`/documents/${encodeURIComponent(d.id)}/download`, `${d.type}-${d.id}.pdf`);
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <>
      <PageHeader
        title="My documents"
        subtitle="Generated from templates and released only after an HR approval."
        actions={
          canAsk ? (
            <Link className="btn" to="/answer-desk">
              Have a question? Answer Desk
            </Link>
          ) : undefined
        }
      />
      <form className="card stack" onSubmit={request}>
        <h2>Request a document</h2>
        <label>
          Document
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        {type === "leave_confirmation" ? (
          <div className="row">
            <label className="grow">
              From
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
            </label>
            <label className="grow">
              To
              <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} required />
            </label>
          </div>
        ) : (
          <label>
            Purpose
            <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              {PURPOSES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
        )}
        <button className="btn primary">Request</button>
      </form>
      <ErrorBox error={error || docs.error} />
      {notice && <div className="alert ok">{notice}</div>}

      <div className="card">
        <h2>My requests</h2>
        <Loading show={docs.loading} />
        {!docs.loading && !docs.data?.length && <Empty>No requests yet. Use the form above to ask for a certificate.</Empty>}
        <table className="table">
          <tbody>
            {(docs.data ?? []).map((d) => (
              <tr key={d.id}>
                <td>
                  <div>{TYPES.find(([v]) => v === d.type)?.[1] ?? d.type}</div>
                  <div className="muted small">
                    {d.id} · requested {fmtDate(d.requested_at)}
                  </div>
                </td>
                <td>
                  <Badge tone={d.status === "released" ? "ok" : d.status === "rejected" ? "danger" : "neutral"}>{d.status}</Badge>
                </td>
                <td className="num">
                  {d.status === "released" && (
                    <button className="btn small" onClick={() => download(d)}>
                      Download PDF
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
