import { useState, useEffect } from 'react';
import {
    UploadCloud, FileCheck2, Loader2, Download, FileDown, ChevronDown,
    LayoutList, ListOrdered, ShieldAlert, AlertCircle, Sparkles, Info,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLocalMode } from '../context/LocalModeContext';
import { usePersona } from '../context/PersonaContext';
import PersonaSwitcher from '../components/PersonaSwitcher';
import CitationStatusBadge, { ConfidenceBars, TechnicalFailureNote } from '../components/CitationStatusBadge';
import CitationStageList from '../components/CitationStageList';
import AdjustmentBadge from '../components/AdjustmentBadge';
import FlagCorrectionButton from '../components/FlagCorrectionButton';
import CitationWalkthrough from '../components/CitationWalkthrough';
import ContradictionDiff from '../components/ContradictionDiff';
import './VerifyFiling.css';

const DEMO_FILINGS = [
    {
        id: 'writ',
        label: 'Writ Petition (sample)',
        file: '/demo/sample_writ_petition.txt',
        filename: 'sample_writ_petition.txt',
        mime: 'text/plain',
        blurb: 'Contains a citation with no match in our indexed corpus ("Meera Devi v. Union of India") alongside two real, correctly-cited judgments.',
    },
    {
        id: 'bail',
        label: 'Bail Appeal (sample)',
        file: '/demo/sample_bail_appeal.pdf',
        filename: 'sample_bail_appeal.pdf',
        mime: 'application/pdf',
        blurb: 'Contains a real judgment ("Tarun Kumar v. ED") cited for a claim it does not actually support.',
    },
];

const PERSONA_INTRO = {
    lawyer: 'Verify every citation before this filing reaches the court.',
    paralegal: 'Run a full citation audit, then hand a clean, exportable table to your supervising lawyer.',
    student: 'Step through each citation, one at a time, to see exactly why it’s grounded — or isn’t.',
    judge: 'The layer that would have caught it — see how LexSetu flags a citation with no match in the corpus and a holding the source doesn’t actually support, using two real, already-verified test filings.',
};

async function* streamSSE(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const chunk = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const line = chunk.split('\n').find((l) => l.startsWith('data: '));
            if (line) {
                try { yield JSON.parse(line.slice(6)); } catch { /* skip malformed chunk */ }
            }
        }
    }
}

const VerifyFiling = () => {
    const { token } = useAuth();
    const { localOnly } = useLocalMode();
    const { personaId, persona } = usePersona();

    const [coverage, setCoverage] = useState(null);
    const [file, setFile] = useState(null);
    const [filingLabel, setFilingLabel] = useState('');
    const [verifying, setVerifying] = useState(false);
    const [citationsFound, setCitationsFound] = useState([]);
    const [citationResults, setCitationResults] = useState({});
    const [citationStages, setCitationStages] = useState({});
    const [completedCount, setCompletedCount] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [doneReport, setDoneReport] = useState(null);
    const [reportId, setReportId] = useState(null);
    const [errorMsg, setErrorMsg] = useState(null);
    const [viewMode, setViewMode] = useState(persona.defaultView);
    const [diffTarget, setDiffTargetRaw] = useState(null); // { citation, index }
    const openDiff = (citation, index) => setDiffTargetRaw({ citation, index });
    const [expandedIdx, setExpandedIdx] = useState(null);
    const [exporting, setExporting] = useState(null); // 'csv' | 'pdf' | null
    const [inputExpanded, setInputExpanded] = useState(true);
    const [renderLanguage, setRenderLanguage] = useState('en');
    const [renderedCitations, setRenderedCitations] = useState(null);
    const [rendering, setRendering] = useState(false);

    useEffect(() => {
        let cancelled = false;
        fetch('/api/citations/coverage', { headers: { Authorization: `Bearer ${token}` } })
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => { if (!cancelled) setCoverage(data); })
            .catch(() => { if (!cancelled) setCoverage(null); });
        return () => { cancelled = true; };
    }, [token]);

    useEffect(() => { setViewMode(persona.defaultView); }, [personaId, persona.defaultView]);

    const resetResults = () => {
        setErrorMsg(null);
        setDoneReport(null);
        setReportId(null);
        setCitationsFound([]);
        setCitationResults({});
        setCitationStages({});
        setCompletedCount(0);
        setTotalCount(0);
        setExpandedIdx(null);
        setInputExpanded(true);
        setRenderLanguage('en');
        setRenderedCitations(null);
    };

    const runVerification = async (fileToVerify) => {
        resetResults();
        setVerifying(true);
        try {
            const formData = new FormData();
            formData.append('file', fileToVerify);
            const response = await fetch('/api/citations/verify-filing', {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
                body: formData,
            });
            if (!response.ok) {
                let msg = 'Verification failed';
                try { const e = await response.json(); msg = e.detail || msg; } catch { msg = `Server error (${response.status})`; }
                throw new Error(msg);
            }
            for await (const event of streamSSE(response)) {
                if (event.type === 'citations_found') {
                    setCitationsFound(event.citations);
                    setTotalCount(event.total);
                } else if (event.type === 'stage') {
                    setCitationStages((prev) => ({
                        ...prev,
                        [event.citation_index]: {
                            ...prev[event.citation_index],
                            [event.stage]: { status: event.status, reason: event.reason },
                        },
                    }));
                } else if (event.type === 'result') {
                    setCompletedCount(event.completed);
                    setCitationResults((prev) => ({ ...prev, [event.citation_index]: event.citation }));
                } else if (event.type === 'done') {
                    setDoneReport(event.report);
                    setReportId(event.report_id);
                    setInputExpanded(false);
                } else if (event.type === 'error') {
                    setErrorMsg(event.message || 'Something went wrong while verifying this filing.');
                }
            }
        } catch (err) {
            setErrorMsg(err.message);
        } finally {
            setVerifying(false);
        }
    };

    const handleFileChange = (e) => {
        const f = e.target.files?.[0];
        if (f) {
            setFile(f);
            setFilingLabel(f.name);
            resetResults();
        }
    };

    const loadDemoFiling = async (demo) => {
        setFilingLabel(demo.label);
        try {
            const res = await fetch(demo.file);
            const blob = await res.blob();
            const demoFile = new File([blob], demo.filename, { type: demo.mime });
            setFile(demoFile);
            await runVerification(demoFile);
        } catch (err) {
            setErrorMsg('Could not load demo filing: ' + err.message);
        }
    };

    // A tighten flag takes effect on the pipeline immediately (proven server-side);
    // optimistically reflect that in the CURRENTLY displayed report too, so the
    // person flagging sees the change without needing to re-run the whole filing.
    // A loosen flag stays untouched here -- it must NOT visibly change anything
    // until an admin confirms it; FlagCorrectionButton's own inline feedback
    // ("Submitted for review...") is the only thing that changes for that case.
    const handleFlagged = (idx, response) => {
        if (response.direction !== 'tighten') return;
        setDoneReport((prev) => {
            if (!prev) return prev;
            const citations = prev.citations.map((c, i) => {
                if (i !== idx) return c;
                // Match what the real short-circuited pipeline actually returns
                // (services/citation_verifier.py: resolve_case/search/entailment
                // are skipped entirely) -- leaving the old matched_case/matched_text/
                // entailment in place would show a stale "High Confidence" tag and
                // the ORIGINAL matched passage next to a verdict that no longer has
                // any retrieval or entailment behind it. Caught via browser testing.
                return {
                    ...c,
                    status: response.correct_output,
                    matched_case: null,
                    paragraph_display: null,
                    matched_text: null,
                    entailment: null,
                    adjusted_from_correction: true,
                    correction_meta: { system_output: c.status, flagged_at: new Date().toISOString() },
                };
            });
            return { ...prev, citations };
        });
    };

    // Harness-sprint Part E: a rendering step over the ALREADY-verified report --
    // never re-runs verification, never feeds Hindi/Hinglish back into the
    // pipeline. Falls back to English on any failure rather than showing a
    // half-translated or broken state.
    const changeLanguage = async (lang) => {
        setRenderLanguage(lang);
        if (lang === 'en' || !reportId) {
            setRenderedCitations(null);
            return;
        }
        setRendering(true);
        try {
            const res = await fetch(`/api/citations/${reportId}/render`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ language: lang }),
            });
            if (!res.ok) {
                const e = await res.json().catch(() => ({}));
                throw new Error(e.detail || 'Translation failed.');
            }
            const data = await res.json();
            setRenderedCitations(data.citations);
        } catch (err) {
            setErrorMsg(err.message);
            setRenderLanguage('en');
            setRenderedCitations(null);
        } finally {
            setRendering(false);
        }
    };

    // Plain <a href="/api/citations/export/...">.csv/.pdf never worked -- the
    // JWT lives in localStorage, so a bare browser navigation carries no
    // Authorization header and the export just opened a tab showing a raw
    // 401. Fetching with the header, then downloading the blob, is the same
    // pattern DraftAssistant.jsx already uses for its own downloads.
    const downloadExport = async (format) => {
        if (!reportId) return;
        setExporting(format);
        try {
            const response = await fetch(`/api/citations/export/${reportId}.${format}`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) throw new Error(`Export failed (${response.status})`);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `citation-integrity-report-${reportId.slice(0, 8)}.${format}`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (err) {
            setErrorMsg('Export failed: ' + err.message);
        } finally {
            setExporting(null);
        }
    };

    // Stable index order (not arrival order) so cards don't jump around as
    // parallel results land -- each slot fills in place, "checking..." until it does.
    const orderedCitations = Array.from({ length: totalCount }, (_, i) => {
        const found = citationsFound[i];
        const result = citationResults[i];
        return result ? { ...found, ...result } : found ? { ...found, pending: true } : null;
    });
    const finalCitations = doneReport?.citations || null;
    const baseCitations = finalCitations || orderedCitations;
    // Harness-sprint Part E: merge translated display text onto the SAME
    // canonical citation objects -- status/case_name/etc are untouched, only
    // rendered_claimed_content / entailment.rendered_reasoning are added, so
    // export and flag-correction (which read the English fields) are
    // completely unaffected by which language is currently displayed.
    const displayCitations = baseCitations.map((c, i) => {
        if (!c || !renderedCitations) return c;
        const r = renderedCitations[i];
        if (!r) return c;
        return {
            ...c,
            rendered_claimed_content: r.rendered_claimed_content,
            entailment: c.entailment
                ? { ...c.entailment, rendered_reasoning: r.entailment?.rendered_reasoning }
                : c.entailment,
        };
    });

    return (
        <div className="verify-wrapper animate-fade-in">
            <div className="verify-header">
                <div className="badge-chip"><FileCheck2 size={16} /><span>Verify-a-Filing</span></div>
                <h2>Citation Integrity Check</h2>
                <p className="subtitle persona-tagline">{PERSONA_INTRO[personaId]}</p>
                <PersonaSwitcher />
            </div>

            {/* UX item 2: real coverage banner, visible wherever verification starts */}
            <div className="coverage-banner">
                <Info size={15} />
                {coverage ? coverage.banner : 'Loading indexed corpus coverage…'}
            </div>

            {localOnly && (
                <div className="local-only-block-banner">
                    <ShieldAlert size={16} />
                    Citation checking is turned off in Local-only mode. Comparing a citation against the real
                    judgment text needs an internet connection to our verification service, which Local-only mode
                    switches off. Turn Local-only off in the sidebar to use this feature.
                </div>
            )}

            {/* Caught in UX audit: with the full upload card always expanded, the
                walkthrough's actual step content sat mostly below the fold on a
                normal browser window. Collapsing to a compact bar once a report
                exists gives the results/walkthrough the space back. */}
            {doneReport && !inputExpanded ? (
                <button className="outline verify-input-collapsed" onClick={() => setInputExpanded(true)}>
                    <FileCheck2 size={15} /> {filingLabel || 'Filing verified'} <span>— verify a different filing</span>
                </button>
            ) : (
                <div className="verify-input-card">
                    <div className="file-upload-box">
                        <input type="file" id="verify-file-input" accept=".pdf,.txt" onChange={handleFileChange} style={{ display: 'none' }} disabled={localOnly} />
                        <label htmlFor="verify-file-input" className={`file-drop-area ${localOnly ? 'disabled' : ''}`}>
                            <UploadCloud size={28} className="upload-icon" />
                            {file ? (
                                <div className="selected-file-info">
                                    <strong>{filingLabel}</strong>
                                    <span>({(file.size / 1024).toFixed(1)} KB)</span>
                                </div>
                            ) : (
                                <div>
                                    <p className="drop-title">Upload a filing (.pdf or .txt)</p>
                                    <p className="drop-sub">Any filing — not just one LexSetu drafted</p>
                                </div>
                            )}
                        </label>
                    </div>

                    <button
                        className="primary-btn verify-btn"
                        onClick={() => file && runVerification(file)}
                        disabled={!file || verifying || localOnly}
                    >
                        {verifying ? <><Loader2 size={18} className="spin" /> Verifying…</> : <><Sparkles size={18} /> Verify Citations</>}
                    </button>

                    <div className="divider-text"><span>OR TRY A VERIFIED SAMPLE</span></div>
                    <div className="demo-filing-grid">
                        {DEMO_FILINGS.map((demo) => (
                            <button key={demo.id} className="outline demo-filing-card" onClick={() => loadDemoFiling(demo)} disabled={verifying || localOnly}>
                                <strong>{demo.label}</strong>
                                <span>{demo.blurb}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {errorMsg && (
                <div className="verify-error-banner"><AlertCircle size={16} /> {errorMsg}</div>
            )}

            {verifying && totalCount === 0 && (
                <div className="verify-progress-state">
                    <Loader2 size={28} className="spin" />
                    <p>Reading filing and extracting citations…</p>
                </div>
            )}

            {totalCount > 0 && (
                <>
                    {verifying && (
                        <div className="verify-progress-strip">
                            <Loader2 size={16} className="spin" />
                            Checking citation {Math.min(completedCount + 1, totalCount)} of {totalCount}…
                            <div className="verify-progress-track">
                                <div className="verify-progress-fill" style={{ width: `${(completedCount / totalCount) * 100}%` }} />
                            </div>
                        </div>
                    )}

                    {doneReport?.extraction_incomplete && (
                        <div className="verify-error-banner">
                            <AlertCircle size={16} /> Citation extraction didn't fully complete for this filing
                            (the extraction service was briefly unavailable) — the list below may be missing
                            citations. Re-run verification to try again.
                        </div>
                    )}

                    {doneReport && (
                        <div className="verify-summary-strip">
                            <span className="summary-count verified">{doneReport.summary.verified} Verified</span>
                            <span className="summary-count mismatch">{doneReport.summary.mismatch} Mismatch</span>
                            <span className="summary-count not-found">{doneReport.summary.not_found} Not found</span>

                            <div className={`export-actions ${persona.emphasizeExport ? 'emphasized' : ''}`}>
                                <button className="outline btn-sm" onClick={() => downloadExport('csv')} disabled={exporting === 'csv'}>
                                    {exporting === 'csv' ? <Loader2 size={15} className="spin" /> : <Download size={15} />} Export CSV
                                </button>
                                <button className="outline btn-sm" onClick={() => downloadExport('pdf')} disabled={exporting === 'pdf'}>
                                    {exporting === 'pdf' ? <Loader2 size={15} className="spin" /> : <FileDown size={15} />} Export PDF
                                </button>
                            </div>
                        </div>
                    )}

                    {doneReport && (
                        <div className="view-mode-row">
                            <div className="view-mode-toggle" role="tablist">
                                <button className={viewMode === 'list' ? 'active' : ''} onClick={() => setViewMode('list')}>
                                    <LayoutList size={15} /> All results
                                </button>
                                <button className={viewMode === 'walkthrough' ? 'active' : ''} onClick={() => setViewMode('walkthrough')}>
                                    <ListOrdered size={15} /> Step-by-step walkthrough
                                </button>
                            </div>

                            <div className="language-toggle" role="tablist">
                                {[['en', 'English'], ['hindi', 'हिंदी'], ['hinglish', 'Hinglish']].map(([code, label]) => (
                                    <button key={code} className={renderLanguage === code ? 'active' : ''} onClick={() => changeLanguage(code)} disabled={rendering}>
                                        {rendering && renderLanguage === code ? <Loader2 size={13} className="spin" /> : null} {label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {renderLanguage !== 'en' && renderedCitations && (
                        <div className="translation-notice">
                            <Info size={14} /> Translated from a result verified in English — the verdicts and citation data themselves are unchanged, only this text.
                        </div>
                    )}

                    {doneReport && viewMode === 'walkthrough' && (
                        <CitationWalkthrough citations={displayCitations} onOpenDiff={openDiff} />
                    )}

                    {(!doneReport || viewMode === 'list') && (
                        <div className="citation-card-list">
                            {displayCitations.map((c, i) => (
                                <CitationCard
                                    key={i}
                                    citation={c}
                                    stages={citationStages[i]}
                                    expanded={expandedIdx === i}
                                    onToggle={() => setExpandedIdx(expandedIdx === i ? null : i)}
                                    onOpenDiff={openDiff}
                                    reportId={reportId}
                                    citationIndex={i}
                                    token={token}
                                    onFlagged={handleFlagged}
                                />
                            ))}
                        </div>
                    )}
                </>
            )}

            {doneReport && totalCount === 0 && (
                <div className="verify-empty-state">
                    <FileCheck2 size={40} strokeWidth={1.2} />
                    <h4>No citations detected</h4>
                    <p>This filing doesn't appear to reference any case judgments — nothing to verify.</p>
                </div>
            )}

            {diffTarget && (
                <ContradictionDiff
                    citation={diffTarget.citation}
                    onClose={() => setDiffTargetRaw(null)}
                    reportId={reportId}
                    citationIndex={diffTarget.index}
                    token={token}
                    onFlagged={handleFlagged}
                />
            )}
        </div>
    );
};

const CitationCard = ({ citation, stages, expanded, onToggle, onOpenDiff, reportId, citationIndex, token, onFlagged }) => {
    if (!citation || citation.pending) {
        return (
            <div className="citation-card pending-card">
                <CitationStageList stages={stages} caseName={citation?.case_name} />
            </div>
        );
    }

    const caseName = citation.matched_case?.case_name || citation.case_name;

    return (
        <div className={`citation-card ${expanded ? 'expanded' : ''}`}>
            <button className="citation-card-header" onClick={onToggle}>
                <div className="citation-card-title">
                    <span className="case-name">{caseName}</span>
                    {citation.matched_case && (
                        <span className="case-meta">{citation.matched_case.court} · {citation.matched_case.date?.slice(0, 10)}</span>
                    )}
                </div>
                <div className="citation-card-right">
                    <AdjustmentBadge interactive={false} correctionMeta={citation.adjusted_from_correction ? citation.correction_meta : null} />
                    <CitationStatusBadge status={citation.status} />
                    <ChevronDown size={16} className={`chevron ${expanded ? 'rotated' : ''}`} />
                </div>
            </button>

            {expanded && (
                <div className="citation-card-detail animate-fade-in">
                    <p className="detail-label">Claimed in the filing</p>
                    <p className="detail-claim" lang={citation.rendered_claimed_content ? 'hi' : 'en'}>
                        {citation.rendered_claimed_content || citation.claimed_content || citation.context_snippet}
                    </p>

                    {citation.status === 'Not found in indexed corpus' && (
                        <p className="detail-not-found">
                            No matching source in our indexed corpus. This doesn't mean the citation is fake —
                            it falls outside our current Supreme Court, 2016–2025 coverage.
                        </p>
                    )}

                    {citation.matched_case && (
                        <>
                            <p className="detail-label">Matched passage {citation.paragraph_display ? `(${citation.paragraph_display})` : ''}</p>
                            <p className="detail-source">{citation.matched_text}</p>
                        </>
                    )}

                    {citation.entailment?.technical_failure && <TechnicalFailureNote />}

                    {citation.adjusted_from_correction && (
                        <div className="detail-adjustment-row">
                            <AdjustmentBadge correctionMeta={citation.correction_meta} />
                        </div>
                    )}

                    <div className="detail-footer">
                        {citation.entailment?.confidence && !citation.entailment?.technical_failure && (
                            <ConfidenceBars confidence={citation.entailment.confidence} />
                        )}
                        {citation.status === 'Mismatch' && (
                            <button className="outline btn-sm" onClick={() => onOpenDiff(citation, citationIndex)}>
                                {citation.entailment?.technical_failure ? 'View details' : 'View contradiction'}
                            </button>
                        )}
                    </div>

                    {reportId && (
                        <div className="detail-flag-row">
                            <FlagCorrectionButton
                                reportId={reportId}
                                citationIndex={citationIndex}
                                currentStatus={citation.status}
                                token={token}
                                onFlagged={onFlagged}
                            />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default VerifyFiling;
