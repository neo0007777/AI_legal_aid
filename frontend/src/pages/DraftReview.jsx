import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import './DraftReview.css';
import {
    FileCheck, UploadCloud, AlertTriangle, AlertCircle, CheckCircle2, Sparkles,
    ShieldAlert, RefreshCw, FileText, ArrowRight, Wand2, Check, Copy, Download
} from 'lucide-react';
import TranslateAction from '../components/TranslateAction';

const buildReviewSummaryText = (report) => {
    if (!report) return '';
    const parts = [`Document type: ${report.document_type}. Risk level: ${report.risk_level}. Score: ${report.overall_score}/100.`, report.summary];
    if (report.missing_sections?.length) parts.push(`Missing mandatory sections: ${report.missing_sections.join(', ')}.`);
    if (report.missing_fields?.length) parts.push(`Unfilled placeholders: ${report.missing_fields.map(f => f.placeholder).join(', ')}.`);
    const allIssues = [...(report.critical || []), ...(report.warnings || []), ...(report.suggestions || [])];
    allIssues.forEach(issue => {
        parts.push(`${issue.title}: ${issue.description}${issue.suggested_fix ? ` Fix: ${issue.suggested_fix}` : ''}`);
    });
    return parts.join('\n\n');
};

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const DraftReview = () => {
    const location = useLocation();
    const [draftText, setDraftText] = useState(location.state?.draft || '');
    const [documentType, setDocumentType] = useState('auto');
    const [selectedFile, setSelectedFile] = useState(null);

    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [isFixing, setIsFixing] = useState(false);

    const [reviewReport, setReviewReport] = useState(location.state?.review || null);
    const [correctedDraft, setCorrectedDraft] = useState(null);
    const [changesMade, setChangesMade] = useState([]);
    const [copied, setCopied] = useState(false);

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
            alert("Please paste a legal draft or upload a document file (.pdf, .docx, .txt, .rtf).");
            return;
        }

        setIsAnalyzing(true);
        setReviewReport(null);
        setCorrectedDraft(null);

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
                    body: formData,
                });
            } else {
                response = await fetch(`${API_BASE_URL}/review/analyze`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
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

        setIsFixing(true);

        const allIssues = [
            ...(reviewReport.critical || []),
            ...(reviewReport.warnings || []),
            ...(reviewReport.suggestions || [])
        ];

        try {
            const response = await fetch(`${API_BASE_URL}/review/fix`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    draft: draftText || (selectedFile ? "Uploaded Document Text" : ""),
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

    const handleCopyFix = () => {
        if (correctedDraft) {
            navigator.clipboard.writeText(correctedDraft);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const getScoreColor = (score) => {
        if (score >= 85) return '#10B981';
        if (score >= 60) return '#c98659';
        return '#EF4444';
    };

    const getRiskBadge = (risk) => {
        if (risk === 'Low') return <span className="badge-risk low"><CheckCircle2 size={14} /> Low Risk</span>;
        if (risk === 'Medium') return <span className="badge-risk medium"><AlertCircle size={14} /> Medium Risk</span>;
        return <span className="badge-risk high"><ShieldAlert size={14} /> High Risk</span>;
    };

    return (
        <div className="review-wrapper animate-fade-in">
            {/* Header */}
            <div className="review-header">
                <div>
                    <div className="badge-chip">
                        <FileCheck size={16} />
                        <span>Universal AI Legal Review Engine</span>
                    </div>
                    <h2>Legal Draft Review & Auto-Fix</h2>
                    <p className="subtitle">
                        RAG-powered hybrid analysis comparing your draft against 50M+ precedents and 1,800+ landmark templates.
                    </p>
                </div>
            </div>

            {/* Main Layout Grid */}
            <div className="review-grid">
                {/* Left Panel: Input & Controls */}
                <div className="review-input-card">
                    <h3>1. Select Input Method</h3>

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
                                    <p className="drop-title">Upload Draft (.pdf, .docx, .txt, .rtf)</p>
                                    <p className="drop-sub">Drag & drop or click to browse file</p>
                                </div>
                            )}
                        </label>
                    </div>

                    <div className="divider-text"><span>OR PASTE TEXT BELOW</span></div>

                    {/* Textarea */}
                    <textarea
                        className="draft-textarea"
                        placeholder="Paste legal petition, contract, affidavit, or notice here..."
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
                                <RefreshCw size={18} className="spin" /> Comparing against Qdrant Templates...
                            </>
                        ) : (
                            <>
                                <Sparkles size={18} /> Run AI Legal Review Engine
                            </>
                        )}
                    </button>
                </div>

                {/* Right Panel: Review Report Results */}
                <div className="review-results-card">
                    {!reviewReport && !isAnalyzing && (
                        <div className="empty-review-placeholder">
                            <FileCheck size={48} strokeWidth={1.2} />
                            <h4>No Review Analysis Generated</h4>
                            <p>Upload a document or paste text on the left to run the hybrid rule & RAG legal review pipeline.</p>
                        </div>
                    )}

                    {isAnalyzing && (
                        <div className="review-analyzing-state">
                            <RefreshCw size={40} className="spin text-gold" />
                            <h4>Analyzing Document & Retrieving Top-5 Qdrant Templates...</h4>
                            <p>Scanning structural sections, placeholders, legal reasoning, and precedent compliance.</p>
                        </div>
                    )}

                    {reviewReport && (
                        <div className="review-report-container animate-fade-in">
                            {/* Score & Summary Banner */}
                            <div className="report-summary-banner">
                                <div className="score-circle-wrapper">
                                    <div
                                        className="score-circle"
                                        style={{ borderColor: getScoreColor(reviewReport.overall_score) }}
                                    >
                                        <span className="score-num" style={{ color: getScoreColor(reviewReport.overall_score) }}>
                                            {reviewReport.overall_score}
                                        </span>
                                        <span className="score-denom">/ 100</span>
                                    </div>
                                </div>

                                <div className="summary-details">
                                    <div className="summary-top-row">
                                        <span className="doc-type-tag">{reviewReport.document_type}</span>
                                        {getRiskBadge(reviewReport.risk_level)}
                                    </div>
                                    <p className="summary-text">{reviewReport.summary}</p>
                                </div>
                            </div>

                            {/* Missing Sections & Placeholders */}
                            {(reviewReport.missing_sections.length > 0 || reviewReport.missing_fields.length > 0) && (
                                <div className="missing-elements-section">
                                    {reviewReport.missing_sections.length > 0 && (
                                        <div className="missing-card">
                                            <h5><AlertTriangle size={16} /> Missing Mandatory Sections ({reviewReport.missing_sections.length})</h5>
                                            <div className="tags-flex">
                                                {reviewReport.missing_sections.map((sec, idx) => (
                                                    <span key={idx} className="tag-missing-sec">{sec}</span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {reviewReport.missing_fields.length > 0 && (
                                        <div className="missing-card mt-2">
                                            <h5><AlertCircle size={16} /> Unfilled Bracket Placeholders ({reviewReport.missing_fields.length})</h5>
                                            <div className="tags-flex">
                                                {reviewReport.missing_fields.map((mf, idx) => (
                                                    <span key={idx} className="tag-missing-field">{mf.placeholder}</span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Detailed Issues List */}
                            <div className="issues-list-wrapper">
                                <h4>Detected Legal & Structural Issues</h4>

                                {reviewReport.critical.map((issue) => (
                                    <div key={issue.id} className="issue-item critical">
                                        <div className="issue-badge red">CRITICAL</div>
                                        <div>
                                            <h6>{issue.title}</h6>
                                            <p>{issue.description}</p>
                                            {issue.suggested_fix && <div className="suggested-fix-box"><strong>Fix Recommendation:</strong> {issue.suggested_fix}</div>}
                                        </div>
                                    </div>
                                ))}

                                {reviewReport.warnings.map((issue) => (
                                    <div key={issue.id} className="issue-item warning">
                                        <div className="issue-badge amber">WARNING</div>
                                        <div>
                                            <h6>{issue.title}</h6>
                                            <p>{issue.description}</p>
                                            {issue.suggested_fix && <div className="suggested-fix-box"><strong>Fix Recommendation:</strong> {issue.suggested_fix}</div>}
                                        </div>
                                    </div>
                                ))}

                                {reviewReport.suggestions.map((issue) => (
                                    <div key={issue.id} className="issue-item suggestion">
                                        <div className="issue-badge blue">SUGGESTION</div>
                                        <div>
                                            <h6>{issue.title}</h6>
                                            <p>{issue.description}</p>
                                            {issue.suggested_fix && <div className="suggested-fix-box"><strong>Fix Recommendation:</strong> {issue.suggested_fix}</div>}
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
                                            <RefreshCw size={18} className="spin" /> Fixing Detected Issues & Preserving Layout...
                                        </>
                                    ) : (
                                        <>
                                            <Wand2 size={18} /> Auto-Fix Detected Issues
                                        </>
                                    )}
                                </button>
                            </div>

                            <TranslateAction
                                sourceType="draft_review"
                                text={buildReviewSummaryText(reviewReport)}
                                citations={[]}
                            />
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
                            <h3>Auto-Fixed Corrected Draft</h3>
                        </div>
                        <div className="flex-align gap-2">
                            <button className="secondary-btn btn-sm" onClick={handleCopyFix}>
                                {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? 'Copied' : 'Copy Corrected Draft'}
                            </button>
                        </div>
                    </div>

                    {changesMade.length > 0 && (
                        <div className="changes-summary-box">
                            <strong>Applied Remediation Actions:</strong>
                            <ul>
                                {changesMade.map((ch, idx) => (
                                    <li key={idx}>{ch}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="split-comparison-grid">
                        <div className="split-pane">
                            <h5>Original Draft</h5>
                            <pre className="draft-pre-box">{draftText || "Uploaded File Draft"}</pre>
                        </div>
                        <div className="split-pane fixed-pane">
                            <h5>Corrected Draft (Preserved Layout)</h5>
                            <pre className="draft-pre-box corrected">{correctedDraft}</pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DraftReview;
