import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
    BookOpen, Search, ShieldCheck, ExternalLink, Hash, Clock,
    AlertCircle, CheckCircle, RefreshCw, ChevronRight, Scale,
    FileText, ArrowRight, Layers, Database, Globe2
} from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import './Statutes.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const Statutes = () => {
    const { t } = useTranslation();
    const { languageCode } = useLanguage();
    // States for Acts
    const [acts, setActs] = useState([]);
    const [selectedAct, setSelectedAct] = useState(null);
    const [actDetail, setActDetail] = useState(null);
    const [loadingActs, setLoadingActs] = useState(true);
    const [loadingActDetail, setLoadingActDetail] = useState(false);
    
    // States for Provisions
    const [sectionFilter, setSectionFilter] = useState('');
    const [selectedProvisionNumber, setSelectedProvisionNumber] = useState(null);
    const [provisionDetail, setProvisionDetail] = useState(null);
    const [loadingProvision, setLoadingProvision] = useState(false);
    const [provisionError, setProvisionError] = useState(null);

    // States for Corpus Meta
    const [corpusMeta, setCorpusMeta] = useState(null);
    const [metaError, setMetaError] = useState(null);

    // Fetch Corpus Metadata on Mount
    useEffect(() => {
        fetchCorpusMeta();
        fetchActs();
    }, []);

    const fetchCorpusMeta = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/statutes/meta`);
            if (res.ok) {
                const data = await res.json();
                setCorpusMeta(data);
            } else {
                setMetaError("Unable to retrieve source data.");
            }
        } catch (err) {
            console.error("Meta fetch failed:", err);
            setMetaError("Unable to retrieve source data.");
        }
    };

    const fetchActs = async () => {
        setLoadingActs(true);
        try {
            const res = await fetch(`${API_BASE_URL}/statutes/acts?limit=20`);
            if (res.ok) {
                const data = await res.json();
                const fetchedActs = data.acts || [];
                setActs(fetchedActs);
                if (fetchedActs.length > 0 && !selectedAct) {
                    selectAct(fetchedActs[0]);
                }
            } else {
                console.error("Failed to fetch acts: HTTP", res.status);
            }
        } catch (err) {
            console.error("Acts fetch error:", err);
        } finally {
            setLoadingActs(false);
        }
    };

    const selectAct = async (act) => {
        setSelectedAct(act);
        setSelectedProvisionNumber(null);
        setProvisionDetail(null);
        setProvisionError(null);
        setLoadingActDetail(true);

        try {
            const res = await fetch(`${API_BASE_URL}/statutes/acts/${act.source_act_id}`);
            if (res.ok) {
                const data = await res.json();
                setActDetail(data);
                // Auto-select first provision
                if (data.provisions && data.provisions.length > 0) {
                    fetchProvision(act.source_act_id, data.provisions[0].provision_number);
                }
            } else {
                setActDetail(null);
            }
        } catch (err) {
            console.error("Act detail error:", err);
            setActDetail(null);
        } finally {
            setLoadingActDetail(false);
        }
    };

    const fetchProvision = async (actSourceId, provisionNumber) => {
        setSelectedProvisionNumber(provisionNumber);
        setLoadingProvision(true);
        setProvisionError(null);

        try {
            const res = await fetch(`${API_BASE_URL}/statutes/acts/${actSourceId}/provisions/${encodeURIComponent(provisionNumber)}`);
            if (res.ok) {
                const data = await res.json();
                setProvisionDetail(data);
            } else if (res.status === 404) {
                setProvisionDetail(null);
                setProvisionError("Not available from source.");
            } else {
                setProvisionDetail(null);
                setProvisionError("Unable to retrieve source data.");
            }
        } catch (err) {
            console.error("Provision fetch error:", err);
            setProvisionDetail(null);
            setProvisionError("Unable to retrieve source data.");
        } finally {
            setLoadingProvision(false);
        }
    };

    // Filter provisions list by search input
    const filteredProvisions = (actDetail?.provisions || []).filter(p => {
        if (!sectionFilter.trim()) return true;
        const q = sectionFilter.toLowerCase().trim();
        const numMatch = String(p.provision_number).toLowerCase().includes(q);
        const headingMatch = (p.heading || '').toLowerCase().includes(q);
        return numMatch || headingMatch;
    });

    return (
        <div className="statutes-explorer-page">
            {/* Top Navigation & Provenance Banner */}
            <header className="statutes-header">
                <div className="statutes-title-area">
                    <div className="title-with-badge">
                        <Scale className="header-icon" size={28} />
                        <h1>{t('statutes.title')}</h1>
                        <span className="source-truth-badge">
                            <ShieldCheck size={14} /> {t('statutes.sourceOfTruth')}
                        </span>
                    </div>
                    <p className="statutes-subtitle">
                        Verbatim statutory provisions and official transitions from India Code API (eCourtsIndia).
                        Zero LLM intervention in text layer.
                    </p>
                </div>

                <div className="corpus-meta-card">
                    <div className="meta-item">
                        <span className="meta-label">SOURCE API</span>
                        <span className="meta-value">{corpusMeta?.source_api || "indiacode.ecourtsindia.com"}</span>
                    </div>
                    <div className="meta-divider" />
                    <div className="meta-item">
                        <span className="meta-label">AUTHORITY</span>
                        <span className="meta-value">{corpusMeta?.source_authority || "INDIA_CODE_CORPUS"}</span>
                    </div>
                    <div className="meta-divider" />
                    <div className="meta-item">
                        <span className="meta-label">ACTS STORED</span>
                        <span className="meta-value highlight">{corpusMeta?.local_storage?.acts_stored ?? acts.length}</span>
                    </div>
                    <div className="meta-divider" />
                    <div className="meta-item">
                        <span className="meta-label">PROVISIONS</span>
                        <span className="meta-value highlight">{corpusMeta?.local_storage?.provisions_indexed ?? 2298}</span>
                    </div>
                </div>
            </header>

            {/* Act Selection Grid */}
            <section className="acts-strip-section">
                <div className="strip-title">
                    <Layers size={16} />
                    <span>{t('statutes.selectStatute')}</span>
                </div>
                <div className="acts-strip">
                    {loadingActs ? (
                        <div className="strip-loading">{t('statutes.loadingActs')}</div>
                    ) : (
                        acts.map((act) => {
                            const isSelected = selectedAct?.source_act_id === act.source_act_id;
                            return (
                                <button
                                    key={act.source_act_id}
                                    className={`act-tab-pill ${isSelected ? 'active' : ''}`}
                                    onClick={() => selectAct(act)}
                                >
                                    <div className="pill-top">
                                        <span className="pill-id">{act.source_act_id.toUpperCase()}</span>
                                        {act.in_force && <span className="pill-status">{t('statutes.inForce')}</span>}
                                    </div>
                                    <div className="pill-title">{act.title}</div>
                                    <div className="pill-footer">
                                        <span>{act.year ? `Year: ${act.year}` : 'Not available'}</span>
                                        <span>{act.section_count ? `${act.section_count} Secs` : ''}</span>
                                    </div>
                                </button>
                            );
                        })
                    )}
                </div>
            </section>

            {/* Main Content Workspace: Provisions List + Exact Provision Reader */}
            <div className="statutes-workspace">
                {/* Left Panel: Table of Provisions */}
                <aside className="provisions-sidebar">
                    <div className="sidebar-search-box">
                        <Search size={16} className="search-icon" />
                        <input
                            type="text"
                            placeholder="Filter by section or title (e.g. 103, 124A)..."
                            value={sectionFilter}
                            onChange={(e) => setSectionFilter(e.target.value)}
                        />
                        {sectionFilter && (
                            <button className="clear-btn" onClick={() => setSectionFilter('')}>✕</button>
                        )}
                    </div>

                    <div className="provisions-list-header">
                        <span>{t('statutes.tableOfProvisions')}</span>
                        <span className="count-badge">{filteredProvisions.length} of {actDetail?.provisions_count || 0}</span>
                    </div>

                    <div className="provisions-scroll-container">
                        {loadingActDetail ? (
                            <div className="loading-state">Loading table of provisions...</div>
                        ) : filteredProvisions.length === 0 ? (
                            <div className="empty-state">No matching provisions found.</div>
                        ) : (
                            filteredProvisions.map((p) => {
                                const isSelected = selectedProvisionNumber === p.provision_number;
                                return (
                                    <div
                                        key={p.provision_number}
                                        className={`provision-row-item ${isSelected ? 'selected' : ''}`}
                                        onClick={() => fetchProvision(selectedAct.source_act_id, p.provision_number)}
                                    >
                                        <div className="provision-row-left">
                                            <span className="sec-number-badge">Sec {p.provision_number}</span>
                                            <span className="sec-heading-text">{p.heading || "Not available from source"}</span>
                                        </div>
                                        <ChevronRight size={14} className="row-chevron" />
                                    </div>
                                );
                            })
                        )}
                    </div>
                </aside>

                {/* Right Panel: Exact Provision Reader */}
                <main className="provision-reader-panel">
                    {loadingProvision ? (
                        <div className="reader-loading-state">
                            <RefreshCw size={24} className="spin-icon" />
                            <span>Retrieving exact statutory text from source...</span>
                        </div>
                    ) : provisionError ? (
                        <div className="reader-error-state">
                            <AlertCircle size={28} className="error-icon" />
                            <h3>{provisionError}</h3>
                            <p>No fabricated or estimated statutory text is displayed.</p>
                        </div>
                    ) : provisionDetail ? (
                        <div className="provision-full-view">
                            {/* Act & Section Banner */}
                            <div className="reader-act-breadcrumb">
                                <span className="breadcrumb-act">{provisionDetail.act_title}</span>
                                <span className="breadcrumb-divider">/</span>
                                <span className="breadcrumb-sec">
                                    {provisionDetail.provision_type ? provisionDetail.provision_type.toUpperCase() : 'SECTION'} {provisionDetail.provision_number}
                                </span>
                            </div>

                            <h2 className="provision-main-heading">
                                {provisionDetail.heading || "Not available from source"}
                            </h2>

                            {/* Verbatim Legal Text Box */}
                            <div className="verbatim-text-card">
                                <div className="card-top-tag">
                                    <FileText size={14} />
                                    <span>{t('statutes.verbatimSourceText')}</span>
                                    <span className="unaltered-pill">{t('statutes.unalteredText')}</span>
                                </div>
                                {languageCode !== 'en' && (
                                    <div className="legal-applicability-disclaimer" style={{ marginBottom: '0.6rem' }}>
                                        <Globe2 size={14} />
                                        <span>{t('statutes.englishOnlyNotice')}</span>
                                    </div>
                                )}
                                <div className="statutory-text-content">
                                    {provisionDetail.verbatim_text ? (
                                        <p>{provisionDetail.verbatim_text}</p>
                                    ) : (
                                        <p className="text-muted">{t('statutes.notAvailable')}</p>
                                    )}
                                </div>
                            </div>

                            {/* Source-listed Correspondences / Mappings */}
                            <div className="mappings-section">
                                <div className="mappings-header">
                                    <div className="header-left">
                                        <ArrowRight size={16} />
                                        <h4>Source-listed Correspondence</h4>
                                        <span className="neutral-tag">API Mapping</span>
                                    </div>
                                </div>

                                <div className="legal-applicability-disclaimer">
                                    <AlertCircle size={14} />
                                    <span>
                                        <strong>Source correspondence only:</strong> Legal applicability depends on the alleged commission date, transitional savings clauses, and procedural posture.
                                    </span>
                                </div>

                                {provisionDetail.source_correspondences && provisionDetail.source_correspondences.length > 0 ? (
                                    <div className="correspondences-grid">
                                        {provisionDetail.source_correspondences.map((corr, idx) => (
                                            <div key={idx} className="correspondence-card">
                                                <div className="corr-top">
                                                    <span className="corr-direction">{corr.direction.toUpperCase()}</span>
                                                    <span className={`corr-relation-badge relation-${corr.relation}`}>
                                                        {corr.relation}
                                                    </span>
                                                </div>
                                                <div className="corr-target">
                                                    <strong>{corr.target_act.toUpperCase()} Section {corr.target_provision}</strong>
                                                    {corr.target_heading && <span className="corr-target-heading">{corr.target_heading}</span>}
                                                </div>
                                                <div className="corr-footer">
                                                    {corr.score && <span className="corr-score">Match Score: {corr.score}</span>}
                                                    {corr.target_url && (
                                                        <a href={corr.target_url} target="_blank" rel="noopener noreferrer" className="corr-link">
                                                            Source View <ExternalLink size={12} />
                                                        </a>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="no-mapping-state">
                                        <span>No mapping available from source.</span>
                                    </div>
                                )}
                            </div>

                            {/* Full Provenance & Hash Audit Card */}
                            <footer className="provenance-audit-box">
                                <div className="audit-header">
                                    <Database size={15} />
                                    <span>{t('statutes.provenanceAudit')}</span>
                                </div>
                                <div className="audit-grid">
                                    <div className="audit-cell">
                                        <span className="cell-label">SOURCE API</span>
                                        <span className="cell-val">{provisionDetail.provenance?.source_api || "indiacode.ecourtsindia.com"}</span>
                                    </div>
                                    <div className="audit-cell">
                                        <span className="cell-label">SOURCE AUTHORITY</span>
                                        <span className="cell-val">{provisionDetail.provenance?.source_authority || "INDIA_CODE_CORPUS"}</span>
                                    </div>
                                    <div className="audit-cell">
                                        <span className="cell-label">CANONICAL SOURCE URL</span>
                                        {provisionDetail.provenance?.canonical_legal_source ? (
                                            <a
                                                href={provisionDetail.provenance.canonical_legal_source}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="canonical-link"
                                            >
                                                {provisionDetail.provenance.canonical_legal_source} <ExternalLink size={12} />
                                            </a>
                                        ) : (
                                            <span className="cell-val text-muted">Not available from source</span>
                                        )}
                                    </div>
                                    <div className="audit-cell">
                                        <span className="cell-label">RETRIEVED TIMESTAMP</span>
                                        <span className="cell-val">
                                            {provisionDetail.provenance?.retrieved_at 
                                                ? new Date(provisionDetail.provenance.retrieved_at).toLocaleString() 
                                                : "Not available"}
                                        </span>
                                    </div>
                                    <div className="audit-cell">
                                        <span className="cell-label">CONTENT SHA-256 (VERBATIM TEXT)</span>
                                        <code className="cell-hash">{provisionDetail.provenance?.content_sha256 || "N/A"}</code>
                                    </div>
                                    <div className="audit-cell">
                                        <span className="cell-label">RAW RESPONSE SHA-256 (API PAYLOAD)</span>
                                        <code className="cell-hash">{provisionDetail.provenance?.raw_response_sha256 || "N/A"}</code>
                                    </div>
                                </div>
                            </footer>
                        </div>
                    ) : (
                        <div className="reader-empty-selection">
                            <BookOpen size={48} className="empty-book-icon" />
                            <h3>Select a provision to inspect exact statutory text</h3>
                            <p>All provisions are fetched directly from the India Code API without modification.</p>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
};

export default Statutes;
