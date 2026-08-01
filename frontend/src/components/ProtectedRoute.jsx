import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const ProtectedRoute = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();
    const location = useLocation();

    if (loading) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#63120e', color: '#f9eedc' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '50%', border: '3px solid #dfa46f', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }}></div>
                <span style={{ marginLeft: '1rem', fontWeight: 600, letterSpacing: '2px', fontSize: '0.85rem', textTransform: 'uppercase', color: '#f1d1a6' }}>Verifying Key...</span>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return children;
};

export default ProtectedRoute;
