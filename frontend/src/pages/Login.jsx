import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Shield, Lock, Mail, ArrowRight, AlertCircle, User, Sparkles,
    ShieldCheck, Eye, EyeOff, KeyRound, CheckCircle2, Scale, FileCheck, Database
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { formatErrorMessage } from '../utils/formatError';
import './Login.css';

const Login = () => {
    const [tab, setTab] = useState('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [fullName, setFullName] = useState('');
    const [role, setRole] = useState('advocate');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const { login, register, isAuthenticated } = useAuth();
    const navigate = useNavigate();

    // If already logged in, redirect to workspace
    useEffect(() => {
        if (isAuthenticated) {
            navigate('/', { replace: true });
        }
    }, [isAuthenticated, navigate]);

    const handleSubmit = async (e) => {
        if (e) e.preventDefault();
        setError('');
        setIsLoading(true);

        let result;
        if (tab === 'login') {
            result = await login(email.trim(), password);
        } else {
            if (!fullName.trim()) {
                setError('Full name is required.');
                setIsLoading(false);
                return;
            }
            result = await register(fullName.trim(), email.trim(), password, role);
        }

        if (!result.success) {
            setError(formatErrorMessage(result.message, 'Authentication failed. Please verify your credentials.'));
            setIsLoading(false);
        }
    };

    const handleDemoLogin = async () => {
        setError('');
        setIsLoading(true);
        setEmail('test@lexsetu.com');
        setPassword('password123');
        const result = await login('test@lexsetu.com', 'password123');
        if (!result.success) {
            setError(formatErrorMessage(result.message, 'Demo sign-in failed. Please check backend connection.'));
            setIsLoading(false);
        }
    };

    return (
        <div className="login-matrix">
            {/* Left Sovereign Security Showcase Panel */}
            <div className="login-graphic-panel">
                <div className="security-ambient-orb orb-1" aria-hidden="true" />
                <div className="security-ambient-orb orb-2" aria-hidden="true" />

                <div className="panel-inner-container">
                    {/* Brand Header */}
                    <div className="brand-header-cluster">
                        <div className="brand-emblem-wrap">
                            <img src="/ai-legal-bg.png" alt="LexSetu Seal" className="login-logo-img" />
                            <span className="live-shield-dot" title="Cryptographic Shield Active" />
                        </div>
                        <div className="brand-text-block">
                            <div className="brand-title-row">
                                <h1>LexSetu</h1>
                                <span className="security-badge-pill">
                                    <ShieldCheck size={12} /> SOVEREIGN VAULT
                                </span>
                            </div>
                            <p className="brand-tagline">Enterprise Legal Intelligence & Judicial Drafting Infrastructure</p>
                        </div>
                    </div>

                    {/* High-Impact Trust Hero Banner */}
                    <div className="trust-hero-card">
                        <div className="trust-hero-header">
                            <div className="trust-hero-icon-ring">
                                <ShieldCheck size={28} className="trust-shield-icon" />
                            </div>
                            <div className="trust-hero-copy">
                                <h3>Statutory Privacy & Data Sovereignty Guarantee</h3>
                                <p>Built specifically for Advocates, Law Chambers, and Legal Counsel handling sensitive case matters and privileged client records.</p>
                            </div>
                        </div>

                        <div className="trust-status-strip">
                            <div className="trust-status-item">
                                <span className="pulse-indicator" />
                                <span>256-Bit Hardware Encryption Active</span>
                            </div>
                            <span className="trust-dot-sep">•</span>
                            <div className="trust-status-item">
                                <CheckCircle2 size={14} className="green-check" />
                                <span>Zero Model Training on Your Data</span>
                            </div>
                        </div>
                    </div>

                    {/* 4 Core Security & Privilege Pillars */}
                    <div className="security-pillars-grid">
                        <div className="security-pillar-card">
                            <div className="pillar-icon-box">
                                <Scale size={18} />
                            </div>
                            <div className="pillar-content">
                                <h4>Statutory Advocate-Client Privilege</h4>
                                <p>Protected under Section 126 Evidence Act & Section 132 Bharatiya Sakshya Adhiniyam. Your filings and drafts are legally privileged.</p>
                            </div>
                        </div>

                        <div className="security-pillar-card">
                            <div className="pillar-icon-box">
                                <Lock size={18} />
                            </div>
                            <div className="pillar-content">
                                <h4>End-to-End AES-256 Vault</h4>
                                <p>All documents, inquiries, and case records are encrypted in transit via TLS 1.3 and stored in isolated encrypted enclaves.</p>
                            </div>
                        </div>

                        <div className="security-pillar-card">
                            <div className="pillar-icon-box">
                                <FileCheck size={18} />
                            </div>
                            <div className="pillar-content">
                                <h4>Zero AI Training Retention</h4>
                                <p>Private client names, factual pleadings, and drafts are never retained or fed into public LLM training datasets.</p>
                            </div>
                        </div>

                        <div className="security-pillar-card">
                            <div className="pillar-icon-box">
                                <KeyRound size={18} />
                            </div>
                            <div className="pillar-content">
                                <h4>Argon2id & Cryptographic Revocation</h4>
                                <p>Brute-force lockout protection, timing-attack proof hash validation, and real-time session revocation.</p>
                            </div>
                        </div>
                    </div>

                    {/* Bottom Security Standards Strip */}
                    <div className="security-compliance-footer">
                        <div className="compliance-badge">
                            <Lock size={12} />
                            <span>AES-256-GCM Vault</span>
                        </div>
                        <div className="compliance-badge">
                            <Shield size={12} />
                            <span>BSA § 132 Privileged</span>
                        </div>
                        <div className="compliance-badge">
                            <Database size={12} />
                            <span>India Data Sovereignty</span>
                        </div>
                        <div className="compliance-badge">
                            <Sparkles size={12} />
                            <span>Airgapped Inference</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Interactive Form Panel */}
            <div className="login-interactive-panel">
                <div className="login-card">
                    <div className="login-tabs">
                        <button
                            type="button"
                            className={`login-tab ${tab === 'login' ? 'active' : ''}`}
                            onClick={() => { setTab('login'); setError(''); }}
                        >
                            Sign In
                        </button>
                        <button
                            type="button"
                            className={`login-tab ${tab === 'register' ? 'active' : ''}`}
                            onClick={() => { setTab('register'); setError(''); }}
                        >
                            Register
                        </button>
                    </div>

                    <div className="login-card-header">
                        <h2>{tab === 'login' ? 'Welcome back' : 'Create Account'}</h2>
                        <p className="login-subtitle">
                            {tab === 'login'
                                ? 'Enter your credentials to access your secure legal workspace.'
                                : 'Join LexSetu to unlock protected AI legal intelligence.'}
                        </p>
                    </div>

                    {error && (
                        <div className="login-error-flag animate-fade-in" role="alert">
                            <AlertCircle size={18} style={{ flexShrink: 0 }} />
                            <span>{formatErrorMessage(error)}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="login-form">
                        {tab === 'register' && (
                            <div className="input-group">
                                <label>Full Name</label>
                                <div className="input-wrapper">
                                    <User size={18} className="input-icon" />
                                    <input
                                        type="text"
                                        placeholder="e.g. Advocate Sharma"
                                        value={fullName}
                                        onChange={(e) => setFullName(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>
                        )}

                        <div className="input-group">
                            <label>Email Address</label>
                            <div className="input-wrapper">
                                <Mail size={18} className="input-icon" />
                                <input
                                    type="email"
                                    placeholder="advocate@example.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <div className="input-group">
                            <div className="label-row">
                                <label>Password</label>
                            </div>
                            <div className="input-wrapper">
                                <Lock size={18} className="input-icon" />
                                <input
                                    type={showPassword ? 'text' : 'password'}
                                    placeholder="••••••••"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                />
                                <button
                                    type="button"
                                    className="password-toggle-btn"
                                    onClick={() => setShowPassword(!showPassword)}
                                    title={showPassword ? "Hide password" : "Show password"}
                                    aria-label="Toggle password visibility"
                                >
                                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        {tab === 'register' && (
                            <div className="input-group">
                                <label>Professional Role</label>
                                <div className="input-wrapper">
                                    <select
                                        value={role}
                                        onChange={(e) => setRole(e.target.value)}
                                        className="role-select"
                                    >
                                        <option value="advocate">Advocate / Legal Counsel</option>
                                        <option value="intern">Legal Intern / Researcher</option>
                                        <option value="user">General User / Litigant</option>
                                    </select>
                                </div>
                            </div>
                        )}

                        <button
                            type="submit"
                            className={`login-submit-btn ${isLoading ? 'loading' : ''}`}
                            disabled={isLoading}
                        >
                            {isLoading ? (
                                <><Sparkles size={18} className="spin-loader" /> Authenticating...</>
                            ) : (
                                <>{tab === 'login' ? 'Sign in to Secure Workspace' : 'Create Protected Account'} <ArrowRight size={18} /></>
                            )}
                        </button>
                    </form>

                    {/* Security & Data Safety Note under form */}
                    <div className="form-security-guarantee">
                        <ShieldCheck size={14} className="guarantee-icon" />
                        <span>Protected by 256-bit TLS encryption • Data stored in India</span>
                    </div>

                    {tab === 'login' && (
                        <div className="demo-sign-in-section">
                            <div className="demo-divider">
                                <span>or continue with test credentials</span>
                            </div>
                            <button
                                type="button"
                                onClick={handleDemoLogin}
                                disabled={isLoading}
                                className="demo-sign-in-btn"
                            >
                                <Sparkles size={15} />
                                <span>Quick Demo Sign-in <strong>(Advocate Persona)</strong></span>
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Login;
