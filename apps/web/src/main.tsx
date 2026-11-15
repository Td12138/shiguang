import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/tokens.css';
import './styles/global.css';

const ROOT_ID = 'root';

const container = document.getElementById(ROOT_ID);
if (!container) {
  throw new Error(`未找到根节点 #${ROOT_ID}`);
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
