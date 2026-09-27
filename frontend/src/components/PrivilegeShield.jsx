import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldCheck, Lock, Cpu, Trash2, ChevronDown, ChevronUp, AlertCircle, HardDrive, CheckCircle2 } from 'lucide-react';
import { useLocalMode } from '../context/LocalModeContext';
import './PrivilegeShield.css';

const PrivilegeShield = ({ className = '', compact = false }) => {
    const { t } = useTranslation();
    const [expanded, setExpanded] = useState(false);
    const { localOnly } = useLocalMode();

    if (compact) {
        return (
            <div className={`privilege-shield-compact ${className}`}>
                <span className="privilege-compact-pill" onClick={() => setExpanded(v => !v)}>
                    <ShieldCheck size={13} className="shield-icon-active" />
                    <span>{t('privilege.active', 'Privilege Shield Active')}</span>
                    <span className="privilege-sub-dot" />
                    <span className="privilege-sub-mode">{localOnly ? 'Air-Gapped' : 'Zero-Retention RAM'}</span>
                </span>

                {expanded && (
                    <div className="privilege-compact-popover animate-fade-in">
                        <div className="popover-header">
                            <ShieldCheck size={16} className="shield-gold" />
                            <strong>{t('privilege.title', 'Attorney-Client Privilege Guard')}</strong>
                        </div>
                        <ul className="popover-points">
                            <li><strong>Zero AI Training:</strong> {t('privilege.zeroAi', 'Filings never train public or private LLMs.')}</li>
                            <li><strong>RAM-Only Stream:</strong> {t('privilege.ramOnly', 'No persistent disk storage of client documents.')}</li>
                            <li><strong>DPDP & BSA Aligned:</strong> {t('privilege.dpdp', 'Designed around Sec 126 IEA / Sec 132 BSA.')}</li>
                            <li><strong>Local Isolation:</strong> {localOnly ? 'Active (0 bytes leave device)' : 'Toggle sidebar to enable Air-Gapped mode.'}</li>
                        </ul>
                    </div>
                )}
            </div>
        );
    }

    return (
        <div className={`privilege-shield-card ${className}`}>
            <div className="privilege-shield-header" onClick={() => setExpanded(v => !v)} role="button" tabIndex={0}>
                <div className="shield-title-area">
                    <div className="shield-glow-icon">
                        <ShieldCheck size={18} />
                    </div>
                    <div className="shield-text">
                        <div className="shield-primary-line">
                            <span className="shield-headline">{t('privilege.title', 'Attorney-Client Privilege Guard')}</span>
                            <span className={`shield-mode-tag ${localOnly ? 'airgapped' : 'ephemeral'}`}>
                                {localOnly ? t('privilege.airgapped', 'Air-Gapped Local Mode') : t('privilege.ephemeral', 'Ephemeral Zero-Retention RAM')}
                            </span>
                        </div>
                        <span className="shield-subline">
                            {t('privilege.tagline', 'Client confidentiality preserved • Zero AI model training • Sec. 126 IEA / Sec. 132 BSA compliant')}
                        </span>
                    </div>
                </div>

                <div className="shield-action-area">
                    <button type="button" className="shield-toggle-btn" aria-label="Toggle Confidentiality Audit">
                        <span>{expanded ? t('privilege.hideAudit', 'Hide Audit') : t('privilege.audit', 'Security Audit')}</span>
                        {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </button>
                </div>
            </div>

            {expanded && (
                <div className="privilege-shield-body animate-fade-in">
                    <div className="shield-pillars-grid">
                        <div className="pillar-item">
                            <div className="pillar-icon-box">
                                <Lock size={15} />
                            </div>
                            <div className="pillar-content">
                                <h6>{t('privilege.zeroAiTitle', 'Zero LLM Training')}</h6>
                                <p>{t('privilege.zeroAiDesc', 'Client facts, names, and drafts are never used to train or fine-tune public or private AI models.')}</p>
                            </div>
                        </div>

                        <div className="pillar-item">
                            <div className="pillar-icon-box">
                                <Cpu size={15} />
                            </div>
                            <div className="pillar-content">
                                <h6>{t('privilege.volatileRamTitle', 'Volatile RAM Only')}</h6>
                                <p>{t('privilege.volatileRamDesc', 'Uploaded documents live only in server RAM during verification and are purged automatically.')}</p>
                            </div>
                        </div>

                        <div className="pillar-item">
                            <div className="pillar-icon-box">
                                <CheckCircle2 size={15} />
                            </div>
                            <div className="pillar-content">
                                <h6>{t('privilege.statutoryPrivilegeTitle', 'Statutory Privilege')}</h6>
                                <p>{t('privilege.statutoryPrivilegeDesc', 'Engineered to respect legal professional privilege under Section 126 IEA / Section 132 BSA and DPDP Act 2023.')}</p>
                            </div>
                        </div>

                        <div className="pillar-item">
                            <div className="pillar-icon-box">
                                <HardDrive size={15} />
                            </div>
                            <div className="pillar-content">
                                <h6>{t('privilege.airgappedOptionTitle', 'Air-Gapped Option')}</h6>
                                <p>{t('privilege.airgappedOptionDesc', 'Need absolute offline isolation? Flip the sidebar switch to Local-Only mode for 0 outbound network packets.')}</p>
                            </div>
                        </div>
                    </div>

                    <div className="shield-status-footer">
                        <div className="status-indicator-row">
                            <span className={`status-indicator-dot ${localOnly ? 'local-green' : 'cloud-blue'}`} />
                            <span className="status-indicator-text">
                                {localOnly
                                    ? t('privilege.activeOfflineState', 'Active Network State: 100% Offline / Air-Gapped. Zero outbound bytes.')
                                    : t('privilege.activeCloudState', 'Active Network State: End-to-End TLS Encrypted Stream. Memory ephemeral.')}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PrivilegeShield;
