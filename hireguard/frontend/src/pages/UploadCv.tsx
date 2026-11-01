import { DragEvent, FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import * as pdfjs from "pdfjs-dist";
import "../components/PdfViewer"; // configures the pdf.js worker
import { api, errMsg } from "../api";
import { Icon } from "../components/icons";
import { ErrorBox, fmtNum, PageHeader, useLoad } from "../components/ui";
import type { CandidateDetail, Job } from "../types";

// Server limits (HG_MAX_UPLOAD_BYTES, HG_MAX_PDF_PAGES), checked here first for a fast answer.
const MAX_BYTES = 5 * 1024 * 1024;
const MAX_PAGES = 6;

async function checkPdf(file: File): Promise<string | null> {
  if (file.size > MAX_BYTES) return `This file is ${fmtNum(file.size / 1024 / 1024, 1)} MB. The limit is 5 MB.`;
  const head = new Uint8Array(await file.slice(0, 5).arrayBuffer());
  if (String.fromCharCode(...head) !== "%PDF-") return "This is not a PDF file.";
  try {
    const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false }).promise;
    const pages = doc.numPages;
    await doc.destroy();
    if (pages > MAX_PAGES) return `This PDF has ${pages} pages. The limit is ${MAX_PAGES}.`;
  } catch {
    return "This PDF can't be read. It may be damaged or password-protected.";
  }
  return null;
}

export default function UploadCv() {
  const jobs = useLoad(() => api<Job[]>("/jobs"));
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState(params.get("job") ?? "");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!job && jobs.data?.length) setJob(jobs.data[0].job_id);
  }, [jobs.data, job]);

  async function pick(f: File | undefined) {
    setError(null);
    setFile(null);
    if (!f) return;
    const problem = await checkPdf(f);
    if (problem) setError(problem);
    else setFile(f);
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    void pick(e.dataTransfer.files?.[0]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("job_id", job);
    form.append("name", name.trim());
    form.append("email", email.trim());
    try {
      const c = await api<CandidateDetail>("/candidates", { form });
      const notice =
        c.hidden + c.flags
          ? `${c.name} was screened. ${c.hidden} hidden item(s) and ${c.flags} injection flag(s) were removed before scoring.`
          : `${c.name} was screened and scored.`;
      navigate(`/candidates?job=${encodeURIComponent(c.job_id)}&c=${encodeURIComponent(c.candidate_id)}`, { state: { notice } });
    } catch (x) {
      setError(errMsg(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Upload a CV"
        subtitle="Every PDF is treated as hostile: hidden text is stripped and reported, and only validated fields are scored."
      />
      <div className="upload-layout">
        <form className="panel stack" onSubmit={submit}>
          <div
            className={`dropzone ${over ? "over" : ""} ${file ? "has-file" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={drop}
          >
            <Icon name="upload" size={28} />
            <p className="strong">{file ? file.name : "Drop the candidate's PDF here"}</p>
            <p className="muted small">PDF only, up to 5 MB and {MAX_PAGES} pages</p>
            <label className="btn small file-btn">
              Choose a file
              <input type="file" accept="application/pdf,.pdf" className="visually-hidden" onChange={(e) => pick(e.target.files?.[0])} />
            </label>
          </div>
          <label>
            Job
            <select value={job} onChange={(e) => setJob(e.target.value)} required>
              {(jobs.data ?? []).map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.title} ({j.job_id})
                </option>
              ))}
            </select>
          </label>
          <div className="grid2">
            <label>
              Candidate name
              <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label>
              Candidate email
              <input type="email" value={email} maxLength={254} onChange={(e) => setEmail(e.target.value)} required />
            </label>
          </div>
          <ErrorBox error={error || jobs.error} />
          <div className="row end">
            <Link className="btn ghost" to="/candidates">
              Cancel
            </Link>
            <button className="btn primary" disabled={!file || !job || busy}>
              {busy ? "Screening…" : "Upload and screen"}
            </button>
          </div>
        </form>
        <aside className="panel steps" aria-label="What happens to the file">
          <h2>What happens next</h2>
          <ol>
            <li>
              <strong>Sanitize.</strong> White text, tiny fonts, off-page text and invisible characters are found and
              removed. You will see them in Blocked attacks.
            </li>
            <li>
              <strong>Extract.</strong> The model reads only the visible text and fills a fixed form. It has no tools
              and cannot act.
            </li>
            <li>
              <strong>Validate.</strong> Code checks every field against the text and drops anything it can't prove.
            </li>
            <li>
              <strong>Score.</strong> The job's rubric scores the validated fields. The score stays a proposal until a
              shortlist is approved.
            </li>
          </ol>
        </aside>
      </div>
    </>
  );
}
