import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import './styles/index.css';

// Global keyframe styles (injected once)
const globalStyles = document.createElement('style');
globalStyles.textContent = `
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes pulse-ring {
    0%   { transform: scale(0.95); opacity: 0.7; }
    50%  { transform: scale(1.05); opacity: 0.3; }
    100% { transform: scale(0.95); opacity: 0.7; }
  }
  @keyframes ripple {
    0%   { transform: translate(-50%, -50%) scale(1); opacity: 0.5; }
    100% { transform: translate(-50%, -50%) scale(2.2); opacity: 0; }
  }
  @keyframes glow-pulse {
    0%, 100% { opacity: 0.2; }
    50%       { opacity: 0.4; }
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;
document.head.appendChild(globalStyles);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
