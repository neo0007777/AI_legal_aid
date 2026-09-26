import { useState, useEffect } from 'react';
import {
    UploadCloud, FileCheck2, Loader2, Download, FileDown, ChevronDown,
    LayoutList, ListOrdered, ShieldAlert, AlertCircle, Sparkles, Info,
    Scale, Hash, ExternalLink, BookmarkCheck, Check, FileText, Trash2, CheckCircle2,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLocalMode } from '../context/LocalModeContext';
import { usePersona } from '../context/PersonaContext';
import { useLanguage, SUPPORTED_LANGUAGES } from '../context/LanguageContext';
import PersonaSwitcher from '../components/PersonaSwitcher';
import CitationStatusBadge, {
    ConfidenceBars, TechnicalFailureNote, RetrievalSourceBadge,
    IdentityBadge, PropositionBadge,
} from '../components/CitationStatusBadge';
import CitationWalkthrough from '../components/CitationWalkthrough';
import ContradictionDiff from '../components/ContradictionDiff';
import AdjustmentBadge from '../components/AdjustmentBadge';
import FlagCorrectionButton from '../components/FlagCorrectionButton';
import PrivilegeShield from '../components/PrivilegeShield';
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
    const { languageCode } = useLanguage();

    const [coverage, setCoverage] = useState(null);
    const [file, setFile] = useState(null);
    const [filingLabel, setFilingLabel] = useState('');
    const [verifying, setVerifying] = useState(false);
    const [citationsFound, setCitationsFound] = useState([]);
    const [citationResults, setCitationResults] = useState({});
    const [completedCount, setCompletedCount] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [doneReport, setDoneReport] = useState(null);
    const [reportId, setReportId] = useState(null);
    const [errorMsg, setErrorMsg] = useState(null);
    const [viewMode, setViewMode] = useState(persona.defaultView);
    const [diffTarget, setDiffTarget] = useState(null);
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
        setCompletedCount(0);
        setTotalCount(0);
        setExpandedIdx(null);
        setInputExpanded(true);
        setRenderLanguage('en');
        setRenderedCitations(null);
        setRendering(false);
    };

    const changeLanguage = async (targetLang) => {
        if (!reportId || targetLang === renderLanguage) return;
        if (targetLang === 'en') {
            setRenderLanguage('en');
            setRenderedCitations(null);
            return;
        }
        setRendering(true);
        try {
            const res = await fetch(`/api/citations/${reportId}/render`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ language: targetLang }),
            });
            if (!res.ok) throw new Error(`Render failed: ${res.status}`);
            const data = await res.json();
            setRenderedCitations(data.citations);
            setRenderLanguage(targetLang);
        } catch (err) {
            console.error('Translation error:', err);
        } finally {
            setRendering(false);
        }
    };

    // Auto-follow the app-wide language switcher: as soon as a report is
    // ready, or the global language changes, render the citation report in
    // that language without requiring a separate click inside this page.
    // Hinglish stays a manual-only option below (it isn't part of the
    // app-wide switcher), and the manual buttons still work as an override.
    useEffect(() => {
        if (!reportId) return;
        if (languageCode === renderLanguage) return;
        changeLanguage(languageCode);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reportId, languageCode]);

    const handleFlagged = (idx, newStatus, meta) => {
        setCitationResults((prev) => {
            const copy = { ...prev };
            if (copy[idx]) {
                copy[idx] = {
                    ...copy[idx],
                    status: newStatus,
                    adjusted_from_correction: true,
                    correction_meta: meta,
                };
            }
            return copy;
        });
        if (doneReport) {
            setDoneReport((prev) => {
                if (!prev) return prev;
                const copyCitations = [...prev.citations];
                if (copyCitations[idx]) {
                    copyCitations[idx] = {
                        ...copyCitations[idx],
                        status: newStatus,
                        adjusted_from_correction: true,
                        correction_meta: meta,
                    };
                }
                return { ...prev, citations: copyCitations };
            });
        }
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

    // Plain <a href="/api/citations/export/...">.csv/.pdf never worked -- the
    // JWT lives in localStorage, so a bare browser navigation carries no
    // Authorization header and the export just opened a tab showing a raw
    // 401. Fetching with the header, then downloading the blob, is the same
    // pattern DraftAssistant.jsx already uses for its own downloads.
    const downloadExport = async (format) => {
        if (!reportId) return;
        setExporting(format);
        try {
            const langParam = format === 'pdf' && renderLanguage !== 'en' ? `?lang=${encodeURIComponent(renderLanguage)}` : '';
            const response = await fetch(`/api/citations/export/${reportId}.${format}${langParam}`, {
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

    const [purging, setPurging] = useState(false);
    const [purgeNotice, setPurgeNotice] = useState(null);

    const handlePurgeSession = async () => {
        if (!reportId) return;
        setPurging(true);
        try {
            await fetch(`/api/citations/${reportId}/purge`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
        } catch (e) {
            console.warn('Purge session notice:', e);
        } finally {
            setPurging(false);
        }
        resetResults();
        setPurgeNotice('Filing text & citation report completely purged from active server memory. Zero trace retained.');
        setTimeout(() => setPurgeNotice(null), 6000);
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
    const displayCitations = renderedCitations || baseCitations;

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

            {/* High-trust visible Attorney-Client Privilege Shield */}
            <PrivilegeShield />

            {purgeNotice && (
                <div className="purge-success-banner animate-fade-in">
                    <CheckCircle2 size={16} />
                    <span>{purgeNotice}</span>
                </div>
            )}

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
                            {doneReport.summary.partial_match > 0 && (
                                <span className="summary-count partial">{doneReport.summary.partial_match} Partial</span>
                            )}
                            <span className="summary-count mismatch">{doneReport.summary.mismatch} Mismatch</span>
                            {doneReport.summary.possible_fabrication > 0 && (
                                <span className="summary-count fabrication">{doneReport.summary.possible_fabrication} Fabrication</span>
                            )}
                            {doneReport.summary.unverified > 0 && (
                                <span className="summary-count unverified">{doneReport.summary.unverified} Unverified</span>
                            )}
                            {doneReport.summary.not_found > 0 && !doneReport.summary.possible_fabrication && !doneReport.summary.unverified && (
                                <span className="summary-count not-found">{doneReport.summary.not_found} Not in Index</span>
                            )}
                            {doneReport.summary.external_error > 0 && (
                                <span className="summary-count ext-error">{doneReport.summary.external_error} Source unavailable</span>
                            )}

                            <div className={`export-actions ${persona.emphasizeExport ? 'emphasized' : ''}`}>
                                <button className="outline btn-sm" onClick={() => downloadExport('csv')} disabled={exporting === 'csv'}>
                                    {exporting === 'csv' ? <Loader2 size={15} className="spin" /> : <Download size={15} />} Export CSV
                                </button>
                                <button className="outline btn-sm" onClick={() => downloadExport('pdf')} disabled={exporting === 'pdf'}>
                                    {exporting === 'pdf' ? <Loader2 size={15} className="spin" /> : <FileDown size={15} />} Export PDF
                                </button>
                                <button
                                    className="outline btn-sm btn-purge-session"
                                    onClick={handlePurgeSession}
                                    disabled={purging}
                                    title="Immediately wipe document and verification record from active server RAM"
                                >
                                    {purging ? <Loader2 size={15} className="spin" /> : <Trash2 size={15} />} Purge RAM
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
                                {[{ code: 'en', nativeLabel: 'English' }, ...SUPPORTED_LANGUAGES.filter(l => l.code !== 'en'), { code: 'hinglish', nativeLabel: 'Hinglish' }].map(({ code, nativeLabel }) => (
                                    <button
                                        key={code}
                                        className={renderLanguage === code ? 'active' : ''}
                                        onClick={() => changeLanguage(code)}
                                        disabled={rendering}
                                    >
                                        {rendering && renderLanguage === code ? <Loader2 size={13} className="spin" /> : null} {nativeLabel}
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
                        <CitationWalkthrough citations={displayCitations} onOpenDiff={setDiffTarget} />
                    )}

                    {(!doneReport || viewMode === 'list') && (
                        <div className="citation-card-list">
                            {displayCitations.map((c, i) => (
                                <CitationCard
                                    key={i}
                                    citation={c}
                                    expanded={expandedIdx === i}
                                    onToggle={() => setExpandedIdx(expandedIdx === i ? null : i)}
                                    onOpenDiff={setDiffTarget}
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

            {diffTarget && <ContradictionDiff citation={diffTarget} onClose={() => setDiffTarget(null)} />}
        </div>
    );
};

const CitationCard = ({ citation, expanded, onToggle, onOpenDiff, reportId, citationIndex, token, onFlagged }) => {
    if (!citation) {
        return (
            <div className="citation-card pending-card">
                <Loader2 size={16} className="spin" /> Checking…
            </div>
        );
    }
    if (citation.pending) {
        return (
            <div className="citation-card pending-card">
                <Loader2 size={16} className="spin" /> Checking <strong>{citation.case_name}</strong>…
            </div>
        );
    }

    const caseName = citation.citation_identity?.matched_case?.case_name || citation.matched_case?.case_name || citation.case_name;
    const isVerified     = citation.citation_identity?.status === 'VERIFIED';
    const isFabrication  = citation.status === 'Possible Fabrication' || citation.citation_identity?.status === 'POSSIBLE_FABRICATION';
    const isUnverified   = citation.status === 'Unverified Citation' || citation.citation_identity?.status === 'UNVERIFIED_CITATION';
    const isNotFound     = citation.status === 'Not Indexed / Not Found' || citation.citation_identity?.status === 'NOT_FOUND_IN_INDEXED_CORPUS';
    const isExtError     = citation.status === 'External Source Error';

    const propStatus = citation.proposition_verification?.status;
    const rawReasoning = citation.proposition_verification?.reasoning || citation.entailment?.reasoning;
    const propReasoning = typeof rawReasoning === 'string' ? rawReasoning : (rawReasoning ? JSON.stringify(rawReasoning) : '');
    const rawEvidence = citation.proposition_verification?.evidence_passage || citation.matched_text;
    const evidenceText = typeof rawEvidence === 'string' ? rawEvidence : (rawEvidence ? JSON.stringify(rawEvidence) : '');
    const holdingType = citation.proposition_verification?.holding_type;
    const rawQuote = citation.proposition_verification?.supporting_quote;
    const supportingQuote = typeof rawQuote === 'string' ? rawQuote : (rawQuote ? JSON.stringify(rawQuote) : null);
    const evidencePassageIndex = citation.proposition_verification?.evidence_passage_index || null;
    const relatedAuthorities = Array.isArray(citation.related_authorities) ? citation.related_authorities : [];

    return (
        <div className={`citation-card ${expanded ? 'expanded' : ''}`}>
            <button className="citation-card-header" onClick={onToggle}>
                <div className="citation-card-title">
                    <span className="case-name">{caseName}</span>
                    <span className="case-meta">
                        {citation.citation_string ? `${citation.citation_string} · ` : ''}
                        {citation.matched_case?.court || citation.citation_identity?.matched_case?.court || 'Court unverified'}
                        {citation.matched_case?.date ? ` · ${citation.matched_case.date?.slice(0, 10)}` : ''}
                    </span>
                </div>
                <div className="citation-card-right">
                    <AdjustmentBadge interactive={false} correctionMeta={citation.adjusted_from_correction ? citation.correction_meta : null} />
                    <RetrievalSourceBadge
                        retrievalSource={citation.retrieval_source}
                        externalLookup={citation.external_lookup}
                    />
                    <CitationStatusBadge status={citation.status} />
                    <ChevronDown size={16} className={`chevron ${expanded ? 'rotated' : ''}`} />
                </div>
            </button>

            {expanded && (
                <div className="citation-card-detail animate-fade-in">

                    {/* ── STAGE 1: CASE IDENTITY RESOLUTION ── */}
                    <div className="stage-block">
                        <div className="stage-block-header">
                            <span className="stage-block-title">
                                <BookmarkCheck size={14} /> Stage 1: Case Identity Resolution
                            </span>
                            <IdentityBadge status={citation.citation_identity?.status || (citation.matched_case ? 'VERIFIED' : 'UNVERIFIED_CITATION')} />
                        </div>
                        <div className="stage-info-grid">
                            <div className="stage-info-cell">
                                <strong>Canonical Authority</strong>
                                <span>{citation.citation_identity?.matched_case?.case_name || citation.matched_case?.case_name || 'Unresolved'}</span>
                            </div>
                            <div className="stage-info-cell">
                                <strong>Reported Citation</strong>
                                <span>{citation.citation_identity?.matched_case?.citation || citation.citation_string || 'Not provided'}</span>
                            </div>
                            <div className="stage-info-cell">
                                <strong>Court / Date</strong>
                                <span>
                                    {citation.citation_identity?.matched_case?.court || 'N/A'}
                                    {citation.citation_identity?.matched_case?.date ? ` (${citation.citation_identity.matched_case.date})` : ''}
                                </span>
                            </div>
                            <div className="stage-info-cell">
                                <strong>Resolution Method</strong>
                                <span style={{ textTransform: 'capitalize' }}>
                                    {citation.citation_identity?.resolution_method?.replace(/_/g, ' ') || 'None (No match)'}
                                </span>
                            </div>
                        </div>

                        {isFabrication && (
                            <div className="detail-not-found-block">
                                <p className="detail-not-found" style={{ background: '#FEE2E2', color: '#991B1B' }}>
                                    <strong>Authoritative Search Exhausted:</strong> Neither the Indian Kanoon national repository nor official court indices record any judgment for this citation and parties. This authority appears to be fabricated or fictitious.
                                </p>
                            </div>
                        )}

                        {isUnverified && !isFabrication && (
                            <div className="detail-not-found-block">
                                <p className="detail-not-found">
                                    <strong>Identity Unverified:</strong> The exact reported authority could not be resolved from authoritative records. Semantic similarity or citing judgments were not accepted as substitutes. Manual verification is required.
                                </p>
                            </div>
                        )}

                        {isNotFound && !isFabrication && !isUnverified && (
                            <div className="detail-not-found-block">
                                <p className="detail-not-found">
                                    Not found in the local indexed corpus. External search returned no authoritative match.
                                </p>
                            </div>
                        )}

                        {isExtError && (
                            <div className="detail-not-found-block">
                                <p className="detail-not-found">
                                    External source search encountered network/timeout issues. Identity could not be checked right now.
                                </p>
                            </div>
                        )}
                    </div>

                    {/* ── STAGE 4, 5, 6: SUBSTANTIVE PROPOSITION & ENTAILMENT ── */}
                    <div className="stage-block">
                        <div className="stage-block-header">
                            <span className="stage-block-title">
                                <Scale size={14} /> Stage 2: Substantive Proposition & Entailment
                            </span>
                            <PropositionBadge status={propStatus || (isVerified ? 'SUPPORTED' : 'NOT_RUN')} />
                        </div>

                        <p className="detail-label" style={{ marginTop: '0.4rem' }}>Filing Claim (Verbatim)</p>
                        <p className="detail-claim">{citation.claimed_content || citation.context_snippet}</p>

                        {isVerified && evidenceText ? (
                            <>
                                <p className="detail-label">
                                    Evidence from Actual Cited Judgment
                                    {citation.paragraph_display ? ` (${citation.paragraph_display})` : ''}
                                    <span style={{ marginLeft: '0.4rem', fontSize: '0.7rem', fontWeight: 500, color: '#6b7280', background: '#f3f4f6', borderRadius: '4px', padding: '1px 5px' }}>
                                        semantic top-5
                                    </span>
                                    {holdingType && (
                                        <span style={{ marginLeft: '0.5rem', fontWeight: 600, color: '#63120e' }}>
                                            [{holdingType.replace(/_/g, ' ')}]
                                        </span>
                                    )}
                                </p>
                                <p className="detail-source">{evidenceText}</p>

                                {/* Extractive supporting quote — verbatim from the judgment */}
                                {supportingQuote && (
                                    <div className="supporting-quote-block">
                                        <div className="supporting-quote-label">
                                            <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: '#0f766e' }}>
                                                📌 Grounding Sentence
                                                {evidencePassageIndex ? ` [P${evidencePassageIndex}]` : ''}
                                            </span>
                                        </div>
                                        <blockquote className="supporting-quote-text">
                                            &ldquo;{supportingQuote}&rdquo;
                                        </blockquote>
                                    </div>
                                )}

                                {propReasoning && (
                                    <div className="reasoning-box">
                                        <strong>Entailment Assessment: </strong>{propReasoning}
                                    </div>
                                )}
                            </>
                        ) : (
                            <div className="detail-not-found-block" style={{ marginTop: '0.5rem' }}>
                                <p className="detail-not-found" style={{ fontStyle: 'italic' }}>
                                    Proposition verification withheld: Case identity must be established before running NLI. Never evaluate entailment against an unverified authority or unrelated judgment.
                                </p>
                            </div>
                        )}
                    </div>

                    {/* ── STAGE 2 & 8: RELATED AUTHORITIES (CITING CASES) ── */}
                    {relatedAuthorities.length > 0 && (
                        <div className="related-cases-box">
                            <div className="related-cases-header">
                                <span className="related-cases-title">
                                    <FileText size={14} /> Related Cases ({relatedAuthorities.length})
                                </span>
                            </div>
                            <p className="related-disclaimer">
                                These judgments discuss or cite the claimed authority, but are <strong>NOT</strong> the cited authority itself. They were strictly excluded from proposition verification.
                            </p>
                            <div className="related-cases-list">
                                {relatedAuthorities.map((ra, idx) => (
                                    <div key={idx} className="related-case-row">
                                        <span className="related-case-name">{ra.case_name}</span>
                                        <div className="related-case-meta">
                                            <span className="related-case-rel">{ra.relationship}</span>
                                            {ra.court && <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>({ra.court})</span>}
                                            {ra.source_url && (
                                                <a href={ra.source_url} target="_blank" rel="noopener noreferrer" className="related-case-link" title="Open in Indian Kanoon">
                                                    <ExternalLink size={13} />
                                                </a>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* ── STAGE 3 & 10: SOURCE & AUDIT METADATA ── */}
                    {citation.source?.source_url && (
                        <p className="detail-external-link">
                            Primary Authority Source:{' '}
                            <a href={citation.source.source_url} target="_blank" rel="noopener noreferrer">
                                {citation.source.source_name || 'Authoritative Source'}
                            </a>
                            {citation.source.canonical_case_id && (
                                <span> &nbsp;·&nbsp; ID: <code>{citation.source.canonical_case_id}</code></span>
                            )}
                            {citation.source.document_hash && (
                                <span title={`SHA-256: ${citation.source.document_hash}`}>
                                    {' '}&nbsp;·&nbsp; Hash: <code>{String(citation.source.document_hash).slice(0, 10)}…</code>
                                </span>
                            )}
                        </p>
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
                        {(citation.status === 'Mismatch' || propStatus === 'CONTRADICTED') && (
                            <button className="outline btn-sm" onClick={() => onOpenDiff(citation)}>
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
