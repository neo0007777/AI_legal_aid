import { useState, useRef, useEffect } from 'react';
import {
    Send, Sparkles, Scale, BookOpen, AlertTriangle,
    ShieldAlert, Search, Loader2, FileText, Copy, Check,
    Mic, MicOff, RotateCcw, X, Shield, Gavel, HelpCircle,
    Crown, Lock, ArrowRight, ShieldCheck, CheckCircle2, FileDown
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { downloadFileFromBlob, exportPdfFromApi } from '../utils/downloadHelper';
import './LegalAid.css';

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

const parseAnswer = (rawAnswer) => {
    if (!rawAnswer) return { directAnswer: '', legalBasis: '', precedents: '', insight: '', disclaimer: '' };

    const sections = {
        directAnswer: '',
        legalBasis: '',
        precedents: '',
        insight: '',
        disclaimer: '',
    };

    // Resilient regex that matches markdown headers, asterisks, hashes, colons
    const directMatch = rawAnswer.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?DIRECT ANSWER:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?LEGAL BASIS:?|$)/i);
    const legalMatch = rawAnswer.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?LEGAL BASIS:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?BINDING PRECEDENTS:?|$)/i);
    const precedentsMatch = rawAnswer.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?BINDING PRECEDENTS:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?ACTIONABLE INSIGHT:?|$)/i);
    const insightMatch = rawAnswer.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?ACTIONABLE INSIGHT:?(?:\*\*)?\s*([\s\S]*?)(?=(?:^|\n)(?:#+\s*)?(?:\*\*)?DISCLAIMER:?|$)/i);
    const disclaimerMatch = rawAnswer.match(/(?:^|\n)(?:#+\s*)?(?:\*\*)?DISCLAIMER:?(?:\*\*)?\s*([\s\S]*?)$/i);

    if (directMatch && directMatch[1].trim()) sections.directAnswer = directMatch[1].trim();
    if (legalMatch && legalMatch[1].trim()) sections.legalBasis = legalMatch[1].trim();
    if (precedentsMatch && precedentsMatch[1].trim()) sections.precedents = precedentsMatch[1].trim();
    if (insightMatch && insightMatch[1].trim()) sections.insight = insightMatch[1].trim();
    if (disclaimerMatch && disclaimerMatch[1].trim()) sections.disclaimer = disclaimerMatch[1].trim();

    if (!sections.directAnswer && !sections.legalBasis) {
        sections.directAnswer = rawAnswer.trim();
    }

    return sections;
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

const cleanAndNormalizeText = (text) => {
    if (!text) return '';
    return text
        .replace(/[\u202F\u00A0\u2000-\u200A]/g, ' ') // normalize all strange unicode spaces
        .replace(/\s*---+$/, '') // remove trailing markdown lines
        .trim();
};

const formatRichInline = (rawText) => {
    if (!rawText) return null;
    const text = cleanAndNormalizeText(rawText);

    // Regex to match:
    // 1. ***bold italic***
    // 2. **bold**
    // 3. *italic* or _italic_
    // 4. `code`
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
            elements.push(<div key={idx} className="aid-line-spacer" />);
            return;
        }

        // Horizontal separator line --- or ***
        if (/^[-*]{3,}$/.test(trimmed)) {
            elements.push(<hr key={idx} className="aid-divider" />);
            return;
        }

        // Bullet point: - item, * item, • item
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

        // Numbered list: e.g. "1. " or "5. "
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

const LegalAid = () => {
    const { getAuthHeaders } = useAuth();

    const [messages, setMessages] = useState([]);
    const [inputValue, setInputValue] = useState('');
    const [isThinking, setIsThinking] = useState(false);
    const [loadingStage, setLoadingStage] = useState(0);
    const [copiedId, setCopiedId] = useState(null);
    const [downloadingPdfId, setDownloadingPdfId] = useState(null);
    const [isListening, setIsListening] = useState(false);
    const [showUpgradeModal, setShowUpgradeModal] = useState(false);
    const [upgradeRequested, setUpgradeRequested] = useState(false);

    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const recognitionRef = useRef(null);

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

                recognition.onerror = () => {
                    setIsListening(false);
                };

                recognition.onend = () => {
                    setIsListening(false);
                };

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
            alert('Voice input is not supported in this browser. Please use Chrome, Edge, or Safari.');
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
                console.error('Speech recognition error:', err);
                setIsListening(false);
            }
        }
    };

    const handleCopy = (id, text) => {
        navigator.clipboard.writeText(text);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const handleClearChat = () => {
        if (messages.length === 0) return;
        if (window.confirm("Start a new consultation? This will clear current conversation.")) {
            setMessages([]);
            setInputValue('');
        }
    };

    const handleSend = async (queryText) => {
        const text = queryText || inputValue;
        if (!text.trim() || isThinking) return;

        const userMsg = { id: 'msg_' + Date.now(), type: 'user', text };
        setMessages(prev => [...prev, userMsg]);
        setInputValue('');
        setIsThinking(true);
        setLoadingStage(0);

        const stageTimer1 = setTimeout(() => setLoadingStage(1), 1200);
        const stageTimer2 = setTimeout(() => setLoadingStage(2), 2500);

        try {
            const response = await fetch('/api/legal-aid/ask', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ question: text, n_results: 3 }),
            });

            clearTimeout(stageTimer1);
            clearTimeout(stageTimer2);

            if (!response.ok) {
                let msg = 'Request failed';
                try { const e = await response.json(); msg = e.detail || msg; } catch { msg = `Server error (${response.status})`; }
                throw new Error(msg);
            }

            const data = await response.json();
            const parsed = parseAnswer(data.answer);

            const aiMsg = {
                id: 'ai_' + Date.now(),
                type: 'structured_ai',
                question: text,
                raw: data.answer,
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
                data: {
                    answer: parsed.directAnswer,
                    legal_basis: parsed.legalBasis || 'Refer to relevant Indian statutes and case law.',
                    references: parsed.precedents ? parsed.precedents.split('\n').map(r => r.trim()).filter(Boolean) : [],
                    insight: parsed.insight || '',
                    disclaimer: parsed.disclaimer,
                    tags: data.sources?.map(s => s.category).filter((v, i, a) => a.indexOf(v) === i).slice(0, 3) || [],
                    sources: data.sources || [],
                }
            };

            setMessages(prev => [...prev, aiMsg]);
        } catch (err) {
            const errorMsg = {
                id: 'err_' + Date.now(),
                type: 'error',
                text: err.message,
            };
            setMessages(prev => [...prev, errorMsg]);
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
                            <Sparkles size={20} />
                            <span>AI Legal Research Suite</span>
                        </div>
                        <h3>How can LexSetu assist your legal research today?</h3>
                        <p className="empty-state-subtitle">
                            Ask procedural questions, verify criminal provisions, clarify tenancy issues, or explore remedies under Indian law.
                        </p>

                        <div className="suggestions-grid">
                            {SUGGESTIONS.map((sug, idx) => (
                                <button
                                    key={idx}
                                    type="button"
                                    className="suggestion-card"
                                    onClick={() => handleSend(sug.text)}
                                >
                                    <div className="suggestion-card-header">
                                        <sug.icon size={18} className="suggestion-icon" />
                                        <span className="suggestion-category">{sug.category}</span>
                                    </div>
                                    <p className="suggestion-text">{sug.text}</p>
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="messages-container">
                        {messages.map((msg) => (
                            <div key={msg.id} className={`chat-message-row ${msg.type === 'user' ? 'user-row' : 'ai-row'}`}>
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
                                    <div className="ai-response-card">
                                        <div className="card-header-bar">
                                            <div className="card-header-title">
                                                <Scale size={18} className="card-header-icon" />
                                                <span>LexSetu Legal Analysis</span>
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

                                        <div className="card-sections-body">
                                            {/* Direct Answer */}
                                            {msg.data.answer && (
                                                <div className="response-section direct-answer-section">
                                                    <div className="section-heading">
                                                        <FileText size={16} />
                                                        <h4>Direct Answer</h4>
                                                    </div>
                                                    <div className="section-content text-rich">
                                                        {renderFormattedText(msg.data.answer)}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Legal Basis */}
                                            {msg.data.legal_basis && (
                                                <div className="response-section legal-basis-section">
                                                    <div className="section-heading">
                                                        <Scale size={16} />
                                                        <h4>Statutory Grounds & Legal Basis</h4>
                                                    </div>
                                                    <div className="section-content text-rich">
                                                        {renderFormattedText(msg.data.legal_basis)}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Precedents Cited */}
                                            {msg.data.references && msg.data.references.length > 0 && (
                                                <div className="response-section precedents-section">
                                                    <div className="section-heading">
                                                        <BookOpen size={16} />
                                                        <h4>Judicial Precedents & Authorities Cited</h4>
                                                    </div>
                                                    <div className="precedents-list">
                                                        {msg.data.references.map((ref, i) => {
                                                            const cleanRef = ref
                                                                .replace(/^(\d+[\.\)]\s*|[-•*]\s*)+/, '')
                                                                .replace(/\s*---+$/, '')
                                                                .trim();
                                                            if (!cleanRef || cleanRef.toLowerCase().includes('no direct precedent required')) {
                                                                return null;
                                                            }
                                                            return (
                                                                <div key={i} className="precedent-item">
                                                                    <span className="precedent-index-badge">{i + 1}</span>
                                                                    <div className="precedent-content">
                                                                        {formatRichInline(cleanRef)}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Actionable Insight */}
                                            {msg.data.insight && (
                                                <div className="response-section insight-section">
                                                    <div className="section-heading">
                                                        <AlertTriangle size={16} />
                                                        <h4>Actionable Counsel & Strategic Steps</h4>
                                                    </div>
                                                    <div className="section-content text-rich">
                                                        {renderFormattedText(msg.data.insight)}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Professional Upgrade Plan Advisory Banner */}
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

                                        {/* Card Footer with Tags */}
                                        <div className="card-footer-bar">
                                            <div className="card-tags-list">
                                                {msg.data.tags.map((tag, i) => (
                                                    <span key={i} className="statute-tag">
                                                        {formatCategoryTag(tag)}
                                                    </span>
                                                ))}
                                            </div>
                                            {msg.data.disclaimer && (
                                                <p className="footer-disclaimer-note">
                                                    {msg.data.disclaimer}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* AI Thinking Animation */}
                {isThinking && (
                    <div className="thinking-indicator-wrapper">
                        <div className="thinking-card">
                            <Loader2 size={20} className="spin-loader" />
                            <div className="thinking-text-flow">
                                <strong>
                                    {loadingStage === 0 && "Parsing legal query & identifying jurisdiction..."}
                                    {loadingStage === 1 && "Cross-referencing statutory database (IPC, CrPC, CPC)..."}
                                    {loadingStage === 2 && "Synthesizing binding precedents and actionable insight..."}
                                </strong>
                                <span className="thinking-subtext">LexSetu Neural Engine active</span>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Bottom Query Input Assembly */}
            <div className="legal-aid-input-area">
                <div className="input-box-wrapper">
                    <Search size={20} className="input-leading-icon" />
                    <input
                        ref={inputRef}
                        type="text"
                        className="legal-query-input"
                        placeholder="Ask about bail, property partition, cheques, contracts, consumer redressal..."
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSend();
                            }
                        }}
                        disabled={isThinking}
                    />

                    {inputValue.trim() && (
                        <button
                            type="button"
                            className="input-clear-btn"
                            onClick={() => setInputValue('')}
                            title="Clear input"
                        >
                            <X size={16} />
                        </button>
                    )}

                    <button
                        type="button"
                        className={`input-voice-btn ${isListening ? 'listening' : ''}`}
                        onClick={toggleListening}
                        title={isListening ? "Listening... click to stop" : "Voice dictation (English / Hindi)"}
                    >
                        {isListening ? <MicOff size={18} /> : <Mic size={18} />}
                    </button>

                    <button
                        type="button"
                        className={`input-submit-btn ${inputValue.trim() ? 'can-send' : ''}`}
                        onClick={() => handleSend()}
                        disabled={!inputValue.trim() || isThinking}
                        title="Submit query (Enter)"
                    >
                        <Send size={18} />
                    </button>
                </div>

                <div className="input-footer-note">
                    <Shield size={12} />
                    <span>Confidential queries: Personal identifying information is not required. LexSetu complies with Indian privacy norms.</span>
                </div>
            </div>

            {/* Professional Upgrade to Pro Modal */}
            {showUpgradeModal && (
                <div className="legal-aid-modal-backdrop" onClick={() => setShowUpgradeModal(false)}>
                    <div className="upgrade-modal-card animate-fade-in" onClick={e => e.stopPropagation()}>
                        <button className="modal-close-btn" onClick={() => setShowUpgradeModal(false)}><X size={18} /></button>
                        <div className="upgrade-modal-header">
                            <div className="modal-crown-glow"><Crown size={28} /></div>
                            <h3>LexSetu Advocate Pro & Enterprise</h3>
                            <p>Privileged Legal Advisory, High-Stakes Defense & Direct Empanelled Counsel</p>
                        </div>

                        {upgradeRequested ? (
                            <div className="upgrade-success-state animate-fade-in">
                                <CheckCircle2 size={40} className="text-success-gold" />
                                <h4>Consultation Request Received</h4>
                                <p>Our senior legal practice coordinator has received your privileged inquiry. We will contact your verified account within 15 minutes.</p>
                                <button className="primary-btn" onClick={() => { setShowUpgradeModal(false); setUpgradeRequested(false); }}>Close</button>
                            </div>
                        ) : (
                            <div className="upgrade-modal-body">
                                <div className="plan-comparison-box">
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
                                        <span className="feature-name">Turnaround SLA</span>
                                        <span className="feature-val included">Priority 1-Hour SLA</span>
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
