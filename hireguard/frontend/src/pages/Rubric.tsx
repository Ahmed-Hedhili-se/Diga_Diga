import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, errMsg } from "../api";
import { usePermission } from "../auth";
import { ConfirmButton, ErrorBox, fmtNum, Loading, PageHeader, useLoad } from "../components/ui";
import type { Cefr, DegreeLevel, Job, Rubric as RubricData } from "../types";

const COMPONENTS = ["skills", "experience", "degree", "languages"] as const;
const DEGREES: DegreeLevel[] = ["none", "bac", "bts", "licence", "master", "ingenieur", "phd"];
const CEFRS: Cefr[] = ["A1", "A2", "B1", "B2", "C1", "C2", "native"];
const LANGS = ["fr", "en", "ar"] as const;

export default function Rubric() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const jobs = useLoad(() => api<Job[]>("/jobs"));
  const jobId = params.get("job") ?? jobs.data?.[0]?.job_id ?? "";
  const canEdit = usePermission("rubric.edit");
  const loaded = useLoad(() => api<RubricData>(`/jobs/${encodeURIComponent(jobId)}/rubric`), [jobId]);
  const [rubric, setRubric] = useState<RubricData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setRubric(loaded.data), [loaded.data]);

  const componentTotal = rubric
    ? COMPONENTS.reduce((total, component) => total + (rubric.component_weights[component] ?? 0), 0)
    : 0;
  const skillTotal = rubric ? Object.values(rubric.skill_weights).reduce((total, weight) => total + weight, 0) : 0;
  const valid = !!rubric && Math.round(componentTotal) === 100 && skillTotal > 0;

  async function save() {
    if (!rubric) return;
    setError(null);
    try {
      await api<RubricData>(`/jobs/${encodeURIComponent(jobId)}/rubric`, { method: "PUT", body: rubric });
      navigate(`/candidates?job=${encodeURIComponent(jobId)}`);
    } catch (saveError) {
      setError(errMsg(saveError));
      throw saveError;
    }
  }

  function close() {
    navigate(`/candidates${jobId ? `?job=${encodeURIComponent(jobId)}` : ""}`);
  }

  return (
    <>
      <PageHeader
        title="Scoring rubric"
        subtitle="Review the job criteria and weights. Saving is audited; existing scores change only after rescoring."
        actions={
          <label className="inline">
            Job
            <select
              aria-label="Job"
              value={jobId}
              onChange={(event) => navigate(`/rubrics?job=${encodeURIComponent(event.target.value)}`)}
            >
              {(jobs.data ?? []).map((job) => (
                <option key={job.job_id} value={job.job_id}>{job.title}</option>
              ))}
            </select>
          </label>
        }
      />
      <ErrorBox error={jobs.error || loaded.error || error} />
      <Loading show={loaded.loading || jobs.loading} rows={5} />
      {rubric && (
        <div className="card stack rubric">
          {!canEdit && <div className="alert info">Read-only: only HR managers can edit the rubric.</div>}
          <h2>Score components</h2>
          <p className={`small ${Math.round(componentTotal) === 100 ? "muted" : "text-warn"}`}>
            Total {fmtNum(componentTotal)} / 100{Math.round(componentTotal) === 100 ? "" : " (must equal 100)"}
          </p>
          {COMPONENTS.map((component) => (
            <label className="slider-row" key={component}>
              <span className="cap">{component}</span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                disabled={!canEdit}
                value={rubric.component_weights[component] ?? 0}
                onChange={(event) => setRubric({
                  ...rubric,
                  component_weights: { ...rubric.component_weights, [component]: Number(event.target.value) },
                })}
              />
              <span className="num">{rubric.component_weights[component] ?? 0}</span>
            </label>
          ))}
          <h2>Skill weights</h2>
          <p className="muted small">Relative share of the skills component.</p>
          {Object.entries(rubric.skill_weights).map(([skill, weight]) => (
            <label className="slider-row" key={skill}>
              <code>{skill}</code>
              <input
                type="range"
                min={0}
                max={10}
                step={1}
                disabled={!canEdit}
                value={weight}
                onChange={(event) => setRubric({
                  ...rubric,
                  skill_weights: { ...rubric.skill_weights, [skill]: Number(event.target.value) },
                })}
              />
              <span className="num">{skillTotal ? `${fmtNum((100 * weight) / skillTotal)}%` : "—"}</span>
            </label>
          ))}
          <div className="grid2">
            <label>
              Minimum years of experience
              <input
                type="number"
                min={0}
                max={40}
                step={0.5}
                disabled={!canEdit}
                value={rubric.min_years}
                onChange={(event) => setRubric({ ...rubric, min_years: Number(event.target.value) })}
              />
            </label>
            <label>
              Required degree
              <select
                disabled={!canEdit}
                value={rubric.required_degree}
                onChange={(event) => setRubric({ ...rubric, required_degree: event.target.value as DegreeLevel })}
              >
                {DEGREES.map((degree) => <option key={degree} value={degree}>{degree}</option>)}
              </select>
            </label>
          </div>
          <h2>Languages</h2>
          {rubric.languages.map((language, index) => (
            <div className="row" key={`${language.iso}-${index}`}>
              <select
                aria-label="Language"
                disabled={!canEdit}
                value={language.iso}
                onChange={(event) => setRubric({
                  ...rubric,
                  languages: rubric.languages.map((item, itemIndex) => itemIndex === index
                    ? { ...item, iso: event.target.value as typeof language.iso }
                    : item),
                })}
              >
                {LANGS.map((lang) => <option key={lang} value={lang}>{lang}</option>)}
              </select>
              <select
                aria-label="Minimum level"
                disabled={!canEdit}
                value={language.min_cefr}
                onChange={(event) => setRubric({
                  ...rubric,
                  languages: rubric.languages.map((item, itemIndex) => itemIndex === index
                    ? { ...item, min_cefr: event.target.value as Cefr }
                    : item),
                })}
              >
                {CEFRS.map((level) => <option key={level} value={level}>{level}</option>)}
              </select>
              {canEdit && (
                <button
                  type="button"
                  className="btn small ghost"
                  onClick={() => setRubric({
                    ...rubric,
                    languages: rubric.languages.filter((_, itemIndex) => itemIndex !== index),
                  })}
                >
                  Remove
                </button>
              )}
            </div>
          ))}
          {canEdit && (
            <button
              type="button"
              className="btn small"
              disabled={rubric.languages.length >= LANGS.length}
              onClick={() => setRubric({
                ...rubric,
                languages: [
                  ...rubric.languages,
                  { iso: LANGS.find((lang) => !rubric.languages.some((item) => item.iso === lang)) ?? "fr", min_cefr: "B2" },
                ],
              })}
            >
              Add language
            </button>
          )}
          {canEdit && (
            <div className="row end">
              <button type="button" className="btn ghost" onClick={close}>Cancel</button>
              <ConfirmButton
                className="btn primary"
                label="Save rubric"
                disabled={!valid}
                title="Save this rubric?"
                message="The change is recorded in the audit log. Existing scores change only when someone rescores."
                confirmLabel="Save rubric"
                onConfirm={save}
              />
            </div>
          )}
        </div>
      )}
      {!canEdit && <button type="button" className="btn" onClick={close}>Back to candidates</button>}
    </>
  );
}
