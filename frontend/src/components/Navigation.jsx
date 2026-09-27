import { useState, useRef, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Scale, BookOpen, MessageSquare, Home as HomeIcon, FileSearch, Clock, User, LogOut, FileCheck, ShieldCheck, Menu, X, ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import LocalModeToggle from './LocalModeToggle';
import LanguageSwitcher from './LanguageSwitcher';
import './Navigation.css';

const Navigation = () => {
    const { t } = useTranslation();
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [isDropdownOpen, setIsDropdownOpen] = useState(false);
    const [mobileOpen, setMobileOpen] = useState(false);
    const dropdownRef = useRef(null);

    // No responsive behavior existed anywhere in this app before (confirmed
    // via mobile-viewport testing for S3: the fixed 280px sidebar just
    // crushes every page's content into a ~110px sliver on a phone). This is
    // the minimal fix -- off-canvas sidebar + hamburger toggle -- applied
    // once at the shared shell level so every page benefits, not just the
    // new Verify-a-Filing screens the UX pass specifically calls out.
    useEffect(() => { setMobileOpen(false); }, [location.pathname]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setIsDropdownOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleLogout = () => {
        setIsDropdownOpen(false);
        logout();
    };

    return (
        <>
        <button className="mobile-nav-toggle" onClick={() => setMobileOpen(v => !v)} aria-label={mobileOpen ? 'Close menu' : 'Open menu'}>
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        {mobileOpen && <div className="mobile-nav-backdrop" onClick={() => setMobileOpen(false)} />}
        <aside className={`sidebar-nav ${mobileOpen ? 'mobile-open' : ''}`}>
            <div className="sidebar-header">
                <img src="/ai-legal-bg.png" alt="LexSetu Logo" className="sidebar-logo-img" />
                <div className="logo-text">
                    <h2>LexSetu</h2>
                    <span className="badge">PRO</span>
                </div>
            </div>

            <div className="sidebar-scrollable">
                <div className="sidebar-section">
                    <p className="section-title">{t('nav.workspace')}</p>
                    <div className="nav-links">
                        <NavLink to="/" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <HomeIcon size={18} /> {t('nav.dashboard')}
                        </NavLink>
                        <NavLink to="/verify-filing" className={({ isActive }) => isActive ? "nav-link active nav-link-flagship" : "nav-link nav-link-flagship"}>
                            <ShieldCheck size={18} /> {t('nav.verifyFiling')}
                        </NavLink>
                        <NavLink to="/case-finder" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <Scale size={18} /> {t('nav.caseFinder')}
                        </NavLink>
                        <NavLink to="/draft-assistant" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <BookOpen size={18} /> {t('nav.draftAssistant')}
                        </NavLink>
                        <NavLink to="/draft-review" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <FileCheck size={18} /> {t('nav.draftReview')}
                        </NavLink>
                        <NavLink to="/clause-conflict" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <FileSearch size={18} /> {t('nav.contractAnalysis')}
                        </NavLink>
                        <NavLink to="/statutes" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <Scale size={18} /> {t('nav.bareActsStatutes')}
                        </NavLink>
                        <NavLink to="/legal-aid" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                            <MessageSquare size={18} /> {t('nav.aiLegalAid')}
                        </NavLink>
                        {(user?.role === 'admin' || user?.role === 'advocate') && (
                            <NavLink to="/admin/corrections" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                                <ShieldAlert size={18} /> {t('nav.correctionMemory')}
                            </NavLink>
                        )}
                    </div>
                </div>

                <div className="sidebar-section">
                    <p className="section-title">{t('nav.recentActivity')}</p>
                    <div className="recent-list">
                        <div className="recent-item"><Clock size={14} /> {t('nav.caseFinder', 'Case Search')}</div>
                        <div className="recent-item"><Clock size={14} /> {t('nav.draftAssistant', 'Draft Assistant')}</div>
                        <div className="recent-item"><Clock size={14} /> {t('nav.aiLegalAid', 'Legal Aid Q&A')}</div>
                    </div>
                </div>

                <div className="sidebar-section">
                    <LocalModeToggle />
                    <LanguageSwitcher />
                </div>
            </div>

            <div className="sidebar-footer">
                {user ? (
                    <div className="authenticated-user-container" ref={dropdownRef}>
                        <div className="dynamic-user-profile" onClick={() => setIsDropdownOpen(!isDropdownOpen)}>
                            <div className="avatar">
                                {user.name ? user.name.charAt(0).toUpperCase() : 'U'}
                            </div>
                            <div className="user-info">
                                <strong>{user.name || 'User'}</strong>
                                <span>{user.plan || 'Member'}</span>
                            </div>
                        </div>

                        {isDropdownOpen && (
                            <div className="profile-dropdown animate-fade-up">
                                <div className="dropdown-user-header">
                                    <strong>{user.name}</strong>
                                    <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>{user.email}</span>
                                </div>
                                <div className="dropdown-divider"></div>
                                <button className="dropdown-action text-red-600" onClick={handleLogout}>
                                    <LogOut size={16} /> {t('nav.logout')}
                                </button>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="unauthenticated-container">
                        <button className="massive-login-btn" onClick={() => navigate('/login')}>
                            <User size={18} /> {t('nav.login')}
                        </button>
                    </div>
                )}
            </div>
        </aside>
        </>
    );
};

export default Navigation;
