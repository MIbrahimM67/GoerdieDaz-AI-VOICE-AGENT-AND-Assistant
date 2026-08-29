import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { fetchCoreFacts, addCoreFact } from '../api/memory';
import { useAuth } from '../hooks/useAuth';

export default function ClientProfileModal({ isOpen, onClose }) {
  const [facts, setFacts] = useState([]);
  const [newFact, setNewFact] = useState('');
  const [loading, setLoading] = useState(false);
  const { accessToken } = useAuth();

  useEffect(() => {
    if (isOpen && accessToken) {
      loadFacts();
    }
  }, [isOpen, accessToken]);

  const loadFacts = async () => {
    try {
      const data = await fetchCoreFacts(accessToken);
      setFacts(data);
    } catch (err) {
      console.error('Failed to fetch facts', err);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newFact.trim()) return;
    setLoading(true);
    try {
      await addCoreFact(accessToken, newFact);
      setNewFact('');
      await loadFacts();
    } catch (err) {
      console.error('Failed to add fact', err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={styles.overlay}>
      <div style={styles.modal} className="fade-in">
        <div style={styles.header}>
          <h2 style={styles.title}>Core Memory</h2>
          <button onClick={onClose} style={styles.closeBtn} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <p style={styles.description}>
          Facts listed here are permanently injected into GeordieDaz's mind so it always remembers them.
        </p>

        <form onSubmit={handleAdd} style={styles.form}>
          <input
            style={styles.input}
            type="text"
            placeholder="e.g. I drive a red Ferrari"
            value={newFact}
            onChange={(e) => setNewFact(e.target.value)}
            disabled={loading}
          />
          <button style={styles.addBtn} type="submit" disabled={loading || !newFact.trim()}>
            {loading ? 'Adding...' : 'Add Fact'}
          </button>
        </form>

        <div style={styles.list}>
          {facts.length === 0 ? (
            <p style={styles.empty}>No core facts found. Add one above.</p>
          ) : (
            facts.map((fact, i) => (
              <div key={i} style={styles.factItem}>
                <div style={styles.factDot} />
                <span style={styles.factText}>{fact.content}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'fixed',
    top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.7)',
    backdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100,
  },
  modal: {
    width: '100%',
    maxWidth: '480px',
    background: 'var(--color-canvas-elevated)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-panel)',
    padding: 'var(--space-6)',
    boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 'var(--space-2)',
  },
  title: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: 'var(--color-text-body)',
  },
  closeBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--color-text-muted)',
    fontSize: '1.25rem',
    cursor: 'pointer',
  },
  description: {
    fontSize: '0.875rem',
    color: 'var(--color-text-muted)',
    marginBottom: 'var(--space-6)',
    lineHeight: 1.5,
  },
  form: {
    display: 'flex',
    gap: 'var(--space-2)',
    marginBottom: 'var(--space-6)',
  },
  input: {
    flex: 1,
    background: 'var(--color-canvas)',
    border: '1px solid var(--color-border)',
    borderRadius: '4px',
    padding: '0.5rem 0.75rem',
    color: 'var(--color-text-body)',
    fontFamily: 'inherit',
    fontSize: '0.875rem',
  },
  addBtn: {
    background: 'var(--color-accent)',
    color: '#000',
    border: 'none',
    borderRadius: '4px',
    padding: '0 1rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontSize: '0.875rem',
    transition: 'opacity 0.2s',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
    maxHeight: '300px',
    overflowY: 'auto',
  },
  empty: {
    fontSize: '0.875rem',
    color: 'var(--color-text-muted)',
    textAlign: 'center',
    padding: 'var(--space-4)',
  },
  factItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 'var(--space-3)',
    padding: 'var(--space-3)',
    background: 'rgba(255,255,255,0.02)',
    borderRadius: '4px',
    border: '1px solid var(--color-border)',
  },
  factDot: {
    width: 6, height: 6,
    borderRadius: '50%',
    background: 'var(--color-accent)',
    marginTop: 6,
    flexShrink: 0,
  },
  factText: {
    fontSize: '0.875rem',
    color: 'var(--color-text-body)',
    lineHeight: 1.5,
  },
};
