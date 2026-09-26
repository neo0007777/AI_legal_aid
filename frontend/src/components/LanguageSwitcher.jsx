import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Languages, Check } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import './LanguageSwitcher.css';

// App-wide language preference switcher -- same visual weight/placement as
// LocalModeToggle, always visible, not a per-page control. Changing it never
// reloads or re-fetches already-displayed content; it only affects new
// generations and offers a "Translate" action on content already on screen
// (see TranslateAction.jsx).
const LanguageSwitcher = () => {
    const { t } = useTranslation();
    const { currentLanguage, languages, setLanguage } = useLanguage();
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        const onClickOutside = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', onClickOutside);
        return () => document.removeEventListener('mousedown', onClickOutside);
    }, []);

    return (
        <div className="language-switcher" ref={ref}>
            <button
                type="button"
                className="language-switcher-trigger"
                onClick={() => setOpen(v => !v)}
                title={t('language.switcherTitle')}
            >
                <Languages size={14} />
                <span>{currentLanguage.nativeLabel}</span>
            </button>

            {open && (
                <div className="language-switcher-menu" role="listbox" aria-label={t('language.switcherLabel')}>
                    {languages.map((lang) => (
                        <button
                            key={lang.code}
                            type="button"
                            role="option"
                            aria-selected={lang.code === currentLanguage.code}
                            className={`language-option ${lang.code === currentLanguage.code ? 'active' : ''}`}
                            onClick={() => { setLanguage(lang.code); setOpen(false); }}
                        >
                            <span className="language-option-native">{lang.nativeLabel}</span>
                            <span className="language-option-label">{lang.label}</span>
                            {lang.code === currentLanguage.code && <Check size={13} className="language-option-check" />}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

export default LanguageSwitcher;
