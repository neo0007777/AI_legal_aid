import React, { useState } from 'react';
import './Home.css';
import {
    ArrowRight, Search, FileText, Scale, BookOpen, Clock, Bot, CheckCircle,
    AlertTriangle, Shield, Sparkles, CircleCheck, UploadCloud, Cpu,
    PlayCircle, Loader, FileSearch, Zap, Brain
} from 'lucide-react';
import Modal from '../components/Modal';
import { useNavigate } from 'react-router-dom';

// --- DATA ---
const SUGGESTIONS = [
    "Analyze Employee Agreement A & B",
    "IPC Section 420: Cheating and dishonestly inducing delivery",
    "Navtej Singh Johar v. Union of India",
    "Bail Application under CrPC Section 439",
    "Contract Conflict: Non-compete clauses"
];

// --- BOTANICAL LEAF & WATERMARK BACKGROUND ---
const BackgroundDecorations = () => (
    <div className="bg-decorations-layer">
        {/* Top-Left Botanical Leaf Branch */}
        <svg className="bg-leaf-top-left" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M20 180 Q80 120 160 40" stroke="#c98659" strokeWidth="1.5" opacity="0.3" fill="none" />
            <path d="M40 150 Q20 130 30 110 Q50 120 40 150Z" fill="#dfa46f" opacity="0.25" />
            <path d="M70 120 Q50 100 60 80 Q80 90 70 120Z" fill="#c98659" opacity="0.2" />
            <path d="M100 90 Q80 70 90 50 Q110 60 100 90Z" fill="#dfa46f" opacity="0.2" />
            <path d="M130 60 Q110 40 120 20 Q140 30 130 60Z" fill="#ecbf89" opacity="0.3" />
        </svg>

        {/* Top-Center Scales of Justice Watermark */}
        <svg className="bg-scales-watermark" viewBox="0 0 200 160" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M100 20 L100 140 M40 50 L160 50" stroke="#c98659" strokeWidth="1.5" strokeDasharray="3 3" opacity="0.2" />
            <path d="M40 50 L20 100 Q40 120 60 100 Z" stroke="#c98659" strokeWidth="1.2" fill="#f1d1a6" opacity="0.15" />
            <path d="M160 50 L140 100 Q160 120 180 100 Z" stroke="#c98659" strokeWidth="1.2" fill="#f1d1a6" opacity="0.15" />
            <circle cx="100" cy="20" r="6" stroke="#c98659" strokeWidth="1.2" fill="none" opacity="0.25" />
        </svg>

        {/* Bottom-Left Open Book & Leaf Art */}
        <div className="bg-book-leaves-wrapper">
            <svg className="bg-book-leaves" viewBox="0 0 350 220" fill="none" xmlns="http://www.w3.org/2000/svg">
                {/* Flowing Waves */}
                <path d="M0 160 Q120 80 350 140" stroke="#dfa46f" strokeWidth="1" opacity="0.25" fill="none" />
                <path d="M0 180 Q140 100 350 170" stroke="#c98659" strokeWidth="1" opacity="0.2" fill="none" />
                {/* Botanical Stem */}
                <path d="M10 200 Q60 140 120 40" stroke="#8c3a2a" strokeWidth="1.8" opacity="0.3" fill="none" />
                <path d="M30 180 Q10 160 20 140 Q40 150 30 180Z" fill="#c98659" opacity="0.35" />
                <path d="M55 150 Q35 130 45 110 Q65 120 55 150Z" fill="#dfa46f" opacity="0.3" />
                <path d="M80 120 Q60 100 70 80 Q90 90 80 120Z" fill="#ecbf89" opacity="0.35" />
                <path d="M105 90 Q85 70 95 50 Q115 60 105 90Z" fill="#c98659" opacity="0.25" />
            </svg>
        </div>
    </div>
);

// --- SCALES & BOOKS ILLUSTRATION (Inside Mockup Box Bottom-Right) ---


// --- MAIN COMPONENT ---
const Home = () => {
    const navigate = useNavigate();

    const [searchQuery, setSearchQuery] = useState('');
    const [modalConfig, setModalConfig] = useState({
        isOpen: false,
        title: '',
        type: null,
        data: null
    });

    const openModal = (title, type, data) => {
        setModalConfig({ isOpen: true, title, type, data });
    };

    const closeModal = () => {
        setModalConfig({ ...modalConfig, isOpen: false });
    };

    const mockStatuteData = {
        title: "Section 62 - Indian Contract Act, 1872",
        explanation: "If the parties to a contract agree to substitute a new contract for it, or to rescind or alter it, the original contract need not be performed.",
        keyPoints: [
            "Novation: Substitution of an existing contract with a new one.",
            "Rescission: Cancellation of the contract by mutual agreement.",
            "Alteration: Modification of terms with the consent of all parties.",
            "Binding Requirement: The new agreement must be valid and enforceable."
        ]
    };

    const mockDraftData = {
        title: "Draft Output: Software Service Level Agreement (SLA)",
        content: "This Software Service Level Agreement (the \"Agreement\") is entered into on this 15th day of October, 2026, by and between Nexus Tech Solutions Private Limited (the \"Provider\") and Globex Retail Corporation (the \"Client\").\n\n1. SCOPE OF SERVICES\nThe Provider agrees to deliver enterprise resource planning (ERP) hosting across all Tier-1 infrastructure endpoints. The guaranteed uptime objective is 99.9% measured monthly.\n\n2. GOVERNING LAW\nThis Agreement shall be constructed, governed, and enforced in accordance with the laws of the Republic of India without regard to conflict of law principles."
    };

    const mockCaseData = {
        title: "Central Inland Water Transport Corp v. Brojo Nath Ganguly",
        citation: "1986 AIR 1571, 1986 SCR (2) 278",
        summary: "The Supreme Court of India held that courts will not enforce, and will strike down, an unfair and unreasonable contract or an unfair and unreasonable clause in a contract entered into between parties who are not equal in bargaining power.",
        impact: "Established the principle against 'unconscionable bargains' in Indian contract law, specifically protecting weaker parties against massive corporations or state entities."
    };

    const [isFocused, setIsFocused] = useState(false);
    const [activeSuggestion, setActiveSuggestion] = useState(-1);
    const [demoState, setDemoState] = useState('idle');

    const filteredSuggestions = SUGGESTIONS.filter(s =>
        s.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const handleKeyDown = (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveSuggestion(prev => (prev < filteredSuggestions.length - 1 ? prev + 1 : prev));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveSuggestion(prev => (prev > 0 ? prev - 1 : 0));
        } else if (e.key === 'Enter') {
            if (activeSuggestion >= 0 && activeSuggestion < filteredSuggestions.length) {
                setSearchQuery(filteredSuggestions[activeSuggestion]);
            }
            setIsFocused(false);
            if (searchQuery.includes("Agreement") || searchQuery.includes("Contract")) {
                runDemo(true);
            } else {
                navigate('/case-finder');
            }
        }
    };

    const handleSuggestionClick = (suggestion) => {
        setSearchQuery(suggestion);
        setIsFocused(false);
        if (suggestion.includes("Agreement") || suggestion.includes("Contract")) {
            runDemo(true);
        }
    };

    const runDemo = (skipTyping = false) => {
        if (demoState !== 'idle') return;
        if (skipTyping) { triggerDemoSteps(); return; }
        setDemoState('typing');
        setSearchQuery('');
        const targetQuery = SUGGESTIONS[0];
        let i = 0;
        const typingInterval = setInterval(() => {
            setSearchQuery(targetQuery.substring(0, i + 1));
            i++;
            if (i >= targetQuery.length) { clearInterval(typingInterval); setTimeout(() => triggerDemoSteps(), 600); }
        }, 40);
    };

    const triggerDemoSteps = () => {
        setDemoState('uploading');
        setTimeout(() => {
            setDemoState('scanning');
            setTimeout(() => {
                setDemoState('extracting');
                setTimeout(() => {
                    setDemoState('cross_referencing');
                    setTimeout(() => {
                        setDemoState('conflict_detected');
                        setSearchQuery("Analyze Employee Agreement A & B");
                    }, 1500);
                }, 1500);
            }, 1200);
        }, 1200);
    };

    const getStepStatus = (stepName, currentState) => {
        const states = ['idle', 'typing', 'uploading', 'scanning', 'extracting', 'cross_referencing', 'conflict_detected'];
        const stepIndex = states.indexOf(stepName);
        const currentIndex = states.indexOf(currentState);
        if (currentIndex > stepIndex) return 'done';
        if (currentIndex === stepIndex) return 'active';
        return 'pending';
    };

    const resetDashboard = () => {
        setDemoState('idle');
        setSearchQuery('');
    };

    return (
        <div className="dashboard-wrapper animate-fade-in">
            {/* Background Botanical & Wave Artwork */}
            <BackgroundDecorations />

            <div className="dashboard-grid">
                {/* LEFT: Command Center */}
                <div className="command-center stagger-1">
                    <div className="badge-new">
                        <Scale size={15} />
                        <span>AI Document Workspace</span>
                    </div>

                    <h1 className="hero-title">
                        Drop contracts, <br />
                        Identify <span className="highlight-gradient">Conflicts.</span>
                    </h1>

                    <p className="hero-subtitle">
                        NyayaSetu cross-references 50M+ precedents and maps Indian Contract Act nuances in seconds.
                    </p>

                    <div className="hero-search-container search-container-relative">
                        <div className="search-bar-mockup">
                            <Search size={20} className="search-icon-mock" />
                            <input
                                type="text"
                                placeholder="Search queries or describe documents..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                onFocus={() => setIsFocused(true)}
                                onBlur={() => setTimeout(() => setIsFocused(false), 200)}
                                onKeyDown={handleKeyDown}
                            />
                            {searchQuery && demoState === 'conflict_detected' ? (
                                <button className="search-action-btn" onClick={resetDashboard} style={{ background: '#f1d1a6', color: '#63120e' }}>
                                    Clear
                                </button>
                            ) : (
                                <button className="search-action-btn" onClick={() => navigate('/case-finder')}>
                                    <ArrowRight size={20} />
                                </button>
                            )}
                        </div>

                        {isFocused && searchQuery && filteredSuggestions.length > 0 && demoState === 'idle' && (
                            <div className="suggestions-dropdown">
                                {filteredSuggestions.map((s, idx) => (
                                    <div
                                        key={idx}
                                        className={`suggestion-item ${activeSuggestion === idx ? 'active' : ''}`}
                                        onClick={() => handleSuggestionClick(s)}
                                    >
                                        <Search size={14} /> {s}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="hero-cta-group">
                        <button className="primary-btn" onClick={() => navigate('/case-finder')}>
                            <Scale size={18} /> Start Research
                        </button>
                        <button className="secondary-btn" onClick={() => runDemo(false)}>
                            <PlayCircle size={18} /> Quick Demo
                        </button>
                    </div>

                    {/* Bottom Stats Bar */}
                    <div className="stats-bar">
                        <div className="stat-item">
                            <div className="stat-icon-ring">
                                <BookOpen size={20} strokeWidth={1.8} />
                            </div>
                            <div>
                                <strong>50M+</strong>
                                <span>Precedents Indexed</span>
                            </div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-icon-ring">
                                <Brain size={20} strokeWidth={1.8} />
                            </div>
                            <div>
                                <strong>AI-Powered</strong>
                                <span>Legal Research</span>
                            </div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-icon-ring">
                                <Shield size={20} strokeWidth={1.8} />
                            </div>
                            <div>
                                <strong>Secure &</strong>
                                <span>Confidential</span>
                            </div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-icon-ring">
                                <Zap size={20} strokeWidth={1.8} />
                            </div>
                            <div>
                                <strong>Results in</strong>
                                <span>Seconds</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* RIGHT: Workspace Visual */}
                <div className="workspace-visual stagger-2">
                    <div className="advanced-mockup-window">
                        <div className="mockup-header-advanced">
                            <div className="mockup-tabs">
                                <div className="mockup-tab active">Contract Analysis</div>
                                <div className="mockup-tab">Precedent Search</div>
                            </div>
                        </div>
                        <div className="mockup-body-advanced">
                            {(demoState === 'idle' || demoState === 'typing') && (
                                <div className="empty-state animate-fade-in">
                                    <div className="inner-dashed-frame">
                                        <div className="upload-icon-ring">
                                            <UploadCloud size={36} strokeWidth={1.5} />
                                        </div>
                                        <p className="upload-title">Upload documents</p>
                                        <p className="upload-sub">or enter a query to begin<br />AI analysis.</p>
                                    </div>

                                </div>
                            )}

                            {['uploading', 'scanning', 'extracting', 'cross_referencing'].includes(demoState) && (
                                <div className="processing-sequence animate-fade-in">
                                    <div className={`process-step ${getStepStatus('uploading', demoState)}`}>
                                        {getStepStatus('uploading', demoState) === 'active' ? <Loader size={18} className="spin" /> : <CircleCheck size={18} />}
                                        Uploading Party_A_Agreement.pdf & Party_B_Addendum.pdf...
                                    </div>
                                    {getStepStatus('scanning', demoState) !== 'pending' && (
                                        <div className={`process-step ${getStepStatus('scanning', demoState)}`}>
                                            {getStepStatus('scanning', demoState) === 'active' ? <Loader size={18} className="spin" /> : <CircleCheck size={18} />}
                                            Scanning 50M+ judgments & regulatory frameworks...
                                        </div>
                                    )}
                                    {getStepStatus('extracting', demoState) !== 'pending' && (
                                        <div className={`process-step ${getStepStatus('extracting', demoState)}`}>
                                            {getStepStatus('extracting', demoState) === 'active' ? <Loader size={18} className="spin" /> : <CircleCheck size={18} />}
                                            Extracting relevant precedents and parsing clauses...
                                        </div>
                                    )}
                                    {getStepStatus('cross_referencing', demoState) !== 'pending' && (
                                        <div className={`process-step ${getStepStatus('cross_referencing', demoState)}`}>
                                            {getStepStatus('cross_referencing', demoState) === 'active' ? <Loader size={18} className="spin" /> : <CircleCheck size={18} />}
                                            Cross-referencing Indian Contract Act Section 23 & 27...
                                        </div>
                                    )}
                                </div>
                            )}

                            {demoState === 'conflict_detected' && (
                                <div className="split-screen-results animate-fade-in fade-slide-up">
                                    <div className="severity-banner high-risk">
                                        <AlertTriangle size={18} strokeWidth={2.5} />
                                        <span><strong>High Risk:</strong> 1 Critical Termination Conflict Detected</span>
                                    </div>
                                    <div className="split-grid">
                                        <div className="split-col">
                                            <h5>Party A (Base Contract)</h5>
                                            <div className="clause-box clause-match tooltip-trigger stagger-enter-1">
                                                "Section 2: Remote Work is permitted across all national zones."
                                                <span className="tooltip-content severity-low">Aligned with Addendum B.</span>
                                            </div>
                                            <div className="clause-box clause-conflict tooltip-trigger stagger-enter-2">
                                                "Section 4: The employer may terminate this agreement with <strong>30 days</strong> written notice."
                                                <span className="tooltip-content severity-high">Contradicts Addendum B (Minimum 90 days).</span>
                                            </div>
                                        </div>
                                        <div className="split-col">
                                            <h5>Party B (Addendum B)</h5>
                                            <div className="clause-box clause-match tooltip-trigger stagger-enter-1">
                                                "Clause 1: Remote Work authorized."
                                                <span className="tooltip-content severity-low">Matches base contract.</span>
                                            </div>
                                            <div className="clause-box clause-conflict tooltip-trigger stagger-enter-3">
                                                "Clause 3: Notwithstanding any prior agreements, minimum termination notice is <strong>90 days</strong>."
                                                <span className="tooltip-content severity-high">Overrides Base Contract. Creates execution risk.</span>
                                            </div>
                                        </div>
                                    </div>
                                    <details className="citation-accordion stagger-enter-4" open>
                                        <summary>Relevant Statutory Precedents (2)</summary>
                                        <div className="citation-details">
                                            <p><strong>1. Central Inland Water Transport Corp v. Ganguly (1986):</strong> Analyzes unconscionable contracts under Section 23 of the Indian Contract Act. <a href="#" onClick={(e) => { e.preventDefault(); openModal("Case Preview: Unconscionable Contracts", "case", mockCaseData); }}>Preview Case</a></p>
                                            <p style={{ marginTop: '0.75rem' }}><strong>2. Indian Contract Act, 1872 (Section 62):</strong> Effect of novation, rescission, and alteration of contract. <a href="#" onClick={(e) => { e.preventDefault(); openModal("Statute: Indian Contract Act Sec. 62", "statute", mockStatuteData); }}>View Statute</a></p>
                                        </div>
                                    </details>
                                    <div style={{ display: 'flex', gap: '1rem' }}>
                                        <button
                                            className="primary-btn stagger-enter-4"
                                            onClick={() => openModal("Draft Output: Software Service Level Agreement (SLA)", "draft", mockDraftData)}
                                            style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem' }}
                                        >
                                            <FileText size={18} /> Preview Generated Draft
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Modal */}
            <Modal isOpen={modalConfig.isOpen} onClose={closeModal} title={modalConfig.title}>
                {modalConfig.data ? (
                    <div className="dynamic-modal-content">
                        {modalConfig.type === 'draft' && (
                            <div className="draft-preview-render pt-2 pb-4">
                                <h4 style={{ color: '#63120e', marginBottom: '1rem', borderBottom: '2px solid #c98659', paddingBottom: '0.5rem', fontFamily: 'var(--font-heading)' }}>{modalConfig.data.title}</h4>
                                <div style={{ whiteSpace: 'pre-wrap', lineHeight: '1.8', color: '#8c3a2a', fontSize: '0.95rem', fontFamily: 'Times New Roman, serif', background: '#f6e2c6', padding: '1.5rem', borderRadius: '8px', border: '1px solid #c98659' }}>
                                    {modalConfig.data.content}
                                </div>
                            </div>
                        )}
                        {modalConfig.type === 'statute' && (
                            <div className="statute-render pt-2 pb-4">
                                <h4 style={{ color: '#8c3a2a', fontSize: '1.2rem', marginBottom: '1rem', fontFamily: 'var(--font-heading)' }}>{modalConfig.data.title}</h4>
                                <div style={{ background: '#f1d1a6', borderLeft: '4px solid #dfa46f', padding: '1rem', borderRadius: '0 8px 8px 0', marginBottom: '1.5rem' }}>
                                    <p style={{ color: '#63120e', lineHeight: '1.6', fontWeight: '500' }}>{modalConfig.data.explanation}</p>
                                </div>
                                <h5 style={{ color: '#8c3a2a', fontSize: '1rem', marginBottom: '0.75rem', fontWeight: 'bold' }}>Key Binding Points</h5>
                                <ul style={{ listStyleType: 'disc', color: '#8c3a2a', paddingLeft: '1.5rem', lineHeight: '1.7', fontSize: '0.95rem' }}>
                                    {modalConfig.data.keyPoints.map((point, i) => (
                                        <li key={i}>{point}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        {modalConfig.type === 'case' && (
                            <div className="case-render pt-2 pb-4">
                                <h4 style={{ color: '#63120e', fontSize: '1.15rem', marginBottom: '0.25rem', fontFamily: 'var(--font-heading)' }}>{modalConfig.data.title}</h4>
                                <span style={{ display: 'inline-block', background: '#f1d1a6', color: '#8c3a2a', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold', marginBottom: '1.5rem' }}>Citation: {modalConfig.data.citation}</span>
                                <h5 style={{ color: '#8c3a2a', fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Judgment Summary</h5>
                                <p style={{ color: '#8c3a2a', lineHeight: '1.7', marginBottom: '1.5rem', fontSize: '0.95rem' }}>{modalConfig.data.summary}</p>
                                <h5 style={{ color: '#8c3a2a', fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Precedent Impact</h5>
                                <p style={{ color: '#63120e', background: '#f6e2c6', padding: '1rem', borderRadius: '8px', borderLeft: '3px solid #c98659', fontSize: '0.95rem' }}>{modalConfig.data.impact}</p>
                            </div>
                        )}
                    </div>
                ) : null}
            </Modal>
        </div>
    );
};

export default Home;
