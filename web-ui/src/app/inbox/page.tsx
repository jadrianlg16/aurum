'use client';

/**
 * Inbox — the keyboard-driven review queue.
 *
 * Items are grouped by kind (quickadd / cfdi / bank / photo) and reviewed with the keyboard:
 * `j`/`k` move, `a` accepts, `l` opens the label picker, `r` rejects. Accept and reject call
 * the ingest inbox endpoints directly and drop the item from the local list, so the queue
 * advances without a refetch.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Empty, ErrorBox, Loading, Pct, Section } from '@/components/Bits';
import { PostingTable } from '@/components/Posting';
import { acceptInbox, errorMessage, listInbox, listLabels, rejectInbox } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { InboxItem, InboxKind } from '@/lib/types';

const KINDS: InboxKind[] = ['quickadd', 'cfdi', 'bank', 'photo'];
const KIND_KEY: Record<InboxKind, MsgKey> = {
  quickadd: 'inbox.kind.quickadd',
  cfdi: 'inbox.kind.cfdi',
  bank: 'inbox.kind.bank',
  photo: 'inbox.kind.photo',
};

export default function InboxPage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();

  const inbox = useResource(useCallback(() => listInbox(ws, 'pending'), [ws]), [ws]);
  const labels = useResource(useCallback(() => listLabels(ws), [ws]), [ws]);

  const [cursor, setCursor] = useState(0);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const items = useMemo(() => {
    const all = inbox.data ?? [];
    // Group by kind but keep one flat, ordered list so j/k crosses group boundaries.
    return KINDS.flatMap((k) => all.filter((i) => i.kind === k));
  }, [inbox.data]);

  const selected: InboxItem | undefined = items[Math.min(cursor, Math.max(items.length - 1, 0))];

  const drop = useCallback(
    (id: string) => {
      inbox.set((prev) => (prev ? prev.filter((i) => i.id !== id) : prev));
      setCursor((c) => Math.max(0, Math.min(c, items.length - 2)));
    },
    [inbox, items.length],
  );

  const doAccept = useCallback(
    async (label?: string) => {
      if (!selected || busy) return;
      setBusy(true);
      setError(null);
      try {
        await acceptInbox(ws, selected.id, label ? { label } : undefined);
        setFlash(`${t('inbox.accepted')}: ${selected.proposed.narration}`);
        drop(selected.id);
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setBusy(false);
        setPicking(false);
      }
    },
    [selected, busy, ws, t, drop],
  );

  const doReject = useCallback(async () => {
    if (!selected || busy) return;
    setBusy(true);
    setError(null);
    try {
      await rejectInbox(ws, selected.id);
      setFlash(`${t('inbox.rejected')}: ${selected.proposed.narration}`);
      drop(selected.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [selected, busy, ws, t, drop]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      switch (e.key) {
        case 'j':
          e.preventDefault();
          setCursor((c) => Math.min(c + 1, items.length - 1));
          break;
        case 'k':
          e.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
          break;
        case 'a':
          e.preventDefault();
          void doAccept();
          break;
        case 'l':
          e.preventDefault();
          setPicking((v) => !v);
          break;
        case 'r':
          e.preventDefault();
          void doReject();
          break;
        case 'Escape':
          setPicking(false);
          break;
        default:
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [items.length, doAccept, doReject]);

  if (inbox.loading) return <Loading />;
  if (inbox.error) return <ErrorBox message={inbox.error} onRetry={inbox.reload} />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('inbox.title')}</h1>
          <div className="sub">
            {items.length} {t('inbox.pending')} · {t('inbox.keys')}
          </div>
        </div>
      </div>

      {flash && <p className="small" style={{ color: 'var(--pos)' }}>{flash}</p>}
      {error && <p className="err">{error}</p>}

      {items.length === 0 ? (
        <div className="card">
          <Empty text={t('inbox.empty')} />
        </div>
      ) : (
        <div className="inbox-layout">
          <div className="stack" style={{ gap: 12 }}>
            {KINDS.map((kind) => {
              const group = items.filter((i) => i.kind === kind);
              if (group.length === 0) return null;
              return (
                <div key={kind}>
                  <h3>
                    {t(KIND_KEY[kind])} · {group.length}
                  </h3>
                  <div className="stack" style={{ gap: 6 }}>
                    {group.map((item) => {
                      const index = items.indexOf(item);
                      return (
                        <button
                          key={item.id}
                          type="button"
                          className="inbox-item"
                          aria-current={selected?.id === item.id ? 'true' : undefined}
                          onClick={() => setCursor(index)}
                        >
                          <div className="row" style={{ gap: 6 }}>
                            <strong className="small">{item.proposed.payee ?? item.proposed.narration}</strong>
                            <div style={{ flex: 1 }} />
                            <span className={`badge ${item.confidence >= 0.8 ? 'pos' : item.confidence >= 0.6 ? 'warn' : 'neg'}`}>
                              <Pct value={item.confidence} />
                            </span>
                          </div>
                          <span className="small muted">
                            {formatDate(item.proposed.date, lang)} · {item.proposed.narration}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="stack">
            {selected && (
              <Section
                title={t('inbox.proposed')}
                actions={
                  <div className="row" style={{ gap: 6 }}>
                    <button type="button" className="btn primary" onClick={() => void doAccept()} disabled={busy}>
                      {t('inbox.accept')} <span className="kbd">a</span>
                    </button>
                    <button type="button" className="btn" onClick={() => setPicking((v) => !v)} disabled={busy}>
                      {t('inbox.relabel')} <span className="kbd">l</span>
                    </button>
                    <button type="button" className="btn" onClick={() => void doReject()} disabled={busy}>
                      {t('inbox.reject')} <span className="kbd">r</span>
                    </button>
                  </div>
                }
              >
                <div className="row" style={{ marginBottom: 10 }}>
                  <span className="badge neutral">{t(KIND_KEY[selected.kind])}</span>
                  <span className={`badge ${selected.confidence >= 0.8 ? 'pos' : 'warn'}`}>
                    {t('inbox.confidence')} <Pct value={selected.confidence} />
                  </span>
                  {selected.source_ref && <span className="small muted rule-chip">{selected.source_ref}</span>}
                </div>

                <PostingTable txn={selected.proposed} />

                {picking && (
                  <div className="card" style={{ marginTop: 12 }}>
                    <h3>{t('inbox.pick_label')}</h3>
                    {labels.loading ? (
                      <Loading />
                    ) : (
                      <div className="row" style={{ gap: 6 }}>
                        {(labels.data ?? []).map((l) => (
                          <button key={l.id} type="button" className="btn" onClick={() => void doAccept(l.name)}>
                            {l.icon} {l.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </Section>
            )}
          </div>
        </div>
      )}
    </>
  );
}
