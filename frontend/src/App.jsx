import { Routes, Route } from 'react-router-dom';
import Navigation from './components/Navigation';
import ProtectedRoute from './components/ProtectedRoute';
import ServerWakeup from './components/ServerWakeup';

import Home from './pages/Home';
import CaseFinder from './pages/CaseFinder';
import DraftAssistant from './pages/DraftAssistant';
import DraftReview from './pages/DraftReview';
import ClauseConflict from './pages/ClauseConflict';
import LegalAid from './pages/LegalAid';
import VerifyFiling from './pages/VerifyFiling';
import Login from './pages/Login';

import './App.css';

// 🔥 Layout with Outlet
import { Outlet } from "react-router-dom";

const AppShell = () => (
  <div className="nyayasetu-app">
    <Navigation />
    <main className="main-content">
      <Outlet />   {/* 🔥 THIS FIXES YOUR ISSUE */}
    </main>
  </div>
);

const App = () => {
  return (
    <>
    <ServerWakeup />
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />

      {/* Protected Layout */}
      <Route path="/" element={<AppShell />}>
        <Route index element={<ProtectedRoute><Home /></ProtectedRoute>} />
        <Route path="verify-filing" element={<ProtectedRoute><VerifyFiling /></ProtectedRoute>} />
        <Route path="case-finder" element={<ProtectedRoute><CaseFinder /></ProtectedRoute>} />
        <Route path="draft-assistant" element={<ProtectedRoute><DraftAssistant /></ProtectedRoute>} />
        <Route path="draft-review" element={<ProtectedRoute><DraftReview /></ProtectedRoute>} />
        <Route path="clause-conflict" element={<ProtectedRoute><ClauseConflict /></ProtectedRoute>} />
        <Route path="legal-aid" element={<ProtectedRoute><LegalAid /></ProtectedRoute>} />
      </Route>
    </Routes>
    </>
  );
};

export default App;