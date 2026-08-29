/**
 * ToolActivity — Minimalist thinking/memory animation
 * Shows a subtle inline indicator when the AI is searching memory or storing facts.
 * Inspired by Claude/ChatGPT thinking animations.
 */
import { useEffect, useState } from 'react';
import { Search, Database, Clock } from 'lucide-react';
import useAppStore from '../stores/appStore';

const TOOL_LABELS = {
  search_memory: 'Thinking',
  store_fact: 'Updating memory',
  search_history: 'Recalling',
};

const TOOL_ICONS = {
  search_memory: Search,
  store_fact: Database,
  search_history: Clock,
};

export default function ToolActivity() {
  const { activeToolCall } = useAppStore();
  const [dots, setDots] = useState('');

  useEffect(() => {
    if (!activeToolCall) return;
    const interval = setInterval(() => {
      setDots((d) => (d.length >= 3 ? '' : d + '.'));
    }, 400);
    return () => clearInterval(interval);
  }, [activeToolCall]);

  if (!activeToolCall) return null;

  const Icon = TOOL_ICONS[activeToolCall] || Search;
  const label = TOOL_LABELS[activeToolCall] || 'Thinking';

  return (
    <div className="tool-activity">
      <div className="tool-activity-inner">
        <div className="tool-activity-icon">
          <Icon size={14} />
        </div>
        <span className="tool-activity-label">
          {label}{dots}
        </span>
      </div>
    </div>
  );
}
