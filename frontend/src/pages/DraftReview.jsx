import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../context/AuthContext';
import { downloadFileFromBlob, exportPdfFromApi } from '../utils/downloadHelper';
import './DraftReview.css';
import {
    FileCheck, UploadCloud, AlertTriangle, AlertCircle, CheckCircle2, Sparkles,
    ShieldAlert, RefreshCw, FileText, ArrowRight, Wand2, Check, Copy, Download,
    Loader2, FileDown
} from 'lucide-react';

const SAMPLE_DRAFT = `IN THE COURT OF THE SESSIONS JUDGE AT NEW DELHI
BAIL APPLICATION NO. ______ OF 2024

IN THE MATTER OF:
RAMESH KUMAR, S/o Shri Surender Kumar,
R/o House No. 42, Model Town, Delhi-110009
... APPLICANT / ACCUSED

VERSUS

STATE (NCT OF DELHI)
... RESPONDENT

FIR NO.: 112/2024
UNDER SECTIONS: 420, 406 IPC (NOW CORRESPONDING TO 318(4), 316 BNS, 2023)
POLICE STATION: MODEL TOWN, DELHI

APPLICATION UNDER SECTION 439 OF THE CODE OF CRIMINAL PROCEDURE, 1973 (CORRESPONDING TO SECTION 483 OF BHARATIYA NAGARIK SURAKSHA SANHITA, 2023) FOR GRANT OF REGULAR BAIL

MOST RESPECTFULLY SHOWETH:
1. That the Applicant is a law-abiding citizen of India residing at the aforementioned address and has no prior criminal antecedents.
2. That the Applicant has been falsely implicated in FIR No. 112/2024 registered at P.S. Model Town for alleged offences under Sections 420/406 IPC.
3. That the Applicant was arrested on [DATE] and has been in judicial custody since [DATE].
4. That the investigation is substantially complete, custodial interrogation is no longer required, and the alleged offences are triable by Magistrate.
5. That the Applicant undertakes to abide by all conditions imposed by this Hon'ble Court and will not tamper with prosecution evidence or influence witnesses.

PRAYER:
Wherefore, it is most respectfully prayed that this Hon'ble Court may graciously be pleased to:
a) Release the Applicant on regular bail in FIR No. 112/2024, P.S. Model Town;
b) Pass any other or further order as this Hon'ble Court may deem fit and proper in the interest of justice.

APPLICANT
THROUGH COUNSEL
ADVOCATE FOR APPLICANT`;

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const DraftReview = () => {
    const location = useLocation();
    const { t } = useTranslation();
    const { getAuthHeaders } = useAuth();

    const [draftText, setDraftText] = useState(location.state?.draft || '');
    const [documentType, setDocumentType] = useState('auto');
    const [selectedFile, setSelectedFile] = useState(null);

    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [isFixing, setIsFixing] = useState(false);

    // English source-of-truth review report
    const [reviewReport, setReviewReport] = useState(location.state?.review || null);

    // Auto-fix states
    const [correctedDraft, setCorrectedDraft] = useState(null);
    const [changesMade, setChangesMade] = useState([]);

    const [copied, setCopied] = useState(false);
    const [isExportingPdf, setIsExportingPdf] = useState(false);

    useEffect(() => {
        if (location.state?.draft) {
            setDraftText(location.state.draft);
        }
        if (location.state?.review) {
            setReviewReport(location.state.review);
        }
    }, [location.state]);

    // Handle File Upload
    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            setSelectedFile(file);
        }
    };

    // Run Universal Review Engine
    const handleRunReview = async () => {
        if (!draftText.trim() && !selectedFile) {
            alert(t('draftReview.placeholder', 'Please paste a legal draft or upload a document file (.pdf, .docx, .txt, .rtf).'));
            return;
        }

        setIsAnalyzing(true);
        setReviewReport(null);
        setCorrectedDraft(null);
        setChangesMade([]);

        try {
            let response;
            if (selectedFile) {
                const formData = new FormData();
                formData.append('file', selectedFile);
                if (documentType && documentType !== 'auto') {
                    formData.append('document_type', documentType);
                }
                response = await fetch(`${API_BASE_URL}/review/file`, {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: formData,
                });
            } else {
                response = await fetch(`${API_BASE_URL}/review/analyze`, {
                    method: 'POST',
                    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        draft: draftText,
                        document_type: documentType === 'auto' ? null : documentType
                    }),
                });
            }

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Review engine analysis failed');
            }

            const data = await response.json();
            setReviewReport(data);
            if (data.extracted_text) {
                setDraftText(data.extracted_text);
            }
        } catch (error) {
            console.error('Review Error:', error);
            alert(`Review Engine error: ${error.message}`);
        } finally {
            setIsAnalyzing(false);
        }
    };

    // Run Auto Fix Engine
    const handleRunAutoFix = async () => {
        if (!reviewReport) return;
        const currentDraft = draftText.trim();
        if (!currentDraft && !selectedFile) {
            alert('Cannot auto-fix without original draft text. Please paste draft or upload document.');
            return;
        }

        setIsFixing(true);

        const allIssues = [
            ...(reviewReport.critical || []),
            ...(reviewReport.warnings || []),
            ...(reviewReport.suggestions || [])
        ];

        try {
            const response = await fetch(`${API_BASE_URL}/review/fix`, {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    draft: currentDraft || (selectedFile ? "Uploaded Document Text" : ""),
                    issues: allIssues,
                    missing_sections: reviewReport.missing_sections || [],
                    missing_fields: reviewReport.missing_fields || []
                }),
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Auto-fix engine failed');
            }

            const data = await response.json();
            setCorrectedDraft(data.corrected_draft);
            setChangesMade(data.changes_made || []);
        } catch (error) {
            console.error('Auto Fix Error:', error);
            alert(`Auto Fix Error: ${error.message}`);
        } finally {
            setIsFixing(false);
        }
    };

    // Active views
    const activeReport = reviewReport;
    const activeChanges = changesMade;
    const activeCorrectedText = correctedDraft;

    const handleCopyFix = () => {
        if (activeCorrectedText) {
            navigator.clipboard.writeText(activeCorrectedText);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const handleDownloadTxt = () => {
        if (!activeCorrectedText) return;
        const blob = new Blob([activeCorrectedText], { type: 'text/plain;charset=utf-8' });
        downloadFileFromBlob(blob, `LexSetu_Corrected_Draft_${Date.now()}.txt`, 'text/plain');
    };

    const handleExportPdf = async () => {
        if (!activeCorrectedText) return;
        setIsExportingPdf(true);
        try {
            const docType = activeReport?.document_type || 'Reviewed Court Draft';
            await exportPdfFromApi({
                endpoint: '/api/documents/export-pdf',
                body: {
                    title: docType,
                    draft_text: activeCorrectedText,
                    court_name: 'IN THE COMPETENT COURT OF JURISDICTION',
                    case_number: 'APPLICATION / PETITION NO. _____ OF 2026',
                    applicant: 'APPLICANT / PETITIONER',
                    respondent: 'RESPONDENT / OPPOSITE PARTY',
                },
                filename: `LexSetu_Corrected_${docType.replace(/\s+/g, '_')}.pdf`,
                headers: getAuthHeaders(),
            });
        } catch (err) {
            console.error('PDF export error:', err);
            alert('Failed to export PDF: ' + err.message);
        } finally {
            setIsExportingPdf(false);
        }
    };

    const getScoreColor = (score) => {
        if (score >= 85) return '#10B981';
        if (score >= 60) return '#c98659';
        return '#EF4444';
    };

    const getRiskBadge = (risk) => {
        if (risk === 'Low') return <span className="badge-risk low"><CheckCircle2 size={14} /> {t('draftReview.lowRisk', 'Low Risk')}</span>;
        if (risk === 'Medium') return <span className="badge-risk medium"><AlertCircle size={14} /> {t('draftReview.mediumRisk', 'Medium Risk')}</span>;
        return <span className="badge-risk high"><ShieldAlert size={14} /> {t('draftReview.highRisk', 'High Risk')}</span>;
    };

    return (
        <div className="review-wrapper animate-fade-in">
            {/* Header */}
            <div className="review-header">
                <div>
                    <div className="badge-chip">
                        <FileCheck size={16} />
                        <span>{t('draftReview.badge', 'Universal AI Legal Review Engine')}</span>
                    </div>
                    <h2>{t('draftReview.title', 'Legal Draft Review & Auto-Fix')}</h2>
                    <p className="subtitle">
                        {t('draftReview.subtitle', 'RAG-powered hybrid analysis comparing your draft against 50M+ precedents and 1,800+ landmark templates.')}
                    </p>
                </div>
            </div>

            {/* Main Layout Grid */}
            <div className="review-grid">
                {/* Left Panel: Input & Controls */}
                <div className="review-input-card">
                    <h3>{t('draftReview.selectInput', '1. Select Input Method')}</h3>

                    {/* Document Category Dropdown */}
                    <div className="doc-type-selector-box">
                        <label htmlFor="doc-type-select" className="input-label-sm">
                            {t('draftReview.docTypeLabel', 'Document Category / Context:')}
                        </label>
                        <select
                            id="doc-type-select"
                            className="doc-type-select"
                            value={documentType}
                            onChange={(e) => setDocumentType(e.target.value)}
                        >
                            <option value="auto">⚡ Auto-Detect Document Type</option>
                            <option value="Bail Application">Bail Application (BNSS / CrPC)</option>
                            <option value="Anticipatory Bail Application">Anticipatory Bail Application</option>
                            <option value="Legal Notice">Legal Notice / Demand Notice</option>
                            <option value="Reply to Legal Notice">Reply to Legal Notice</option>
                            <option value="Affidavit">Affidavit</option>
                            <option value="Lease / Rent Agreement">Lease / Rent Agreement</option>
                            <option value="Civil Suit / Plaint">Civil Suit / Plaint</option>
                            <option value="Writ Petition">Writ Petition</option>
                            <option value="Section 138 NI Act Complaint">Section 138 NI Act (Cheque Bounce)</option>
                            <option value="NDA / Confidentiality Agreement">NDA / Confidentiality Agreement</option>
                            <option value="Employment Agreement">Employment Agreement</option>
                            <option value="Power of Attorney">Power of Attorney</option>
                            <option value="Sale Deed">Sale Deed</option>
                        </select>
                    </div>

                    {/* File Upload Zone */}
                    <div className="file-upload-box">
                        <input
                            type="file"
                            id="review-file-input"
                            accept=".pdf,.docx,.rtf,.txt"
                            onChange={handleFileChange}
                            style={{ display: 'none' }}
                        />
                        <label htmlFor="review-file-input" className="file-drop-area">
                            <UploadCloud size={32} className="upload-icon" />
                            {selectedFile ? (
                                <div className="selected-file-info">
                                    <strong>{selectedFile.name}</strong>
                                    <span>({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                                </div>
                            ) : (
                                <div>
                                    <p className="drop-title">{t('draftReview.uploadTitle', 'Upload Draft (.pdf, .docx, .txt, .rtf)')}</p>
                                    <p className="drop-sub">{t('draftReview.uploadSub', 'Drag & drop or click to browse file')}</p>
                                </div>
                            )}
                        </label>
                    </div>

                    <div className="divider-text"><span>{t('draftReview.orPaste', 'OR PASTE TEXT BELOW')}</span></div>

                    <div className="paste-header-row">
                        <span className="text-muted-sm">{t('draftReview.pasteDraftDesc', 'Paste draft text or load a template:')}</span>
                        <button
                            type="button"
                            className="btn-sample-link"
                            onClick={() => {
                                setDraftText(SAMPLE_DRAFT);
                                setSelectedFile(null);
                                setDocumentType('Bail Application');
                            }}
                            title="Load pre-configured sample bail draft"
                        >
                            <FileText size={13} /> {t('draftReview.loadSample', 'Load Sample Draft')}
                        </button>
                    </div>

                    {/* Textarea */}
                    <textarea
                        className="draft-textarea"
                        placeholder={t('draftReview.placeholder', 'Paste legal petition, contract, affidavit, or notice here...')}
                        value={draftText}
                        onChange={(e) => {
                            setDraftText(e.target.value);
                            if (selectedFile) setSelectedFile(null);
                        }}
                        rows={12}
                    />

                    <button
                        className="primary-btn run-review-btn"
                        onClick={handleRunReview}
                        disabled={isAnalyzing}
                    >
                        {isAnalyzing ? (
                            <>
                                <RefreshCw size={18} className="spin" /> {t('draftReview.comparing', 'Comparing against Qdrant Templates...')}
                            </>
                        ) : (
                            <>
                                <Sparkles size={18} /> {t('draftReview.runReview', 'Run AI Legal Review Engine')}
                            </>
                        )}
                    </button>
                </div>

                {/* Right Panel: Review Report Results */}
                <div className="review-results-card">
                    {!reviewReport && !isAnalyzing && (
                        <div className="empty-review-placeholder">
                            <FileCheck size={48} strokeWidth={1.2} />
                            <h4>{t('draftReview.noReviewTitle', 'No Review Analysis Generated')}</h4>
                            <p>{t('draftReview.noReviewDesc', 'Upload a document or paste text on the left to run the hybrid rule & RAG legal review pipeline.')}</p>
                        </div>
                    )}

                    {isAnalyzing && (
                        <div className="review-analyzing-state">
                            <RefreshCw size={40} className="spin text-gold" />
                            <h4>{t('draftReview.analyzingTitle', 'Analyzing Document & Retrieving Top-5 Qdrant Templates...')}</h4>
                            <p>{t('draftReview.analyzingDesc', 'Scanning structural sections, placeholders, legal reasoning, and precedent compliance.')}</p>
                        </div>
                    )}

                    {activeReport && (
                        <div className="review-report-container animate-fade-in">
                            {/* Score & Summary Banner */}
                            <div className="report-summary-banner">
                                <div className="score-circle-wrapper">
                                    <div
                                        className="score-circle"
                                        style={{ borderColor: getScoreColor(activeReport.overall_score) }}
                                    >
                                        <span className="score-num" style={{ color: getScoreColor(activeReport.overall_score) }}>
                                            {activeReport.overall_score}
                                        </span>
                                        <span className="score-denom">/ 100</span>
                                    </div>
                                </div>

                                <div className="summary-details">
                                    <div className="summary-top-row">
                                        <span className="doc-type-tag">{activeReport.document_type}</span>
                                        {getRiskBadge(activeReport.risk_level)}
                                    </div>
                                    <p className="summary-text">{activeReport.summary}</p>
                                </div>
                            </div>

                            {/* Missing Sections & Placeholders */}
                            {(activeReport.missing_sections?.length > 0 || activeReport.missing_fields?.length > 0) && (
                                <div className="missing-elements-section">
                                    {activeReport.missing_sections?.length > 0 && (
                                        <div className="missing-card">
                                            <h5><AlertTriangle size={16} /> {t('draftReview.missingSections', { count: activeReport.missing_sections.length, defaultValue: `Missing Mandatory Sections (${activeReport.missing_sections.length})` })}</h5>
                                            <div className="tags-flex">
                                                {activeReport.missing_sections.map((sec, idx) => (
                                                    <span key={idx} className="tag-missing-sec">{sec}</span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {activeReport.missing_fields?.length > 0 && (
                                        <div className="missing-card mt-2">
                                            <h5><AlertCircle size={16} /> {t('draftReview.unfilledPlaceholders', { count: activeReport.missing_fields.length, defaultValue: `Unfilled Bracket Placeholders (${activeReport.missing_fields.length})` })}</h5>
                                            <div className="tags-flex">
                                                {activeReport.missing_fields.map((mf, idx) => (
                                                    <span key={idx} className="tag-missing-field">{mf.placeholder}</span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Detailed Issues List */}
                            <div className="issues-list-wrapper">
                                <h4>{t('draftReview.detectedIssues', 'Detected Legal & Structural Issues')}</h4>

                                {(activeReport.critical || []).map((issue) => (
                                    <div key={issue.id || Math.random()} className="issue-item critical">
                                        <div className="issue-badge red">{t('draftReview.criticalBadge', 'CRITICAL')}</div>
                                        <div>
                                            <h6>{issue.title}</h6>
                                            <p>{issue.description}</p>
                                            {issue.suggested_fix && <div className="suggested-fix-box"><strong>{t('draftReview.fixRecommendation', 'Fix Recommendation:')}</strong> {issue.suggested_fix}</div>}
                                        </div>
                                    </div>
                                ))}

                                {(activeReport.warnings || []).map((issue) => (
                                    <div key={issue.id || Math.random()} className="issue-item warning">
                                        <div className="issue-badge amber">{t('draftReview.warningBadge', 'WARNING')}</div>
                                        <div>
                                            <h6>{issue.title}</h6>
                                            <p>{issue.description}</p>
                                            {issue.suggested_fix && <div className="suggested-fix-box"><strong>{t('draftReview.fixRecommendation', 'Fix Recommendation:')}</strong> {issue.suggested_fix}</div>}
                                        </div>
                                    </div>
                                ))}

                                {(activeReport.suggestions || []).map((issue) => (
                                    <div key={issue.id || Math.random()} className="issue-item suggestion">
                                        <div className="issue-badge blue">{t('draftReview.suggestionBadge', 'SUGGESTION')}</div>
                                        <div>
                                            <h6>{issue.title}</h6>
                                            <p>{issue.description}</p>
                                            {issue.suggested_fix && <div className="suggested-fix-box"><strong>{t('draftReview.fixRecommendation', 'Fix Recommendation:')}</strong> {issue.suggested_fix}</div>}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Auto Fix Trigger */}
                            <div className="autofix-action-bar">
                                <button
                                    className="primary-btn autofix-btn"
                                    onClick={handleRunAutoFix}
                                    disabled={isFixing}
                                >
                                    {isFixing ? (
                                        <>
                                            <RefreshCw size={18} className="spin" /> {t('draftReview.fixingStatus', 'Fixing Detected Issues & Preserving Layout...')}
                                        </>
                                    ) : (
                                        <>
                                            <Wand2 size={18} /> {t('draftReview.autoFixBtn', 'Auto-Fix Detected Issues')}
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Side by Side Corrected Draft Comparison Modal / View */}
            {correctedDraft && (
                <div className="corrected-draft-view mt-4 animate-fade-in">
                    <div className="corrected-header">
                        <div className="flex-align">
                            <Sparkles size={20} className="text-gold" />
                            <h3>{t('draftReview.autoFixedTitle', 'Auto-Fixed Corrected Draft')}</h3>
                        </div>
                        <div className="flex-align gap-2">
                            <button className="secondary-btn btn-sm" onClick={handleDownloadTxt} title={t('draftReview.downloadTxt', 'Download as .txt')}>
                                <Download size={15} /> {t('draftReview.downloadTxt', 'Download .txt')}
                            </button>
                            <button className="secondary-btn btn-sm" onClick={handleExportPdf} disabled={isExportingPdf} title={t('draftReview.exportPdf', 'Export Court-Ready PDF')}>
                                {isExportingPdf ? <Loader2 size={15} className="spin" /> : <FileDown size={15} />}
                                {t('draftReview.exportPdf', 'Export Court PDF')}
                            </button>
                            <button className="secondary-btn btn-sm" onClick={handleCopyFix}>
                                {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? t('draftReview.copied', 'Copied') : t('draftReview.copyFix', 'Copy Corrected Draft')}
                            </button>
                        </div>
                    </div>

                    {activeChanges.length > 0 && (
                        <div className="changes-summary-box">
                            <strong>{t('draftReview.appliedRemediation', 'Applied Remediation Actions:')}</strong>
                            <ul>
                                {activeChanges.map((ch, idx) => (
                                    <li key={idx}>{ch}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="split-comparison-grid">
                        <div className="split-pane">
                            <h5>{t('draftReview.originalDraft', 'Original Draft')}</h5>
                            <pre className="draft-pre-box">{draftText || t('draftReview.uploadedFileDraft', 'Uploaded File Draft')}</pre>
                        </div>
                        <div className="split-pane fixed-pane">
                            <h5>{t('draftReview.correctedDraft', 'Corrected Draft (Preserved Layout)')}</h5>
                            <pre className="draft-pre-box corrected">{activeCorrectedText}</pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DraftReview;
