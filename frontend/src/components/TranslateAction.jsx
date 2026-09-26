import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Languages, Loader2, AlertTriangle, Undo2, RefreshCw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import './TranslateAction.css';

// Shared "Translate to {language}" surface embedded in every feature's result
// view (Legal Aid, Draft Assistant, Draft Review, Contract Analysis, ...).
// One component, one backend call (POST /translate) -- no per-feature
// translation function, per the app-wide language switcher design.
//
// Auto-translates as soon as a non-English language is selected and English
// result text is present -- the whole point of the app-wide switcher is that
// the user shouldn't have to click a button per answer to read it in their
// language. It re-triggers whenever EITHER the language changes OR the
// underlying English text changes (e.g. a new draft was generated while
// Hindi was already selected) -- tracked together so a stale translation
// from a previous answer never lingers on screen.
//
// Correctness contract this component depends on and must never violate:
// translation is a RENDERING step over already-verified English text. It
// never re-triggers generation/verification -- `text`/`citations` are always
// the already-displayed English result, passed in as-is. The disclaimer is
// mandatory and not dismissible; the original English stays one click away.
const TranslateAction = ({ sourceType, text, citations = [] }) => {
    const { t } = useTranslation();
    const { getAuthHeaders } = useAuth();
    const { languageCode } = useLanguage();

    const [translation, setTranslation] = useState(null); // { translated_text, disclaimer, target_lang }
    const [translatedKey, setTranslatedKey] = useState(null); // `${languageCode}::${text}` this translation is for
    const [isTranslating, setIsTranslating] = useState(false);
    const [error, setError] = useState('');
    const [showingOriginal, setShowingOriginal] = useState(false);

    const inFlightKey = useRef(null);

    const currentKey = `${languageCode}::${text || ''}`;
    const isCurrent = translatedKey === currentKey;
    const shouldTranslate = languageCode !== 'en' && !!text && !isCurrent;

    useEffect(() => {
        if (!shouldTranslate) return;
        if (inFlightKey.current === currentKey) return; // already fetching this exact pair
        inFlightKey.current = currentKey;

        const targetLang = languageCode;
        const targetText = text;

        setIsTranslating(true);
        setError('');

        (async () => {
            try {
                const res = await fetch('/api/translate', {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({
                        source_type: sourceType,
                        target_lang: targetLang,
                        text: targetText,
                        citations,
                    }),
                });
                if (!res.ok) {
                    let msg = t('translate.error');
                    try { const e = await res.json(); msg = e.detail || msg; } catch { /* ignore */ }
                    throw new Error(msg);
                }
                const data = await res.json();
                setTranslation(data);
                setTranslatedKey(`${targetLang}::${targetText}`);
                setShowingOriginal(false);
            } catch (err) {
                setError(err.message || t('translate.error'));
            } finally {
                setIsTranslating(false);
                inFlightKey.current = null;
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [shouldTranslate, currentKey]);

    // Nothing to translate into, or nothing to translate yet.
    if (languageCode === 'en' || !text) return null;

    const retry = () => {
        setError('');
        inFlightKey.current = null;
        // Force the effect to re-run by nudging translatedKey away from currentKey
        setTranslatedKey(null);
    };

    return (
        <div className="translate-action-block">
            {isTranslating && (
                <div className="translate-loading-note">
                    <Loader2 size={14} className="spin" /> {t('translate.translating')}
                </div>
            )}

            {!isTranslating && isCurrent && translation && (
                <div className="translate-result-card">
                    <div className="translate-disclaimer">
                        <AlertTriangle size={13} />
                        <span>{translation.disclaimer || t('translate.disclaimer')}</span>
                    </div>

                    <div className="translate-toggle-row">
                        <button
                            type="button"
                            className={`translate-toggle-btn ${!showingOriginal ? 'active' : ''}`}
                            onClick={() => setShowingOriginal(false)}
                        >
                            <Languages size={12} /> {t('translate.viewTranslated')}
                        </button>
                        <button
                            type="button"
                            className={`translate-toggle-btn ${showingOriginal ? 'active' : ''}`}
                            onClick={() => setShowingOriginal(true)}
                        >
                            <Undo2 size={12} /> {t('translate.viewOriginal')}
                        </button>
                    </div>

                    <div className="translate-text-body">
                        {showingOriginal ? text : translation.translated_text}
                    </div>
                </div>
            )}

            {!isTranslating && error && (
                <div className="translate-error-note">
                    <AlertTriangle size={13} /> {error}
                    <button type="button" className="translate-retry-btn" onClick={retry}>
                        <RefreshCw size={12} /> Retry
                    </button>
                </div>
            )}
        </div>
    );
};

export default TranslateAction;
