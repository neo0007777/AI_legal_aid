import { useState, useRef, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
    FileText, Wand2, Download, Copy, RefreshCw, Edit3,
    Sparkles, CornerDownRight, Check, Loader2, ShieldAlert, AlertOctagon,
    Scale, BookmarkMinus, Briefcase, Users, Lock, FileSignature,
    AlertTriangle, ChevronLeft, ChevronRight, FileCheck, CheckCircle2,
    Info, CircleAlert, Eye, FileDown
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLocalMode } from '../context/LocalModeContext';
import VoiceInputButton from '../components/VoiceInputButton';
import PrivilegeShield from '../components/PrivilegeShield';
import { downloadFileFromBlob, exportPdfFromApi } from '../utils/downloadHelper';
import PipelineStageList from '../components/PipelineStageList';
import { useStageStream } from '../hooks/useStageStream';
import './DraftAssistant.css';

// Real, distinct steps backend/routes/documents.py's /draft stream actually emits
const DRAFT_STAGE_ORDER = ['building_manifest', 'resolving_statutes', 'retrieving_templates', 'generating_draft', 'verifying_draft'];
const DRAFT_STAGE_LABELS = {
    building_manifest: 'Building fact manifest & procedural posture',
    resolving_statutes: 'Resolving & locking statutory sources',
    retrieving_templates: 'Retrieving matching templates',
    generating_draft: 'Generating draft',
    verifying_draft: 'Verifying statute citations & source-lock consistency',
};

export const sanitizeDraftText = (text) => {
    if (!text) return '';
    return text
        .replace(/^#{1,6}\s*/gm, '')
        .replace(/\*\*\*([^*]+)\*\*\*/g, '$1')
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/\*([^*]+)\*/g, '$1')
        .replace(/___([^_]+)___/g, '$1')
        .replace(/__([^_]+)__/g, '$1')
        .replace(/_([^_]+)_/g, '$1')
        .replace(/^(\s*[-*_]\s*){3,}$/gm, '----------------------------------------')
        .replace(/\*\*/g, '')
        .replace(/(?<=\s)\*(?=\s)/g, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
};

const renderInlineContent = (text) => {
    if (!text) return null;
    const regex = /(\[(?:NOT PROVIDED|REQUIRES VERIFICATION|CITATION REQUIRES VERIFICATION|CASE-SPECIFIC GROUND REQUIRES SUPPORTING FACTS)[^\]]*\]|【(?:USER_FACT|DOCUMENT_FACT|VERIFIED_LEGAL_RULE)[^】]*】|\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_)/g;
    const parts = text.split(regex);

    return parts.map((part, index) => {
        if (!part) return null;

        if (part.startsWith('[') && part.endsWith(']')) {
            const inner = part.slice(1, -1);
            const isMissing = inner.includes('NOT PROVIDED');
            return (
                <span
                    key={index}
                    className={isMissing ? 'court-tag-missing' : 'court-tag-verification'}
                    title={isMissing ? 'Information not provided in input' : 'Requires verification with case files'}
                >
                    {isMissing ? <AlertTriangle size={11} className="court-tag-icon" /> : <CircleAlert size={11} className="court-tag-icon" />}
                    <span>{inner}</span>
                </span>
            );
        }

        if (part.startsWith('【') && part.endsWith('】')) {
            const inner = part.slice(1, -1);
            return (
                <span key={index} className="court-tag-fact" title="Grounded verification category">
                    {inner}
                </span>
            );
        }

        if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
            const content = part.slice(2, -2).trim();
            return <strong key={index} className="court-strong">{content}</strong>;
        }

        if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
            const content = part.slice(1, -1).trim();
            return <em key={index} className="court-italic">{content}</em>;
        }

        if (part.startsWith('_') && part.endsWith('_') && part.length >= 2) {
            const content = part.slice(1, -1).trim();
            return <em key={index} className="court-italic">{content}</em>;
        }

        const cleaned = part.replace(/\*\*/g, '').replace(/(?<=\s)\*(?=\s)/g, '');
        return <span key={index}>{cleaned}</span>;
    });
};

const renderCourtDocument = (text) => {
    if (!text) return null;
    const lines = text.split('\n');
    const elements = [];
    let tableRows = [];
    let inTable = false;

    const flushTable = (key) => {
        if (tableRows.length > 0) {
            const isHeader = tableRows[0];
            const dataRows = tableRows.slice(1).filter(r => !r.every(c => /^[-:\s]+$/.test(c)));
            elements.push(
                <div key={`table-${key}`} className="court-table-wrapper">
                    <table className="court-table">
                        <thead>
                            <tr>
                                {isHeader.map((h, i) => (
                                    <th key={i}>{renderInlineContent(h)}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {dataRows.map((row, ri) => (
                                <tr key={ri}>
                                    {row.map((cell, ci) => (
                                        <td key={ci}>{renderInlineContent(cell)}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            );
            tableRows = [];
            inTable = false;
        }
    };

    lines.forEach((rawLine, idx) => {
        const trimmed = rawLine.trim();

        // Check if markdown table line: e.g. | col1 | col2 |
        if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
            const cells = trimmed.split('|').slice(1, -1).map(c => c.trim());
            tableRows.push(cells);
            inTable = true;
            return;
        } else if (inTable) {
            flushTable(idx);
        }

        if (!trimmed) {
            elements.push(<div key={idx} className="court-spacer" />);
            return;
        }

        if (/^(\s*[-*_]\s*){3,}$/.test(trimmed)) {
            elements.push(<hr key={idx} className="court-divider" />);
            return;
        }

        const cleanLine = trimmed.replace(/^#{1,6}\s*/, '');

        if (/^(SECTION\s+[I|V|X\d]+:?\s*)?(\d+\.\s+)?(Synopsis|List of Dates|Heading\s*\/\s*Cause Title|Memo of Parties|Verified Case Information|Factual Background|Factual Matrix|Application|Legal Grounds|Prayer|Index of Annexures|Affidavit|Verification)/i.test(cleanLine)) {
            const badgeText = cleanLine.replace(/\*\*/g, '').trim();
            elements.push(
                <div key={idx} className="court-section-guide">
                    <span className="court-guide-pill">{badgeText}</span>
                </div>
            );
            return;
        }

        if (/^(IN THE COURT OF|BEFORE THE|IN THE HIGH COURT|IN THE SUPREME COURT|COURT OF THE|AT\s+[A-Z\s,]+|BAIL APPLICATION NO|APPLICATION FOR|PETITION FOR|SUIT NO|CRIMINAL MISC|MEMORANDUM OF|APPLICATION UNDER|PETITION UNDER)/i.test(cleanLine)) {
            elements.push(
                <div key={idx} className="court-header-title">
                    {renderInlineContent(cleanLine)}
                </div>
            );
            return;
        }

        if (/^\s*(?:\*\*)?\s*(?:VERSUS|V\/S|VS\.?|V\.)\s*(?:\*\*)?\s*$/i.test(trimmed)) {
            elements.push(
                <div key={idx} className="court-versus-block">
                    VERSUS
                </div>
            );
            return;
        }

        if (/^IN THE MATTER OF:?/i.test(cleanLine)) {
            elements.push(
                <div key={idx} className="court-matter-title">
                    {renderInlineContent(cleanLine)}
                </div>
            );
            return;
        }

        if (/^(MOST RESPECTFULLY SHOWETH|RESPECTFULLY SHOWETH|GROUNDS|GROUNDS FOR BAIL|FACTS OF THE CASE|PRAYER|PRAYER CLAUSE|VERIFICATION|AFFIDAVIT|AFFIDAVIT IN SUPPORT|TERMS AND CONDITIONS|SYNOPSIS|LIST OF DATES|INDEX OF ANNEXURES):?/i.test(cleanLine)) {
            elements.push(
                <div key={idx} className="court-section-heading">
                    {renderInlineContent(cleanLine)}
                </div>
            );
            return;
        }

        const numberedMatch = cleanLine.match(/^\s*(\d+[\.\)]|[a-zA-Z][\.\)]|\([0-9a-zA-Z]+\))\s+(.*)/);
        if (numberedMatch) {
            const prefix = numberedMatch[1];
            const body = numberedMatch[2];
            elements.push(
                <div key={idx} className="court-numbered-para">
                    <span className="court-para-num">{prefix}</span>
                    <span className="court-para-body">{renderInlineContent(body)}</span>
                </div>
            );
            return;
        }

        if (/\.\.\.\s*(?:Applicant|Respondent|Petitioner|Defendant|Accused|Deponent|Complainant)/i.test(cleanLine)) {
            elements.push(
                <div key={idx} className="court-party-line">
                    {renderInlineContent(cleanLine)}
                </div>
            );
            return;
        }

        elements.push(
            <p key={idx} className="court-para">
                {renderInlineContent(cleanLine)}
            </p>
        );
    });

    if (inTable) {
        flushTable('final');
    }

    return elements;
};

// Material fields per template — these are flagged if missing
const MATERIAL_FIELDS = {
    bail: ['accused', 'sections', 'court'],
    anticipatory: ['apprehended', 'offense', 'court'],
    plaint: ['plaintiff', 'defendant', 'court', 'cause'],
    injunction: ['applicant', 'respondent', 'court', 'urgency'],
    rent: ['landlord', 'tenant', 'property', 'rent'],
    employment: ['company', 'employee', 'role', 'salary'],
    nda: ['party1', 'party2', 'purpose'],
    vakalatnama: ['court', 'client', 'advocate'],
    affidavit: ['deponent', 'matter'],
};

const TEMPLATE_GROUPS = [
    {
        groupId: 'criminal',
        groupTitle: 'CRIMINAL',
        templates: [
            { id: 'bail', title: 'Bail Application', icon: ShieldAlert, category: 'Petition', fields: [{ id: 'accused', label: 'Name of Accused', placeholder: 'e.g. Ramesh Kumar', material: true }, { id: 'fir', label: 'FIR No. / Year', placeholder: 'e.g. 124/2023' }, { id: 'sections', label: 'Relevant Sections', placeholder: 'e.g. 302, 307 IPC', material: true }, { id: 'court', label: 'Jurisdiction / Court', placeholder: 'e.g. Sessions Court, Delhi', material: true }, { id: 'facts', label: 'Brief Defense Facts', placeholder: 'e.g. Falsely implicated...', type: 'textarea' }] },
            { id: 'anticipatory', title: 'Anticipatory Bail', icon: AlertOctagon, category: 'Petition', fields: [{ id: 'apprehended', label: 'Name of Person', placeholder: 'e.g. Suresh Singh', material: true }, { id: 'ps', label: 'Police Station', placeholder: 'e.g. Vasant Kunj' }, { id: 'offense', label: 'Apprehended Offense', placeholder: 'e.g. 498A IPC', material: true }, { id: 'court', label: 'Court', placeholder: 'e.g. High Court of Delhi', material: true }, { id: 'reasons', label: 'Reasons', placeholder: 'e.g. Matrimonial dispute...', type: 'textarea' }] },
        ]
    },
    {
        groupId: 'civil',
        groupTitle: 'CIVIL',
        templates: [
            { id: 'plaint', title: 'Civil Suit / Plaint', icon: Scale, category: 'Plaint and Written statement', fields: [{ id: 'plaintiff', label: 'Plaintiff', placeholder: 'e.g. ABC Corp.', material: true }, { id: 'defendant', label: 'Defendant', placeholder: 'e.g. XYZ Ltd.', material: true }, { id: 'court', label: 'Court', placeholder: 'e.g. District Court, Mumbai', material: true }, { id: 'suitValue', label: 'Suit Value', placeholder: 'e.g. Rs. 50,00,000/-' }, { id: 'cause', label: 'Cause of Action', placeholder: 'e.g. Breach of contract...', type: 'textarea', material: true }] },
            { id: 'injunction', title: 'Injunction Application', icon: BookmarkMinus, category: 'Civil Pleadings', fields: [{ id: 'applicant', label: 'Applicant', placeholder: 'e.g. Rahul Verma', material: true }, { id: 'respondent', label: 'Respondent', placeholder: 'e.g. Municipal Corp.', material: true }, { id: 'court', label: 'Court', placeholder: 'e.g. Civil Judge, Bangalore', material: true }, { id: 'property', label: 'Subject', placeholder: 'e.g. Plot No. 42, Sector 5' }, { id: 'urgency', label: 'Grounds of Urgency', placeholder: 'e.g. Illegal demolition...', type: 'textarea', material: true }] },
        ]
    },
    {
        groupId: 'contracts',
        groupTitle: 'CONTRACTS',
        templates: [
            { id: 'rent', title: 'Rent Agreement', icon: Briefcase, category: 'Lease Financing', fields: [{ id: 'landlord', label: 'Landlord', placeholder: 'e.g. Sunil Gupta', material: true }, { id: 'tenant', label: 'Tenant', placeholder: 'e.g. Priya Sharma', material: true }, { id: 'property', label: 'Property Address', placeholder: 'e.g. Flat 101, A-Wing...', material: true }, { id: 'rent', label: 'Monthly Rent', placeholder: 'e.g. Rs. 25,000/-', material: true }, { id: 'duration', label: 'Duration', placeholder: 'e.g. 11 Months' }] },
            { id: 'employment', title: 'Employment Contract', icon: Users, category: 'Appointment', fields: [{ id: 'company', label: 'Company', placeholder: 'e.g. TechCorp Solutions', material: true }, { id: 'employee', label: 'Employee', placeholder: 'e.g. Anil Kumar', material: true }, { id: 'role', label: 'Job Title', placeholder: 'e.g. Senior Engineer', material: true }, { id: 'salary', label: 'Annual CTC', placeholder: 'e.g. Rs. 15,00,000', material: true }, { id: 'probation', label: 'Probation Period', placeholder: 'e.g. 3 Months' }] },
            { id: 'nda', title: 'NDA', icon: Lock, category: 'Agreement', fields: [{ id: 'party1', label: 'Disclosing Party', placeholder: 'e.g. Innovator Inc.', material: true }, { id: 'party2', label: 'Receiving Party', placeholder: 'e.g. Vendor Corp.', material: true }, { id: 'purpose', label: 'Purpose', placeholder: 'e.g. Exploring M&A merger', material: true }, { id: 'duration', label: 'Duration', placeholder: 'e.g. 3 Years' }] },
        ]
    },
    {
        groupId: 'courtForms',
        groupTitle: 'COURT FORMS',
        templates: [
            { id: 'vakalatnama', title: 'Vakalatnama', icon: FileSignature, category: 'Vakalatnama', fields: [{ id: 'court', label: 'Court Name', placeholder: 'e.g. Supreme Court of India', material: true }, { id: 'client', label: 'Client Name', placeholder: 'e.g. XYZ Ltd.', material: true }, { id: 'advocate', label: 'Advocate Name', placeholder: 'e.g. Sharma Sr. Counsel', material: true }, { id: 'caseNo', label: 'Case No.', placeholder: 'e.g. SLP (C) 1245/2026' }] },
            { id: 'affidavit', title: 'Affidavit', icon: FileText, category: 'Affidavit', fields: [{ id: 'deponent', label: 'Deponent Name', placeholder: 'e.g. Ramesh Singh', material: true }, { id: 'age', label: 'Age / Father', placeholder: 'e.g. 45 yrs, S/o Suresh' }, { id: 'address', label: 'Address', placeholder: 'e.g. 12, Civil Lines...' }, { id: 'matter', label: 'Related Matter', placeholder: 'e.g. Support of Bail App.', material: true }] },
        ]
    },
];

const DraftAssistant = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const { getAuthHeaders, logout } = useAuth();
    const { localOnly } = useLocalMode();
    const allTemplates = TEMPLATE_GROUPS.flatMap(g => g.templates);
    const [activeTemplateId, setActiveTemplateId] = useState('bail');
    const currentTemplate = allTemplates.find(t => t.id === activeTemplateId);

    const [formData, setFormData] = useState({});
    const [isGenerating, setIsGenerating] = useState(false);
    const { stages: draftStages, connectionLost, run: runStageStream } = useStageStream();
    const [hasGenerated, setHasGenerated] = useState(false);
    const [documentContent, setDocumentContent] = useState('');
    const [sources, setSources] = useState([]);
    const [reviewData, setReviewData] = useState(null);
    const [provenanceData, setProvenanceData] = useState(null);
    const [error, setError] = useState('');
    const [copied, setCopied] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [panelOpen, setPanelOpen] = useState(true);
    const [showMissingWarning, setShowMissingWarning] = useState(false);
    const [viewMode, setViewMode] = useState('court'); // 'court' | 'edit'
    const [statuteAudit, setStatuteAudit] = useState(null);
    const [isVerifyingStatutes, setIsVerifyingStatutes] = useState(false);
    const [exportingPdf, setExportingPdf] = useState(false);
    const editorRef = useRef(null);

    // Helpers to get localized strings
    const getGroupTitle = (group) => t(`draftAssistant.categories.${group.groupId}`, group.groupTitle);
    const getTemplateTitle = (tpl) => t(`draftAssistant.templates.${tpl.id}`, tpl.title);
    const getFieldLabel = (field) => t(`draftAssistant.fields.${field.id}.label`, field.label);
    const getFieldPlaceholder = (field) => t(`draftAssistant.fields.${field.id}.placeholder`, field.placeholder);

    // Localized pipeline stage labels
    const localizedStageLabels = useMemo(() => ({
        building_manifest: t('draftAssistant.stages.building_manifest', DRAFT_STAGE_LABELS.building_manifest),
        resolving_statutes: t('draftAssistant.stages.resolving_statutes', DRAFT_STAGE_LABELS.resolving_statutes),
        retrieving_templates: t('draftAssistant.stages.retrieving_templates', DRAFT_STAGE_LABELS.retrieving_templates),
        generating_draft: t('draftAssistant.stages.generating_draft', DRAFT_STAGE_LABELS.generating_draft),
        verifying_draft: t('draftAssistant.stages.verifying_draft', DRAFT_STAGE_LABELS.verifying_draft),
    }), [t]);

    const switchTemplate = (id) => {
        setActiveTemplateId(id);
        setHasGenerated(false);
        setFormData({});
        setDocumentContent('');
        setSources([]);
        setReviewData(null);
        setProvenanceData(null);
        setStatuteAudit(null);
        setIsVerifyingStatutes(false);
        setError('');
        setShowMissingWarning(false);
        setViewMode('court');
    };

    const handleInputChange = (fieldId, value) => {
        setFormData(prev => ({ ...prev, [fieldId]: value }));
    };

    // Compute missing material fields
    const missingMaterialFields = useMemo(() => {
        const materialIds = MATERIAL_FIELDS[activeTemplateId] || [];
        return currentTemplate.fields
            .filter(f => materialIds.includes(f.id) && !formData[f.id]?.trim())
            .map(f => getFieldLabel(f));
    }, [activeTemplateId, formData, currentTemplate, t]);

    const buildDescription = () => {
        const parts = [`Generate a ${currentTemplate.title} with the following details:`];
        currentTemplate.fields.forEach(field => {
            if (formData[field.id]) {
                parts.push(`${field.label}: ${formData[field.id]}`);
            }
        });
        return parts.join('\n');
    };

    const buildStructuredInput = () => {
        const provided = {};
        const empty = [];
        currentTemplate.fields.forEach(field => {
            if (formData[field.id]?.trim()) {
                provided[field.id] = formData[field.id].trim();
            } else {
                empty.push(field.id);
            }
        });
        return {
            document_type: currentTemplate.title,
            template_id: activeTemplateId,
            provided_fields: provided,
            empty_fields: empty,
        };
    };

    const triggerGeneration = async () => {
        // Show warning about missing material fields
        if (missingMaterialFields.length > 0 && !showMissingWarning) {
            setShowMissingWarning(true);
            return;
        }

        setIsGenerating(true);
        setError('');
        setReviewData(null);
        setProvenanceData(null);
        setShowMissingWarning(false);

        await runStageStream(
            fetch('/api/documents/draft', {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'X-Local-Only': String(localOnly) },
                body: JSON.stringify({
                    description: buildDescription(),
                    category: currentTemplate.category,
                    n_results: 5,
                    template_id: activeTemplateId,
                    structured_input: buildStructuredInput(),
                }),
            }),
            {
                onDone: (data) => {
                    setDocumentContent(data.draft);
                    setSources(data.sources || []);
                    setReviewData(data.review || null);
                    setProvenanceData(data.provenance_report || null);
                    setStatuteAudit(data.statute_verification || null);
                    setHasGenerated(true);
                    setSidebarOpen(false); // Give document generous reading/editing width
                    setViewMode('court');
                },
                onError: (message) => setError(message),
            }
        );
        setIsGenerating(false);
    };

    const handleReverifyStatutes = async () => {
        if (!documentContent) return;
        setIsVerifyingStatutes(true);
        try {
            const res = await fetch('/api/documents/verify-statutes', {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    draft_text: documentContent,
                    category: currentTemplate.category
                })
            });
            if (res.ok) {
                const data = await res.json();
                setStatuteAudit(data);
            }
        } catch (e) {
            console.error("Re-verify statutes failed:", e);
        } finally {
            setIsVerifyingStatutes(false);
        }
    };

    const activeDraftText = documentContent;

    const handleCopy = () => {
        const cleanText = sanitizeDraftText(activeDraftText);
        navigator.clipboard.writeText(cleanText);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleExportPdf = async () => {
        if (!activeDraftText) return;
        setExportingPdf(true);
        try {
            const slug = (currentTemplate?.title || 'Court_Pleading').replace(/\s+/g, '_');
            await exportPdfFromApi({
                endpoint: '/api/documents/export-pdf',
                body: {
                    title: currentTemplate?.title || 'Court Application',
                    draft_text: sanitizeDraftText(activeDraftText),
                    court_name: formData?.court || formData?.court_name || 'IN THE COURT OF THE PRINCIPAL DISTRICT & SESSIONS JUDGE',
                    case_number: formData?.case_number || (formData?.fir_number ? `CASE / FIR NO. ${formData.fir_number}` : 'APPLICATION NO. _____ OF 2026'),
                    applicant: formData?.applicant_name || formData?.client_name || formData?.complainant || formData?.tenant_name || formData?.landlord_name || 'APPLICANT / PETITIONER',
                    respondent: formData?.respondent_name || formData?.opposite_party || formData?.state || 'STATE / OPPOSITE PARTY',
                },
                filename: `${slug}_Court_Ready.pdf`,
                headers: getAuthHeaders(),
            });
        } catch (err) {
            console.error('Court PDF export error:', err);
            alert('Failed to export Court PDF: ' + err.message);
        } finally {
            setExportingPdf(false);
        }
    };

    const handleDownload = () => {
        const cleanText = sanitizeDraftText(activeDraftText);
        const blob = new Blob([cleanText], { type: 'text/plain;charset=utf-8' });
        const slug = (currentTemplate?.title || 'Draft').replace(/\s+/g, '_');
        downloadFileFromBlob(blob, `${slug}_LexSetu.txt`, 'text/plain;charset=utf-8');
    };

    const handleOpenInReview = () => {
        navigate('/draft-review', {
            state: {
                draft: activeDraftText,
                review: reviewData
            }
        });
    };

    return (
        <div className="workspace-layout">
            <aside className={`draft-sidebar ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
                <div className="sidebar-header-workspace">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        {sidebarOpen && <h3>{t('draftAssistant.draftLibrary', 'Draft Library')}</h3>}
                        <button
                            className="panel-toggle-btn"
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            title={sidebarOpen ? t('draftAssistant.collapseLibrary', 'Collapse library') : t('draftAssistant.expandLibrary', 'Expand library')}
                        >
                            {sidebarOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
                        </button>
                    </div>
                </div>
                {sidebarOpen && (
                <div className="template-list">
                    {TEMPLATE_GROUPS.map((group, gIdx) => (
                        <div key={gIdx} className="sidebar-category-group">
                            <h5 className="sidebar-category-title">{getGroupTitle(group)}</h5>
                            {group.templates.map(tItem => (
                                <div
                                    key={tItem.id}
                                    className={`template-item ${activeTemplateId === tItem.id ? 'active' : ''}`}
                                    onClick={() => switchTemplate(tItem.id)}
                                >
                                    <tItem.icon size={18} className="template-icon" />
                                    <div><h4>{getTemplateTitle(tItem)}</h4></div>
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
                )}
            </aside>

            <main className="editor-area">
                {!hasGenerated && !isGenerating && (
                    <div className="form-draft-container animate-fade-in">
                        <div className="standard-form-wrapper">
                            <div className="draft-form-header">
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                                    <div style={{ flex: '1', minWidth: '240px' }}>
                                        <h2>{t('draftAssistant.generateTitle', { title: getTemplateTitle(currentTemplate) })}</h2>
                                        <p>{t('draftAssistant.generateSubtitle', 'Fill in the details below. LexSetu AI will generate a grounded legal document using real Indian legal templates. Missing information will be explicitly marked as [NOT PROVIDED] — not assumed or fabricated.')}</p>
                                    </div>
                                    <PrivilegeShield compact={true} />
                                </div>
                            </div>
                            <div className="draft-form-body">
                                {error && (
                                    <div style={{ padding: '0.75rem', background: '#fee2e2', borderRadius: '6px', color: '#991b1b', marginBottom: '1rem', fontSize: '0.9rem' }}>
                                        {/token|expired|session|unauthorized/i.test(error) ? (
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                                                <span><strong>{t('draftAssistant.sessionExpiredLabel', 'Session Expired:')}</strong> {t('draftAssistant.sessionExpiredDesc', 'Your login token has expired. Please log in again to continue drafting.')}</span>
                                                <button
                                                    type="button"
                                                    onClick={() => logout()}
                                                    style={{
                                                        background: '#991b1b',
                                                        color: '#fff',
                                                        border: 'none',
                                                        padding: '0.35rem 0.75rem',
                                                        borderRadius: '4px',
                                                        fontWeight: 600,
                                                        fontSize: '0.8rem',
                                                        cursor: 'pointer'
                                                    }}
                                                >
                                                    {t('draftAssistant.loginAgain', 'Log In Again')}
                                                </button>
                                            </div>
                                        ) : (
                                            error
                                        )}
                                    </div>
                                )}

                                {/* Missing material fields warning */}
                                {showMissingWarning && missingMaterialFields.length > 0 && (
                                    <div className="missing-fields-warning">
                                        <div className="missing-warning-header">
                                            <AlertTriangle size={18} />
                                            <strong>{t('draftAssistant.missingInfo', 'Missing Information')}</strong>
                                        </div>
                                        <p>{t('draftAssistant.missingFieldsDesc', 'The following fields were not provided and will appear as [NOT PROVIDED] in the generated draft:')}</p>
                                        <ul>
                                            {missingMaterialFields.map((label, i) => (
                                                <li key={i}>{label}</li>
                                            ))}
                                        </ul>
                                        <p style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.5rem' }}>
                                            {t('draftAssistant.missingFieldsNote', 'You can still generate the draft — incomplete information will be clearly flagged, not fabricated.')}
                                        </p>
                                        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.75rem' }}>
                                            <button className="smart-generate-btn" onClick={triggerGeneration} style={{ flex: 1 }}>
                                                <Sparkles size={18} /> {t('draftAssistant.generateAnyway', 'Generate Anyway')}
                                            </button>
                                            <button className="editor-action-btn secondary" onClick={() => setShowMissingWarning(false)} style={{ flex: 0 }}>
                                                {t('draftAssistant.goBack', 'Go Back')}
                                            </button>
                                        </div>
                                    </div>
                                )}

                                <div className="form-grid-premium">
                                    {currentTemplate.fields.map(field => (
                                        <div key={field.id} className={`form-group-premium ${field.type === 'textarea' ? 'full-width' : ''}`}>
                                            <label>
                                                {getFieldLabel(field)}
                                                {field.material && <span className="material-badge" title="Important for accuracy">{t('draftAssistant.requiredBadge', 'Required')}</span>}
                                            </label>
                                            {field.type === 'textarea' ? (
                                                <div className="textarea-with-voice">
                                                    <textarea
                                                        rows="3"
                                                        placeholder={getFieldPlaceholder(field)}
                                                        value={formData[field.id] || ''}
                                                        onChange={(e) => handleInputChange(field.id, e.target.value)}
                                                    />
                                                    <VoiceInputButton
                                                        onTranscript={(text) => handleInputChange(
                                                            field.id,
                                                            (formData[field.id] ? formData[field.id] + ' ' : '') + text
                                                        )}
                                                    />
                                                </div>
                                            ) : (
                                                <input
                                                    type="text"
                                                    placeholder={getFieldPlaceholder(field)}
                                                    value={formData[field.id] || ''}
                                                    onChange={(e) => handleInputChange(field.id, e.target.value)}
                                                />
                                            )}
                                        </div>
                                    ))}
                                </div>
                                {!showMissingWarning && (
                                    <button className="smart-generate-btn" onClick={triggerGeneration}>
                                        <Sparkles size={20} /> {t('draftAssistant.generateBtn', 'Generate Grounded Draft')}
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {isGenerating && (
                    <div className="generation-loading-state animate-fade-in">
                        <h3>{t('draftAssistant.generatingTitle', 'Generating Grounded Draft...')}</h3>
                        <PipelineStageList
                            stages={draftStages}
                            stageOrder={DRAFT_STAGE_ORDER}
                            stageLabels={localizedStageLabels}
                        />
                        {connectionLost && (
                            <p className="stage-connection-lost">
                                <AlertTriangle size={14} /> {t('draftAssistant.connLost', "Couldn't confirm progress — result may still be correct.")}
                            </p>
                        )}
                    </div>
                )}

                {hasGenerated && (
                    <div className="canvas-wrapper">
                        <div className="editor-controls animate-fade-in" style={{ flexWrap: 'wrap', gap: '8px' }}>
                            <div className="refinement-status-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', background: localOnly ? '#FEF3C7' : '#f1d1a6', color: localOnly ? '#92400E' : '#63120e', padding: '0.35rem 0.75rem', borderRadius: '8px', fontSize: '0.8rem', fontWeight: '700', border: localOnly ? '1px solid #F59E0B' : '1px solid #dfa46f' }}>
                                <CheckCircle2 size={15} style={{ color: localOnly ? '#92400E' : '#10B981' }} />
                                <span>
                                    {localOnly
                                        ? t('draftAssistant.localOnlyBadge', 'Generated locally (Ollama) — refinement skipped in local-only mode')
                                        : (reviewData?.overall_score 
                                            ? t('draftAssistant.groundedScore', { score: reviewData.overall_score, defaultValue: `Grounded & Refined (Score: ${reviewData.overall_score}/100)` })
                                            : t('draftAssistant.groundedVerified', 'Grounded & Refined (Verified)'))}
                                </span>
                            </div>

                            <div className="view-mode-toggle">
                                <button
                                    className={`view-toggle-btn ${viewMode === 'court' ? 'active' : ''}`}
                                    onClick={() => setViewMode('court')}
                                    title="Court-ready styled document"
                                >
                                    <Eye size={14} /> {t('draftAssistant.courtView', 'Court View')}
                                </button>
                                <button
                                    className={`view-toggle-btn ${viewMode === 'edit' ? 'active' : ''}`}
                                    onClick={() => setViewMode('edit')}
                                    title="Directly edit text"
                                >
                                    <Edit3 size={14} /> {t('draftAssistant.editText', 'Edit Text')}
                                </button>
                            </div>

                            <div className="editor-actions ml-auto" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                <PrivilegeShield compact={true} />
                                <button className="editor-action-btn secondary" onClick={handleOpenInReview}>
                                    <FileCheck size={15} /> {t('draftAssistant.inspectReview', 'Inspect in Draft Review')}
                                </button>
                                <button className="editor-action-btn secondary" onClick={() => { setHasGenerated(false); setShowMissingWarning(false); }}>
                                    <Edit3 size={15} /> {t('draftAssistant.editDetails', 'Edit Details')}
                                </button>
                                <button className="editor-action-btn secondary" onClick={triggerGeneration}>
                                    <RefreshCw size={15} /> {t('draftAssistant.regenerate', 'Regenerate')}
                                </button>
                                <button className="editor-action-btn secondary" onClick={handleCopy}>
                                    {copied ? <><Check size={15} /> {t('draftAssistant.copied', 'Copied!')}</> : <><Copy size={15} /> {t('draftAssistant.copy', 'Copy')}</>}
                                </button>
                                <button
                                    className="editor-action-btn primary"
                                    onClick={handleExportPdf}
                                    disabled={exportingPdf}
                                    title="Download court-formatted A4 Pleading PDF with official legal margins"
                                    style={{ background: '#63120e', color: '#f9eedc', borderColor: '#8c3a2a' }}
                                >
                                    {exportingPdf ? <Loader2 size={15} className="spin" /> : <FileDown size={15} />} {t('draftAssistant.exportPdf', 'Export Court PDF')}
                                </button>
                                <button className="editor-action-btn secondary" onClick={handleDownload} title="Download plain text (.txt)">
                                    <Download size={15} /> {t('draftAssistant.download', 'Download (.txt)')}
                                </button>
                            </div>
                        </div>

                        <div className="a4-canvas animate-fade-in">
                            {viewMode === 'court' ? (
                                <div className="a4-page court-view-mode" ref={editorRef}>
                                    {renderCourtDocument(activeDraftText)}
                                </div>
                            ) : (
                                <div className="a4-page edit-view-mode">
                                    <textarea
                                        className="a4-editor-textarea"
                                        value={activeDraftText}
                                        onChange={(e) => setDocumentContent(e.target.value)}
                                        placeholder="Draft document content..."
                                        spellCheck={false}
                                        rows={30}
                                    />
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </main>

            <aside className={`ai-insight-panel ${panelOpen ? '' : 'panel-collapsed'}`}>
                <div className="ai-panel-header">
                    <button
                        className="panel-toggle-btn panel-toggle-btn-right"
                        onClick={() => setPanelOpen(!panelOpen)}
                        title={panelOpen ? 'Collapse panel' : 'Expand panel'}
                    >
                        {panelOpen ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
                    </button>
                    {panelOpen && (
                        <>
                            <Sparkles size={18} className="text-primary" />
                            <h3>{t('draftAssistant.provenanceTitle', 'Provenance & Sources')}</h3>
                        </>
                    )}
                </div>
                {panelOpen && (
                <div className="ai-suggestions-feed">
                    {!hasGenerated && (
                        <div className="empty-suggestions">
                            <Wand2 size={32} className="text-secondary mx-auto mb-4 opacity-50" />
                            <p>{t('draftAssistant.generatePrompt', 'Generate a draft to see provenance tracking — what facts came from your input vs. what was marked as missing.')}</p>
                        </div>
                    )}

                    {/* Statute & Section Verification Audit */}
                    {hasGenerated && (
                        <div className="statute-audit-section animate-fade-in">
                            <div className="statute-audit-header">
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                                    <Scale size={16} className="text-primary" />
                                    <h4 className="provenance-heading" style={{ margin: 0 }}>{t('draftAssistant.statuteAudit', 'Statute & Section Audit')}</h4>
                                </div>
                                <button
                                    className="recheck-statute-btn"
                                    onClick={handleReverifyStatutes}
                                    disabled={isVerifyingStatutes}
                                    title="Re-verify legal provisions in current draft"
                                >
                                    {isVerifyingStatutes ? (
                                        <Loader2 size={12} className="spin" />
                                    ) : (
                                        <RefreshCw size={12} />
                                    )}
                                    <span>{isVerifyingStatutes ? t('draftAssistant.checking', 'Checking...') : t('draftAssistant.recheck', 'Re-check')}</span>
                                </button>
                            </div>

                            {statuteAudit ? (
                                <>
                                    <div className={`statute-summary-badge ${statuteAudit.has_warnings ? 'has-warnings' : 'all-verified'}`}>
                                        {statuteAudit.has_warnings ? (
                                            <AlertTriangle size={14} style={{ flexShrink: 0 }} />
                                        ) : (
                                            <CheckCircle2 size={14} style={{ flexShrink: 0 }} />
                                        )}
                                        <span>{statuteAudit.summary}</span>
                                    </div>

                                    <div className="statute-findings-list">
                                        {statuteAudit.findings.map((item, idx) => (
                                            <div key={idx} className={`statute-item-card status-${item.status.toLowerCase()}`}>
                                                <div className="statute-item-top">
                                                    <span className="statute-name-badge">
                                                        {item.raw_mention || `Section ${item.section_number} ${item.act_id.toUpperCase()}`}
                                                    </span>
                                                    <span className={`statute-status-pill ${item.status.toLowerCase()}`}>
                                                        {item.status === 'VERIFIED' ? (
                                                            <><Check size={11} /> Verified</>
                                                        ) : (
                                                            <><CircleAlert size={11} /> Not Found</>
                                                        )}
                                                    </span>
                                                </div>

                                                {item.heading && (
                                                    <div className="statute-official-title">
                                                        <strong>Title:</strong> {item.heading}
                                                    </div>
                                                )}

                                                {item.transition_note && (
                                                    <div className="statute-transition-note">
                                                        <Info size={12} style={{ flexShrink: 0, marginTop: '2px' }} />
                                                        <span>{item.transition_note}</span>
                                                    </div>
                                                )}

                                                {item.equivalent && (
                                                    <div className="statute-equivalent-tag">
                                                        <span className="equiv-label">2024 Law:</span>
                                                        <span className="equiv-val">
                                                            Section {item.equivalent.section} {item.equivalent.act}
                                                            {item.equivalent.heading ? ` (${item.equivalent.heading})` : ''}
                                                        </span>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </>
                            ) : (
                                <div className="empty-statute-audit">
                                    <p>{t('draftAssistant.clickRecheck', 'Click "Re-check" to audit statutory sections in this draft.')}</p>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Provenance Report */}
                    {hasGenerated && provenanceData && (
                        <div className="provenance-section animate-fade-in">
                            <h4 className="provenance-heading">
                                <Info size={15} /> {t('draftAssistant.factProvenance', 'Fact Provenance')}
                            </h4>

                            {provenanceData.provided_facts?.length > 0 && (
                                <div className="provenance-group provenance-provided">
                                    <h5>{t('draftAssistant.fromInput', { count: provenanceData.total_provided, defaultValue: `✅ From Your Input (${provenanceData.total_provided})` })}</h5>
                                    {provenanceData.provided_facts.map((f, i) => (
                                        <div key={i} className="provenance-item">
                                            <span className="provenance-label">{f.field}</span>
                                            <span className="provenance-value">{f.value}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {provenanceData.missing_material?.length > 0 && (
                                <div className="provenance-group provenance-missing-material">
                                    <h5>{t('draftAssistant.missingMaterial', { count: provenanceData.total_missing_material, defaultValue: `⚠️ Missing — Material (${provenanceData.total_missing_material})` })}</h5>
                                    <p className="provenance-note">{t('draftAssistant.missingMaterialNote', 'These appear as [NOT PROVIDED] in the draft')}</p>
                                    {provenanceData.missing_material.map((f, i) => (
                                        <div key={i} className="provenance-item">
                                            <span className="provenance-label">{f.field}</span>
                                            <span className="provenance-status">{t('draftAssistant.notProvided', '[NOT PROVIDED]')}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {provenanceData.missing_optional?.length > 0 && (
                                <div className="provenance-group provenance-missing-optional">
                                    <h5>{t('draftAssistant.missingOptional', { count: provenanceData.total_missing_optional, defaultValue: `📋 Missing — Optional (${provenanceData.total_missing_optional})` })}</h5>
                                    {provenanceData.missing_optional.map((f, i) => (
                                        <div key={i} className="provenance-item">
                                            <span className="provenance-label">{f.field}</span>
                                            <span className="provenance-status">{t('draftAssistant.notProvided', '[NOT PROVIDED]')}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Reference Sources */}
                    {hasGenerated && sources.length > 0 && (
                        <div className="animate-fade-in" style={{ marginTop: '1rem' }}>
                            <h4 className="provenance-heading">
                                <CornerDownRight size={15} /> {t('draftAssistant.referenceTemplates', 'Reference Templates')}
                            </h4>
                            <p style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.75rem' }}>
                                {t('draftAssistant.aiReferenced', 'AI referenced these real documents from the legal database:')}
                            </p>
                            {sources.map((s, i) => (
                                <div key={i} className="suggestion-card">
                                    <h5><CornerDownRight size={14} className="text-secondary" /> {s.filename}</h5>
                                    <p>{t('draftAssistant.categoryMatch', { category: s.category, score: (s.score * 100).toFixed(0), defaultValue: `Category: ${s.category} | Match: ${(s.score * 100).toFixed(0)}%` })}</p>
                                </div>
                            ))}
                        </div>
                    )}
                    {hasGenerated && sources.length === 0 && (
                        <p style={{ fontSize: '0.85rem', color: '#6b7280' }}>
                            {t('draftAssistant.runIngest', 'Run ingest.py to load legal templates for reference-based generation.')}
                        </p>
                    )}
                </div>
                )}
            </aside>
        </div>
    );
};

export default DraftAssistant;
