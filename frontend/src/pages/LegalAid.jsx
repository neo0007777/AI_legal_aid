import { useState, useRef, useEffect } from 'react';
import {
    Send, Sparkles, Scale, BookOpen, AlertTriangle,
    ShieldAlert, Search, FileText, Copy, Check,
    Mic, MicOff, RotateCcw, X, Shield, Gavel, HelpCircle,
    Crown, Lock, ArrowRight, ShieldCheck, CheckCircle2, FileDown,
    SlidersHorizontal, Bookmark, BookmarkCheck, ListChecks,
    Briefcase, RefreshCw, Zap
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { downloadFileFromBlob, exportPdfFromApi } from '../utils/downloadHelper';
import TranslateAction from '../components/TranslateAction';
import PipelineStageList from '../components/PipelineStageList';
import { useStageStream } from '../hooks/useStageStream';
import './LegalAid.css';

// Real, distinct steps backend/routes/legal_aid.py's /ask stream actually emits
// (see ask_legal_question_stream) -- collapsed from a proposed 5-stage list to 4
// because there's no separable "cross-referencing" step distinct from retrieval.
const LEGAL_AID_STAGE_ORDER = ['parsing_query', 'retrieving_sources', 'generating_answer', 'attaching_sources'];
const LEGAL_AID_STAGE_LABELS = {
    parsing_query: 'Parsing legal query & identifying jurisdiction',
    retrieving_sources: 'Searching statutes, precedents & drafting corpus',
    generating_answer: 'Synthesizing grounded answer',
    attaching_sources: 'Attaching source citations',
};

const SUGGESTIONS = [
    {
        category: "Criminal Law",
        text: "What are the rules and procedure for filing an Anticipatory Bail under Section 438 CrPC?",
        icon: ShieldAlert,
    },
    {
        category: "Tenancy & Civil",
        text: "My landlord is refusing to return my security deposit without damages. What is my legal recourse?",
        icon: Scale,
    },
    {
        category: "Civil Injunctions",
        text: "How do I secure an urgent ex-parte injunction against illegal property demolition under Order 39 CPC?",
        icon: AlertTriangle,
    },
    {
        category: "Criminal Procedure",
        text: "Can an FIR be quashed under Section 482 CrPC if the parties have reached a mutual compromise?",
        icon: BookOpen,
    },
    {
        category: "Commercial Law",
        text: "What is the statutory limitation period and notice requirement for cheque dishonour under Section 138 NI Act?",
        icon: Gavel,
    },
    {
        category: "Consumer Rights",
        text: "What remedies exist under Consumer Protection Act 2019 for deficient service and misleading claims?",
        icon: Shield,
    }
];

const cleanAndNormalizeText = (text) => {
    if (!text) return '';
    return text
        .replace(/[\u202F\u00A0\u2000-\u200A]/g, ' ')
        .replace(/\s*---+$/, '')
        .trim();
};

const formatCategoryTag = (cat) => {
    if (!cat) return 'General Law';
    const upper = cat.toUpperCase();
    if (upper === 'SALE') return 'Sale of Goods / Property Act';
    if (upper === 'CRPC') return 'Code of Criminal Procedure';
    if (upper === 'IPC') return 'Indian Penal Code';
    if (upper === 'CPC') return 'Code of Civil Procedure';
    if (upper === 'CONSTITUTION') return 'Constitutional Law';
    return cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
};

const formatRichInline = (rawText) => {
    if (!rawText) return null;
    const text = cleanAndNormalizeText(rawText);

    const regex = /(\*\*\*[^*]+?\*\*\*|\*\*[^*]+?\*\*|\*[^*]+?\*|_[^_]+?_|`[^`]+?`)/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
        if (match.index > lastIndex) {
            const rawPiece = text.substring(lastIndex, match.index).replace(/\*+/g, '');
            if (rawPiece) parts.push(rawPiece);
        }
        const token = match[0];
        if (token.startsWith('***') && token.endsWith('***')) {
            const inner = token.slice(3, -3);
            parts.push(<strong key={match.index} className="aid-strong"><em className="aid-italic">{inner}</em></strong>);
        } else if (token.startsWith('**') && token.endsWith('**')) {
            const inner = token.slice(2, -2);
            parts.push(<strong key={match.index} className="aid-strong">{inner}</strong>);
        } else if (token.startsWith('*') && token.endsWith('*')) {
            const inner = token.slice(1, -1);
            parts.push(<em key={match.index} className="aid-italic">{inner}</em>);
        } else if (token.startsWith('_') && token.endsWith('_')) {
            const inner = token.slice(1, -1);
            parts.push(<em key={match.index} className="aid-italic">{inner}</em>);
        } else if (token.startsWith('`') && token.endsWith('`')) {
            const inner = token.slice(1, -1);
            parts.push(<code key={match.index} className="aid-code">{inner}</code>);
        }
        lastIndex = match.index + token.length;
    }

    if (lastIndex < text.length) {
        const rawPiece = text.substring(lastIndex).replace(/\*+/g, '');
        if (rawPiece) parts.push(rawPiece);
    }

    if (parts.length === 0) {
        return text.replace(/\*+/g, '');
    }

    return parts;
};

const renderFormattedText = (text) => {
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
                <div key={`table-${key}`} className="aid-table-wrapper">
                    <table className="aid-table">
                        <thead>
                            <tr>
                                {isHeader.map((h, i) => (
                                    <th key={i}>{formatRichInline(h)}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {dataRows.map((row, ri) => (
                                <tr key={ri}>
                                    {row.map((cell, ci) => (
                                        <td key={ci}>{formatRichInline(cell)}</td>
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

    lines.forEach((line, idx) => {
        const trimmed = line.trim();

        if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
            const cells = trimmed.split('|').slice(1, -1).map(c => c.trim());
            tableRows.push(cells);
            inTable = true;
            return;
        } else if (inTable) {
            flushTable(idx);
        }

        if (!trimmed) {
            elements.push(<div key={idx} className="aid-line-spacer" />);
            return;
        }

        if (/^[-*]{3,}$/.test(trimmed)) {
            elements.push(<hr key={idx} className="aid-divider" />);
            return;
        }

        if (trimmed.startsWith('- ') || trimmed.startsWith('• ') || trimmed.startsWith('* ')) {
            const cleanContent = line.replace(/^[-•*]\s*/, '').trim();
            elements.push(
                <div key={idx} className="aid-bullet-point">
                    <span className="aid-bullet-dot">•</span>
                    <span className="aid-bullet-content">{formatRichInline(cleanContent)}</span>
                </div>
            );
            return;
        }

        const numMatch = trimmed.match(/^(\d+[\.\)])\s*(.*)/);
        if (numMatch) {
            elements.push(
                <div key={idx} className="aid-numbered-point">
                    <span className="aid-numbered-badge">{numMatch[1]}</span>
                    <span className="aid-numbered-content">{formatRichInline(numMatch[2])}</span>
                </div>
            );
            return;
        }

        elements.push(
            <p key={idx} className="aid-paragraph">
                {formatRichInline(line)}
            </p>
        );
    });

    if (inTable) {
        flushTable('end');
    }

    return elements;
};

/**
 * Multi-mode legal answer parser.
 * Perfectly formats Standard Judicial, Executive Brief, IRAC, Bullet points, or Custom Guided responses
 * without ANY structure mismatch.
 */
const parseLegalAidAnswer = (rawAnswer, requestedMode = 'standard') => {
    if (!rawAnswer) return { mode: 'standard', sections: [], disclaimer: '', raw: '' };

    const cleanRaw = cleanAndNormalizeText(rawAnswer);
    let disclaimer = '';
    let mainText = cleanRaw;

    const discMatch = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?DISCLAIMER:?(?:\*\*)?\s*([\s\S]*?)$/i);
    if (discMatch) {
        disclaimer = discMatch[1].trim();
        mainText = mainText.substring(0, discMatch.index).trim();
    }

    // 1. Executive Brief matching
    const execSummary = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?EXECUTIVE SUMMARY:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?STATUTORY POSITION:?|$)/i);
    const execStatutory = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?STATUTORY POSITION:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?JUDICIAL PRECEDENTS:?|$)/i);
    const execPrecedents = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?JUDICIAL PRECEDENTS:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?STRATEGIC RECOMMENDATIONS:?|$)/i);
    const execStrategy = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?STRATEGIC RECOMMENDATIONS:?(?:\*\*)?\s*([\s\S]*?)$/i);

    if (execSummary || (requestedMode === 'executive_brief' && (execStatutory || execStrategy))) {
        const sections = [];
        if (execSummary && execSummary[1].trim()) {
            sections.push({ id: 'summary', title: 'Executive Summary', icon: 'file', badge: 'Leadership Overview', content: execSummary[1].trim() });
        }
        if (execStatutory && execStatutory[1].trim()) {
            sections.push({ id: 'statutory', title: 'Statutory Position & Codified Sections', icon: 'scale', badge: 'Bare Acts & Codes', content: execStatutory[1].trim() });
        }
        if (execPrecedents && execPrecedents[1].trim()) {
            sections.push({ id: 'precedents', title: 'Judicial Precedents & Decisive Ratios', icon: 'book', badge: 'Binding Precedents', content: execPrecedents[1].trim() });
        }
        if (execStrategy && execStrategy[1].trim()) {
            sections.push({ id: 'strategy', title: 'Strategic Recommendations & Roadmap', icon: 'alert', badge: 'Action Plan', content: execStrategy[1].trim() });
        }
        if (sections.length > 0) {
            return { mode: 'executive_brief', title: 'Executive Legal Brief', sections, disclaimer, raw: rawAnswer };
        }
    }

    // 2. IRAC Framework matching
    const iracIssue = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?(?:LEGAL\s+)?ISSUE:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?RULE:?|$)/i);
    const iracRule = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?RULE:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?APPLICATION:?|$)/i);
    const iracApp = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?APPLICATION:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?CONCLUSION:?|$)/i);
    const iracConcl = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?CONCLUSION:?(?:\*\*)?\s*([\s\S]*?)$/i);

    if (iracIssue || (requestedMode === 'irac' && (iracRule || iracApp))) {
        const sections = [];
        if (iracIssue && iracIssue[1].trim()) {
            sections.push({ id: 'issue', title: 'Legal Issue Presented', icon: 'help', badge: 'I - Issue', content: iracIssue[1].trim() });
        }
        if (iracRule && iracRule[1].trim()) {
            sections.push({ id: 'rule', title: 'Governing Legal Rules & Statutory Provisions', icon: 'scale', badge: 'R - Rule', content: iracRule[1].trim() });
        }
        if (iracApp && iracApp[1].trim()) {
            sections.push({ id: 'application', title: 'Legal Application & Factual Analysis', icon: 'book', badge: 'A - Application', content: iracApp[1].trim() });
        }
        if (iracConcl && iracConcl[1].trim()) {
            sections.push({ id: 'conclusion', title: 'Conclusion & Statutory Remedies', icon: 'gavel', badge: 'C - Conclusion', content: iracConcl[1].trim() });
        }
        if (sections.length > 0) {
            return { mode: 'irac', title: 'IRAC Legal Framework', sections, disclaimer, raw: rawAnswer };
        }
    }

    // 3. Bullet Points & Checklist matching
    const bulletSummary = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?KEY SUMMARY:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?STATUTORY PROVISIONS(?:\s*\(BULLETS\))?:?|$)/i);
    const bulletStatutes = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?STATUTORY PROVISIONS(?:\s*\(BULLETS\))?:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?LANDMARK PRECEDENTS(?:\s*\(BULLETS\))?:?|$)/i);
    const bulletPrecedents = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?LANDMARK PRECEDENTS(?:\s*\(BULLETS\))?:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?ACTIONABLE CHECKLIST:?|$)/i);
    const bulletChecklist = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?ACTIONABLE CHECKLIST:?(?:\*\*)?\s*([\s\S]*?)$/i);

    if (bulletSummary || (requestedMode === 'bullet_points' && (bulletStatutes || bulletChecklist))) {
        const sections = [];
        if (bulletSummary && bulletSummary[1].trim()) {
            sections.push({ id: 'summary', title: 'Key Summary', icon: 'file', badge: 'Quick Take', content: bulletSummary[1].trim() });
        }
        if (bulletStatutes && bulletStatutes[1].trim()) {
            sections.push({ id: 'statutes', title: 'Statutory Provisions', icon: 'scale', badge: 'Applicable Laws', content: bulletStatutes[1].trim() });
        }
        if (bulletPrecedents && bulletPrecedents[1].trim()) {
            sections.push({ id: 'precedents', title: 'Landmark Precedents', icon: 'book', badge: 'Key Rulings', content: bulletPrecedents[1].trim() });
        }
        if (bulletChecklist && bulletChecklist[1].trim()) {
            sections.push({ id: 'checklist', title: 'Actionable Checklist & Timelines', icon: 'checklist', badge: 'Action Steps', content: bulletChecklist[1].trim() });
        }
        if (sections.length > 0) {
            return { mode: 'bullet_points', title: 'Bullet Points & Actionable Checklist', sections, disclaimer, raw: rawAnswer };
        }
    }

    // 4. Standard Direct Answer matching
    const directMatch = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?DIRECT ANSWER:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?LEGAL BASIS:?|$)/i);
    const legalMatch = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?LEGAL BASIS:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?BINDING PRECEDENTS:?|$)/i);
    const precMatch = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?BINDING PRECEDENTS:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?ACTIONABLE INSIGHT:?|$)/i);
    const insightMatch = mainText.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?ACTIONABLE INSIGHT:?(?:\*\*)?\s*([\s\S]*?)$/i);

    if (directMatch || legalMatch) {
        const sections = [];
        if (directMatch && directMatch[1].trim()) {
            sections.push({ id: 'direct', title: 'Direct Answer', icon: 'file', badge: 'Legal Opinion', content: directMatch[1].trim() });
        }
        if (legalMatch && legalMatch[1].trim()) {
            sections.push({ id: 'legal', title: 'Statutory Grounds & Legal Basis', icon: 'scale', badge: 'Statutory Basis', content: legalMatch[1].trim() });
        }
        if (precMatch && precMatch[1].trim()) {
            sections.push({ id: 'precedents', title: 'Judicial Precedents & Authorities Cited', icon: 'book', badge: 'Authorities', content: precMatch[1].trim() });
        }
        if (insightMatch && insightMatch[1].trim()) {
            sections.push({ id: 'insight', title: 'Actionable Counsel & Strategic Steps', icon: 'alert', badge: 'Strategy', content: insightMatch[1].trim() });
        }
        return { mode: 'standard', title: 'Standard Judicial', sections, disclaimer, raw: rawAnswer };
    }

    // 5. Custom Guided Structure (parse markdown headers if any exist)
    const headerRegex = /(?:^|\n)(?:#+\s*|\*\*)([A-Z0-9\s\&\-\/]{3,60})(?:\*\*|:)?\n([\s\S]*?)(?=(?:^|\n)(?:#+\s*|\*\*)[A-Z0-9\s\&\-\/]{3,60}(?:\*\*|:)?\n|$)/gi;
    const customSections = [];
    let hMatch;
    while ((hMatch = headerRegex.exec(mainText)) !== null) {
        const title = hMatch[1].replace(/[*#]/g, '').trim();
        const content = hMatch[2].trim();
        if (title && content && !title.toUpperCase().includes('DISCLAIMER')) {
            customSections.push({
                id: 'custom_' + customSections.length,
                title: title.replace(/^[0-9\.\-\s]+/, ''),
                icon: 'file',
                badge: 'Custom Section',
                content: content,
            });
        }
    }

    if (customSections.length > 0) {
        return { mode: 'custom', title: 'Custom Guided Structure', sections: customSections, disclaimer, raw: rawAnswer };
    }

    // Fallback: single clean response card
    return {
        mode: requestedMode || 'custom',
        title: requestedMode === 'standard' ? 'Standard Judicial' : 'Guided Legal Advisory',
        sections: [
            { id: 'content', title: 'Legal Advisory', icon: 'file', badge: 'Analysis', content: mainText }
        ],
        disclaimer,
        raw: rawAnswer,
    };
};

const renderSectionIcon = (iconType) => {
    switch (iconType) {
        case 'scale':
            return <Scale size={16} />;
        case 'book':
            return <BookOpen size={16} />;
        case 'alert':
            return <AlertTriangle size={16} />;
        case 'gavel':
            return <Gavel size={16} />;
        case 'help':
            return <HelpCircle size={16} />;
        case 'checklist':
            return <CheckCircle2 size={16} />;
        default:
            return <FileText size={16} />;
    }
};

const LegalAid = () => {
    const { getAuthHeaders } = useAuth();

    const [messages, setMessages] = useState([]);
    const [inputValue, setInputValue] = useState('');
    const [isThinking, setIsThinking] = useState(false);
    const { stages: legalAidStages, connectionLost, run: runStageStream } = useStageStream();
    const [copiedId, setCopiedId] = useState(null);
    const [downloadingPdfId, setDownloadingPdfId] = useState(null);
    const [isListening, setIsListening] = useState(false);
    const [showUpgradeModal, setShowUpgradeModal] = useState(false);
    const [upgradeRequested, setUpgradeRequested] = useState(false);

    // Structure Memory & Custom Guidance State
    const [structureMode, setStructureMode] = useState('standard');
    const [structureTitle, setStructureTitle] = useState('Standard Judicial');
    const [customInstructions, setCustomInstructions] = useState('');
    const [hasSavedMemory, setHasSavedMemory] = useState(false);
    const [showGuidanceModal, setShowGuidanceModal] = useState(false);
    const [rememberGuidance, setRememberGuidance] = useState(true);

    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const recognitionRef = useRef(null);

    // Load saved memory structure from database on mount
    useEffect(() => {
        fetch('/api/legal-aid/memory', { headers: getAuthHeaders() })
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (data && data.structure_mode) {
                    setStructureMode(data.structure_mode);
                    setStructureTitle(data.structure_title || 'Standard Judicial');
                    setCustomInstructions(data.custom_instructions || '');
                    setHasSavedMemory(data.structure_mode !== 'standard' || Boolean(data.custom_instructions));
                }
            })
            .catch(err => console.warn('Could not load legal aid memory:', err));
    }, []);

    const downloadLegalAidPDF = async (msg) => {
        setDownloadingPdfId(msg.id);
        try {
            const slug = (msg.question || 'legal-opinion').slice(0, 30).replace(/[^a-zA-Z0-9]+/g, '_');
            await exportPdfFromApi({
                endpoint: '/api/legal-aid/export-pdf',
                body: {
                    question: msg.question || 'Legal Inquiry',
                    answer: msg.raw,
                    sources: msg.data?.sources || [],
                },
                filename: `LexSetu_Opinion_${slug}.pdf`,
                headers: getAuthHeaders(),
            });
        } catch (err) {
            console.error('Legal Aid PDF export error:', err);
            alert('Failed to generate PDF: ' + err.message);
        } finally {
            setDownloadingPdfId(null);
        }
    };

    // Initialize Web Speech API for voice dictation
    useEffect(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            try {
                const recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;
                recognition.lang = 'en-IN';

                recognition.onresult = (event) => {
                    const transcript = event.results[0][0].transcript;
                    setInputValue(prev => prev ? `${prev.trim()} ${transcript}` : transcript);
                    setIsListening(false);
                };

                recognition.onerror = () => setIsListening(false);
                recognition.onend = () => setIsListening(false);

                recognitionRef.current = recognition;
            } catch (e) {
                console.error("Speech recognition setup failed:", e);
            }
        }
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isThinking]);

    const toggleListening = () => {
        if (!recognitionRef.current) {
            alert("Voice dictation is not supported on this browser.");
            return;
        }

        if (isListening) {
            recognitionRef.current.stop();
            setIsListening(false);
        } else {
            try {
                recognitionRef.current.start();
                setIsListening(true);
            } catch (err) {
                console.error("Mic start failed", err);
            }
        }
    };

    const handleCopy = (msgId, rawText) => {
        navigator.clipboard.writeText(rawText);
        setCopiedId(msgId);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const handleClearChat = () => {
        setMessages([]);
        setInputValue('');
    };

    const applyPreset = async (mode, title) => {
        setStructureMode(mode);
        setStructureTitle(title);
        setCustomInstructions('');

        if (hasSavedMemory || rememberGuidance) {
            try {
                await fetch('/api/legal-aid/memory', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders(),
                    },
                    body: JSON.stringify({
                        structure_mode: mode,
                        structure_title: title,
                        custom_instructions: null,
                    }),
                });
                setHasSavedMemory(mode !== 'standard');
            } catch (e) {
                console.error('Failed to save preset memory:', e);
            }
        }
    };

    const handleSaveGuidance = async () => {
        setShowGuidanceModal(false);
        if (rememberGuidance) {
            try {
                const res = await fetch('/api/legal-aid/memory', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders(),
                    },
                    body: JSON.stringify({
                        structure_mode: structureMode,
                        structure_title: structureTitle,
                        custom_instructions: customInstructions || null,
                    }),
                });
                if (res.ok) {
                    setHasSavedMemory(structureMode !== 'standard' || Boolean(customInstructions));
                }
            } catch (e) {
                console.error('Failed to save memory:', e);
            }
        }
    };

    const handleResetMemory = async () => {
        try {
            await fetch('/api/legal-aid/memory', {
                method: 'DELETE',
                headers: getAuthHeaders(),
            });
        } catch (e) {
            console.error('Failed to reset memory:', e);
        }
        setStructureMode('standard');
        setStructureTitle('Standard Judicial');
        setCustomInstructions('');
        setHasSavedMemory(false);
    };

    const handleSendMessage = async (textToSend) => {
        const text = (textToSend || inputValue).trim();
        if (!text || isThinking) return;

        const userMsg = {
            id: 'user_' + Date.now(),
            type: 'user',
            text: text,
        };

        setMessages(prev => [...prev, userMsg]);
        setInputValue('');
        setIsThinking(true);

        try {
            await runStageStream(
                fetch('/api/legal-aid/ask', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders(),
                    },
                    body: JSON.stringify({
                        question: text,
                        n_results: 3,
                        structure_mode: structureMode,
                        custom_instructions: customInstructions || null,
                        save_to_memory: false,
                    }),
                }),
                {
                    onDone: (data) => {
                        const effectiveMode = data.applied_structure_mode || structureMode;
                        const parsed = parseLegalAidAnswer(data.answer, effectiveMode);

                        const aiMsg = {
                            id: 'ai_' + Date.now(),
                            type: 'structured_ai',
                            question: text,
                            raw: data.answer,
                            applied_structure_mode: effectiveMode,
                            applied_structure_title: data.applied_structure_title || structureTitle,
                            memory_active: data.memory_active,
                            requires_upgrade: Boolean(
                                data.requires_upgrade ||
                                data.answer?.includes('Advocate Pro') ||
                                data.answer?.toLowerCase().includes('upgrade your plan') ||
                                data.answer?.toLowerCase().includes('plan does not allow') ||
                                data.answer?.toLowerCase().includes("plan don't allow") ||
                                data.answer?.toLowerCase().includes('exceed the scope of the standard') ||
                                data.answer?.includes('upgrade to the LexSetu')
                            ),
                            upgrade_tier: data.upgrade_tier || 'LexSetu Advocate Pro / Criminal Defense',
                            parsed: parsed,
                            data: {
                                tags: data.sources?.map(s => s.category).filter((v, i, a) => a.indexOf(v) === i).slice(0, 3) || [],
                                sources: data.sources || [],
                            }
                        };

                        setMessages(prev => [...prev, aiMsg]);
                    },
                    onError: (message) => {
                        setMessages(prev => [...prev, { id: 'err_' + Date.now(), type: 'error', text: message }]);
                    },
                }
            );
        } catch (err) {
            setMessages(prev => [...prev, { id: 'err_' + Date.now(), type: 'error', text: err.message || 'Stream failed' }]);
        } finally {
            setIsThinking(false);
        }
    };

    return (
        <div className="legal-aid-workspace">
            {/* Top Bar with Title, Status & Actions */}
            <header className="legal-aid-header">
                <div className="header-brand-block">
                    <div className="header-icon-wrap">
                        <Scale size={24} />
                    </div>
                    <div>
                        <h2>Legal Aid Intelligence</h2>
                        <p>Statutory guidance grounded in IPC, CrPC, CPC, BNS & Judicial Precedents</p>
                    </div>
                </div>

                <div className="header-actions">
                    <div className="status-pill">
                        <span className="pulse-dot" />
                        <span>India Kanoon & Bare Acts Grounded</span>
                    </div>

                    {messages.length > 0 && (
                        <button
                            type="button"
                            className="header-action-btn"
                            onClick={handleClearChat}
                            title="Start new consultation"
                        >
                            <RotateCcw size={15} />
                            <span>New Consultation</span>
                        </button>
                    )}
                </div>
            </header>

            {/* Structure Memory & Format Customization Bar */}
            <div className="structure-memory-bar">
                <div className="memory-info-chip">
                    <Zap size={14} className="text-copper" />
                    <span className="memory-label">Structure Mode:</span>
                    <span className="memory-value">{structureTitle}</span>
                    {hasSavedMemory && (
                        <span className="memory-saved-badge" title="This layout is saved in your persistent memory">
                            <BookmarkCheck size={12} /> Saved in Memory
                        </span>
                    )}
                </div>

                <div className="structure-quick-presets">
                    <button
                        type="button"
                        className={`preset-pill ${structureMode === 'standard' && !customInstructions ? 'active' : ''}`}
                        onClick={() => applyPreset('standard', 'Standard Judicial')}
                    >
                        <Scale size={13} /> Standard
                    </button>
                    <button
                        type="button"
                        className={`preset-pill ${structureMode === 'executive_brief' ? 'active' : ''}`}
                        onClick={() => applyPreset('executive_brief', 'Executive Legal Brief')}
                    >
                        <Briefcase size={13} /> Executive
                    </button>
                    <button
                        type="button"
                        className={`preset-pill ${structureMode === 'irac' ? 'active' : ''}`}
                        onClick={() => applyPreset('irac', 'IRAC Legal Framework')}
                    >
                        <Gavel size={13} /> IRAC
                    </button>
                    <button
                        type="button"
                        className={`preset-pill ${structureMode === 'bullet_points' ? 'active' : ''}`}
                        onClick={() => applyPreset('bullet_points', 'Bullet Points & Checklist')}
                    >
                        <ListChecks size={13} /> Bullets
                    </button>
                    <button
                        type="button"
                        className={`preset-pill custom-btn ${structureMode === 'custom' || customInstructions ? 'active' : ''}`}
                        onClick={() => setShowGuidanceModal(true)}
                    >
                        <SlidersHorizontal size={13} /> Guide Structure
                    </button>
                    {hasSavedMemory && (
                        <button
                            type="button"
                            className="preset-reset-btn"
                            onClick={handleResetMemory}
                            title="Reset memory to Standard Judicial default"
                        >
                            <RefreshCw size={12} /> Reset
                        </button>
                    )}
                </div>
            </div>

            {/* Compact Informational Notice */}
            <div className="legal-notice-banner">
                <ShieldAlert size={16} className="notice-icon" />
                <span>
                    <strong>Statutory Reference:</strong> This AI assistant provides research and procedural guidance. It does not constitute formal advocate-client representation.
                </span>
            </div>

            {/* Scrollable Conversation Stream */}
            <div className="legal-aid-stream">
                {messages.length === 0 ? (
                    <div className="legal-aid-empty-state">
                        <div className="empty-state-badge">
                            <Sparkles size={18} />
                            <span>Statute-Grounded Legal Q&A</span>
                        </div>
                        <h3>How can LexSetu assist your legal inquiry today?</h3>
                        <p>Ask about substantive penal liabilities, civil procedures, contract enforceability, or statutory bail.</p>

                        <div className="guidance-hint-banner">
                            <SlidersHorizontal size={15} />
                            <span><strong>Adaptive Structure:</strong> You can guide the AI to answer in any particular format (bullets, tables, IRAC, or custom). Select a preset above or click <em>Guide Structure</em> to save it into memory.</span>
                        </div>

                        <div className="suggestions-grid">
                            {SUGGESTIONS.map((item, idx) => {
                                const Icon = item.icon;
                                return (
                                    <button
                                        key={idx}
                                        type="button"
                                        className="suggestion-card"
                                        onClick={() => handleSendMessage(item.text)}
                                    >
                                        <div className="suggestion-card-header">
                                            <Icon size={16} className="suggestion-icon" />
                                            <span className="suggestion-category">{item.category}</span>
                                        </div>
                                        <p className="suggestion-text">{item.text}</p>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ) : (
                    <div className="conversation-flow">
                        {messages.map((msg) => (
                            <div key={msg.id} className="message-wrapper">
                                {msg.type === 'user' && (
                                    <div className="user-bubble">
                                        <p>{msg.text}</p>
                                    </div>
                                )}

                                {msg.type === 'error' && (
                                    <div className="error-bubble">
                                        <AlertTriangle size={18} className="error-icon" />
                                        <div>
                                            <strong>Unable to retrieve advice:</strong> {msg.text}
                                            <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>Please verify backend service status.</div>
                                        </div>
                                    </div>
                                )}

                                {msg.type === 'structured_ai' && (
                                    <div className="ai-result-container">
                                        <div className="ai-response-card">
                                            {/* Card Top Bar with Structure Badge */}
                                            <div className="card-header-bar">
                                                <div className="card-header-title">
                                                    <Scale size={18} className="card-header-icon" />
                                                    <span>LexSetu Legal Analysis</span>
                                                    <span className="card-structure-badge">
                                                        {msg.applied_structure_title || 'Standard Judicial'}
                                                    </span>
                                                    {msg.memory_active && (
                                                        <span className="card-memory-active-pill" title="Generated using your saved structure memory">
                                                            <BookmarkCheck size={11} /> Memory Active
                                                        </span>
                                                    )}
                                                </div>
                                                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                                    <button
                                                        type="button"
                                                        className="copy-card-btn"
                                                        onClick={() => downloadLegalAidPDF(msg)}
                                                        disabled={downloadingPdfId === msg.id}
                                                        title="Download formal Legal Opinion as court-grade PDF"
                                                        style={{ background: '#63120e', color: '#f9eedc', borderColor: '#8c3a2a' }}
                                                    >
                                                        {downloadingPdfId === msg.id ? (
                                                            <>
                                                                <Loader2 size={13} className="spin" />
                                                                <span>Generating PDF...</span>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <FileDown size={13} />
                                                                <span>Download PDF</span>
                                                            </>
                                                        )}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="copy-card-btn"
                                                        onClick={() => handleCopy(msg.id, msg.raw)}
                                                        title="Copy complete analysis"
                                                    >
                                                        {copiedId === msg.id ? (
                                                            <>
                                                                <Check size={14} className="text-green-600" />
                                                                <span>Copied!</span>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Copy size={14} />
                                                                <span>Copy</span>
                                                            </>
                                                        )}
                                                    </button>
                                                </div>
                                            </div>

                                            {/* Dynamic Section Rendering - Zero Mismatch */}
                                            <div className="card-sections-body">
                                                {msg.parsed && msg.parsed.sections && msg.parsed.sections.length > 0 ? (
                                                    msg.parsed.sections.map((sec) => (
                                                        <div key={sec.id} className={`response-section section-${sec.id}`}>
                                                            <div className="section-heading">
                                                                {renderSectionIcon(sec.icon)}
                                                                <h4>{sec.title}</h4>
                                                                {sec.badge && <span className="section-type-badge">{sec.badge}</span>}
                                                            </div>
                                                            <div className="section-content text-rich">
                                                                {renderFormattedText(sec.content)}
                                                            </div>
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div className="response-section direct-answer-section">
                                                        <div className="section-heading">
                                                            <FileText size={16} />
                                                            <h4>Legal Opinion</h4>
                                                        </div>
                                                        <div className="section-content text-rich">
                                                            {renderFormattedText(msg.raw)}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Professional Upgrade Plan Advisory Banner (When Blocked) */}
                                                {msg.requires_upgrade && (
                                                    <div className="upgrade-advisory-card animate-fade-in">
                                                        <div className="upgrade-advisory-header">
                                                            <div className="upgrade-crown-icon">
                                                                <Crown size={20} />
                                                            </div>
                                                            <div className="upgrade-header-text">
                                                                <h5>Plan Upgrade Required</h5>
                                                                <p>Your current plan does not allow answering this inquiry. Inquiries regarding illicit substances, sensitive ethical conduct, or active penal liabilities require the LexSetu Advocate Pro tier.</p>
                                                            </div>
                                                            <span className="upgrade-plan-pill">{msg.upgrade_tier || 'Advocate Pro'}</span>
                                                        </div>

                                                        <div className="upgrade-benefits-grid">
                                                            <div className="upgrade-benefit-item">
                                                                <Lock size={14} className="benefit-icon-gold" />
                                                                <span><strong>Privileged Legal Advisory:</strong> Attorney-client privilege under Section 126 Evidence Act / Section 132 BSA.</span>
                                                            </div>
                                                            <div className="upgrade-benefit-item">
                                                                <Gavel size={14} className="benefit-icon-gold" />
                                                                <span><strong>Empanelled Counsel Connect:</strong> Direct 1-on-1 strategy session with practicing High Court advocates.</span>
                                                            </div>
                                                            <div className="upgrade-benefit-item">
                                                                <ShieldCheck size={14} className="benefit-icon-gold" />
                                                                <span><strong>Forensic Case & Trial Review:</strong> Customized defense analysis and statutory limitation audit.</span>
                                                            </div>
                                                        </div>

                                                        <div className="upgrade-card-actions">
                                                            <button className="primary-btn upgrade-cta-btn" onClick={() => setShowUpgradeModal(true)}>
                                                                <Crown size={15} /> Upgrade to Advocate Pro
                                                            </button>
                                                            <button className="outline btn-sm upgrade-consult-btn" onClick={() => setShowUpgradeModal(true)}>
                                                                Schedule Privileged Consultation <ArrowRight size={14} />
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Card Footer with Tags and Disclaimer */}
                                            <div className="card-footer-bar">
                                                <div className="card-tags-list">
                                                    {msg.data.tags.map((tag, i) => (
                                                        <span key={i} className="statute-tag">
                                                            {formatCategoryTag(tag)}
                                                        </span>
                                                    ))}
                                                </div>
                                                {msg.parsed?.disclaimer && (
                                                    <p className="footer-disclaimer-note">
                                                        {msg.parsed.disclaimer}
                                                    </p>
                                                )}
                                            </div>
                                        </div>

                                        <TranslateAction
                                            sourceType="legal_aid"
                                            text={msg.raw}
                                            citations={msg.data.sources}
                                        />

                                        {/* Upgrade to Pro for better reasoning and features - Presented after EVERY result */}
                                        {!msg.requires_upgrade && (
                                            <div className="pro-reasoning-callout animate-fade-in">
                                                <div className="pro-callout-left">
                                                    <div className="pro-crown-badge">
                                                        <Crown size={16} />
                                                        <span>LEXSETU PRO</span>
                                                    </div>
                                                    <div className="pro-callout-text">
                                                        <h5>Upgrade to Pro for Deeper Multi-Step Legal Reasoning</h5>
                                                        <p>Unlock Groq extended reasoning chains, verbatim Supreme Court precedent ratios, and instant court pleading drafts.</p>
                                                    </div>
                                                </div>
                                                <button
                                                    type="button"
                                                    className="primary-btn pro-callout-cta"
                                                    onClick={() => setShowUpgradeModal(true)}
                                                >
                                                    <Sparkles size={14} /> Upgrade to Pro
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Live, backend-truthful pipeline stage trace -- same visual language as
                    Verify Filing's CitationStageList, driven by real SSE stage events,
                    never a client-side timer. */}
                {isThinking && (
                    <div className="thinking-indicator-wrapper">
                        <div className="thinking-card thinking-card-stages">
                            <PipelineStageList
                                stages={legalAidStages}
                                stageOrder={LEGAL_AID_STAGE_ORDER}
                                stageLabels={LEGAL_AID_STAGE_LABELS}
                                title={`LexSetu Neural Engine active • Applying ${structureTitle}`}
                            />
                        </div>
                        {connectionLost && (
                            <p className="stage-connection-lost">
                                <AlertTriangle size={14} /> Couldn't confirm progress — result may still be correct.
                            </p>
                        )}
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Bottom Query Input Assembly */}
            <div className="legal-aid-input-area">
                <div className="input-box-wrapper">
                    <Search size={20} className="input-leading-icon" />
                    <textarea
                        ref={inputRef}
                        className="legal-aid-textarea"
                        placeholder="Ask any legal question (e.g. 'Can anticipatory bail be granted in non-bailable offences?') or guide format..."
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSendMessage();
                            }
                        }}
                        rows={1}
                        disabled={isThinking}
                    />
                    <div className="input-actions-cluster">
                        <button
                            type="button"
                            className={`mic-button ${isListening ? 'listening' : ''}`}
                            onClick={toggleListening}
                            title={isListening ? "Listening... click to stop" : "Voice dictation (Indian English)"}
                        >
                            {isListening ? <MicOff size={18} /> : <Mic size={18} />}
                        </button>
                        <button
                            type="button"
                            className="send-button"
                            onClick={() => handleSendMessage()}
                            disabled={!inputValue.trim() || isThinking}
                            title="Submit legal inquiry"
                        >
                            {isThinking ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
                        </button>
                    </div>
                </div>

                <div className="input-footer-note">
                    <Shield size={12} />
                    <span>Confidential queries: Personal identifying information is not required. LexSetu complies with Indian privacy norms.</span>
                </div>
            </div>

            {/* Guide AI Structure & Memory Modal */}
            {showGuidanceModal && (
                <div className="legal-aid-modal-backdrop" onClick={() => setShowGuidanceModal(false)}>
                    <div className="guidance-modal-card animate-fade-in" onClick={e => e.stopPropagation()}>
                        <button className="modal-close-btn" onClick={() => setShowGuidanceModal(false)}><X size={18} /></button>
                        <div className="guidance-modal-header">
                            <div className="modal-icon-glow"><SlidersHorizontal size={24} /></div>
                            <h3>Guide AI Output Structure & Memory</h3>
                            <p>Customize how LexSetu AI presents answers so it matches your preferred layout without mismatch.</p>
                        </div>

                        <div className="guidance-modal-body">
                            <label className="guidance-input-label">Select a Structure Preset:</label>
                            
                            <div className="guidance-presets-grid">
                                <button
                                    type="button"
                                    className={`guidance-preset-btn ${structureMode === 'standard' && !customInstructions ? 'selected' : ''}`}
                                    onClick={() => {
                                        setStructureMode('standard');
                                        setStructureTitle('Standard Judicial');
                                        setCustomInstructions('');
                                    }}
                                >
                                    <strong>🏛️ Standard Judicial</strong>
                                    <span>Direct Answer, Statutory Grounds, Precedents, Actionable Insight</span>
                                </button>
                                <button
                                    type="button"
                                    className={`guidance-preset-btn ${structureMode === 'executive_brief' ? 'selected' : ''}`}
                                    onClick={() => {
                                        setStructureMode('executive_brief');
                                        setStructureTitle('Executive Legal Brief');
                                        setCustomInstructions('');
                                    }}
                                >
                                    <strong>📋 Executive Brief</strong>
                                    <span>Executive Summary, Statutory Position, Precedents, Strategic Roadmap</span>
                                </button>
                                <button
                                    type="button"
                                    className={`guidance-preset-btn ${structureMode === 'irac' ? 'selected' : ''}`}
                                    onClick={() => {
                                        setStructureMode('irac');
                                        setStructureTitle('IRAC Legal Framework');
                                        setCustomInstructions('');
                                    }}
                                >
                                    <strong>⚖️ IRAC Methodology</strong>
                                    <span>Issue, Governing Rule, Factual Application, Legal Conclusion</span>
                                </button>
                                <button
                                    type="button"
                                    className={`guidance-preset-btn ${structureMode === 'bullet_points' ? 'selected' : ''}`}
                                    onClick={() => {
                                        setStructureMode('bullet_points');
                                        setStructureTitle('Actionable Bullet Points');
                                        setCustomInstructions('');
                                    }}
                                >
                                    <strong>📝 Bullet & Checklist</strong>
                                    <span>Key Summary, Statutory Provisions bullets, Actionable Checklist</span>
                                </button>
                            </div>

                            <div className="custom-guidance-field">
                                <label>Or write custom structural instructions for the AI:</label>
                                <textarea
                                    rows={3}
                                    value={customInstructions}
                                    onChange={(e) => {
                                        setCustomInstructions(e.target.value);
                                        if (e.target.value.trim()) {
                                            setStructureMode('custom');
                                            setStructureTitle('Custom Guided Structure');
                                        }
                                    }}
                                    placeholder="e.g. 'Format in 3 numbered sections: 1. Legal Position, 2. Strategy Table, 3. Urgent Deadlines. Keep it under 250 words.'"
                                />
                            </div>

                            <div className="memory-toggle-row">
                                <label className="memory-checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={rememberGuidance}
                                        onChange={(e) => setRememberGuidance(e.target.checked)}
                                    />
                                    <span>💾 <strong>Save this structure in memory</strong> for all future AI Legal Aid answers</span>
                                </label>
                            </div>

                            <div className="modal-action-row">
                                <button type="button" className="outline" onClick={() => setShowGuidanceModal(false)}>Cancel</button>
                                <button type="button" className="primary-btn cta-upgrade-now" onClick={handleSaveGuidance}>
                                    Apply & Save Structure
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Professional Upgrade to Pro Modal */}
            {showUpgradeModal && (
                <div className="legal-aid-modal-backdrop" onClick={() => setShowUpgradeModal(false)}>
                    <div className="upgrade-modal-card animate-fade-in" onClick={e => e.stopPropagation()}>
                        <button className="modal-close-btn" onClick={() => setShowUpgradeModal(false)}><X size={18} /></button>
                        <div className="upgrade-modal-header">
                            <div className="modal-crown-glow"><Crown size={28} /></div>
                            <h3>LexSetu Advocate Pro & Enterprise</h3>
                            <p>High-Compute Reasoning, Full Landmark Precedents & Direct Empanelled Counsel</p>
                        </div>

                        {upgradeRequested ? (
                            <div className="upgrade-success-state animate-fade-in">
                                <CheckCircle2 size={40} className="text-success-gold" />
                                <h4>Pro Upgrade Request Received</h4>
                                <p>Our senior legal practice coordinator has received your account inquiry. We will contact your verified account within 15 minutes.</p>
                                <button className="primary-btn" onClick={() => { setShowUpgradeModal(false); setUpgradeRequested(false); }}>Close</button>
                            </div>
                        ) : (
                            <div className="upgrade-modal-body">
                                <div className="plan-comparison-box">
                                    <div className="plan-feature-row">
                                        <span className="feature-name">Deep Legal Reasoning Models</span>
                                        <span className="feature-val included">Groq gpt-oss-120b Chain-of-Thought</span>
                                    </div>
                                    <div className="plan-feature-row">
                                        <span className="feature-name">Attorney-Client Privilege Protection</span>
                                        <span className="feature-val included">Sec. 126 IEA / Sec. 132 BSA Protected</span>
                                    </div>
                                    <div className="plan-feature-row">
                                        <span className="feature-name">Empanelled Senior Advocate Connect</span>
                                        <span className="feature-val included">Direct 1-on-1 Consultation</span>
                                    </div>
                                    <div className="plan-feature-row">
                                        <span className="feature-name">Active Penal & Enforcement Strategy</span>
                                        <span className="feature-val included">Custom Trial Briefs & Precedents</span>
                                    </div>
                                    <div className="plan-feature-row">
                                        <span className="feature-name">Dedicated GPU Compute</span>
                                        <span className="feature-val included">Zero-Queue Priority SLA</span>
                                    </div>
                                </div>

                                <div className="modal-action-row">
                                    <button className="outline" onClick={() => setShowUpgradeModal(false)}>Cancel</button>
                                    <button className="primary-btn cta-upgrade-now" onClick={() => setUpgradeRequested(true)}>
                                        Request Advocate Pro Upgrade
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default LegalAid;
