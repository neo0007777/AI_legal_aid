import React from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('ErrorBoundary caught an unhandled error:', error, errorInfo);
        this.setState({ errorInfo });
    }

    handleReload = () => {
        window.location.reload();
    };

    handleGoHome = () => {
        window.location.href = '/';
    };

    render() {
        if (this.state.hasError) {
            const errorMsg = this.state.error?.message || String(this.state.error) || 'An unexpected rendering error occurred.';

            return (
                <div style={{
                    minHeight: '100vh',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#f9eedc',
                    padding: '2rem',
                    fontFamily: "'Inter', sans-serif",
                }}>
                    <div style={{
                        maxWidth: '520px',
                        width: '100%',
                        background: '#f6e2c6',
                        border: '1px solid #dfa46f',
                        borderRadius: '16px',
                        padding: '2.5rem',
                        boxShadow: '0 20px 40px rgba(99, 18, 14, 0.1)',
                        textAlign: 'center',
                    }}>
                        <div style={{
                            width: '56px',
                            height: '56px',
                            borderRadius: '50%',
                            background: '#fee2e2',
                            color: '#dc2626',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '0 auto 1.5rem',
                        }}>
                            <AlertTriangle size={28} />
                        </div>

                        <h2 style={{
                            color: '#63120e',
                            fontSize: '1.4rem',
                            fontWeight: 700,
                            marginBottom: '0.75rem',
                        }}>
                            Session Restored with Safe Recovery
                        </h2>

                        <p style={{
                            color: '#8c3a2a',
                            fontSize: '0.9rem',
                            lineHeight: 1.5,
                            marginBottom: '1.5rem',
                        }}>
                            LexSetu protected your session from an unhandled error:
                        </p>

                        <div style={{
                            background: '#f1d1a6',
                            border: '1px solid #c98659',
                            borderRadius: '8px',
                            padding: '0.85rem 1rem',
                            fontSize: '0.82rem',
                            color: '#63120e',
                            fontFamily: 'monospace',
                            textAlign: 'left',
                            wordBreak: 'break-word',
                            maxHeight: '120px',
                            overflowY: 'auto',
                            marginBottom: '2rem',
                        }}>
                            {errorMsg}
                        </div>

                        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
                            <button
                                onClick={this.handleReload}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.75rem 1.25rem',
                                    background: '#8c3a2a',
                                    color: '#f9eedc',
                                    border: 'none',
                                    borderRadius: '8px',
                                    fontWeight: 600,
                                    fontSize: '0.9rem',
                                    cursor: 'pointer',
                                }}
                            >
                                <RefreshCw size={16} /> Reload Page
                            </button>
                            <button
                                onClick={this.handleGoHome}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    padding: '0.75rem 1.25rem',
                                    background: 'transparent',
                                    color: '#63120e',
                                    border: '1px solid #63120e',
                                    borderRadius: '8px',
                                    fontWeight: 600,
                                    fontSize: '0.9rem',
                                    cursor: 'pointer',
                                }}
                            >
                                <Home size={16} /> Return to Home
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
