'use client';

/**
 * Research — ask box + cited answer ("grounded or silent"), now as-of aware.
 *
 * The abstained state is a first-class result, not an error: when the API says
 * `abstained: true` the screen says so plainly instead of showing an uncited answer.
 * The "not advice" footer is always visible, on every state.
 *
 * Two extras:
 *   · an `as_of` date picker, which restricts the corpus to the text in force on that date;
 *   · each citation's `related` cross-references as chips — clicking one opens a side panel
 *     with `GET /research/refs?law=&article=` (cites / cited by), so a citation can be walked
 *     like a graph without leaving the answer.
 */
import { useCallback, useState } from 'react';
import { CitationCard } from '@/components/Explain';
import { Empty, Loading, Section } from '@/components/Bits';
import { ask, errorMessage, getRefs } from '@/lib/api';
import { formatPct } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { Citation, Jurisdiction, RelatedRef, ResearchAnswer } from '@/lib/types';

/** The refs side panel: one law/article in, its cross-reference graph out. */
function RefsPanel({ target, onClose }: { target: RelatedRef; onClose: () => void }) {
  const { t } = useI18n();
  const refs = useResource(
    useCallback(() => getRefs(target.law, target.article), [target.law, target.article]),
    [target.law, target.article],
  );
  const graph = refs.data;
  const error = refs.error;

  const list = (title: string, refs: RelatedRef[]) => (
    <>
      <h3 style={{ marginTop: 12 }}>{title}</h3>
      {refs.length === 0 ? (
        <Empty text={t('research.refs_empty')} />
      ) : (
        <div className="row small" style={{ flexWrap: 'wrap', gap: 6 }}>
          {refs.map((r, i) => (
            <span key={`${r.law}-${r.article}-${i}`} className="rule-chip">
              {r.law} {r.article}
            </span>
          ))}
        </div>
      )}
    </>
  );

  return (
    <aside className="card" style={{ position: 'sticky', top: 16 }}>
      <div className="row">
        <h2 style={{ margin: 0 }}>{t('research.refs')}</h2>
        <div style={{ flex: 1 }} />
        <button type="button" className="btn ghost" onClick={onClose}>
          {t('common.close')}
        </button>
      </div>
      <p className="small muted" style={{ marginTop: 4 }}>
        {target.law} · {target.article}
      </p>
      {error && <p className="err">{error}</p>}
      {!graph && !error && <Loading />}
      {graph && (
        <>
          {list(t('research.cites'), graph.cites)}
          {list(t('research.cited_by'), graph.cited_by)}
        </>
      )}
    </aside>
  );
}

function CitationWithRelated({
  citation,
  onOpenRef,
}: {
  citation: Citation;
  onOpenRef: (r: RelatedRef) => void;
}) {
  const { t } = useI18n();
  const related = citation.related ?? [];
  return (
    <div>
      <CitationCard citation={citation} />
      <div className="row small" style={{ flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
        <button
          type="button"
          className="btn ghost"
          style={{ padding: '2px 8px' }}
          onClick={() => onOpenRef({ law: citation.law, article: citation.article })}
        >
          {t('research.refs')}
        </button>
        {related.length > 0 && <span className="muted">{t('research.related')}:</span>}
        {related.map((r, i) => (
          <button
            key={`${r.law}-${r.article}-${i}`}
            type="button"
            className="rule-chip"
            onClick={() => onOpenRef(r)}
          >
            {r.law} {r.article}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ResearchPage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();
  const [question, setQuestion] = useState('');
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction | 'both'>('MX');
  const [useBooks, setUseBooks] = useState(true);
  const [asOf, setAsOf] = useState('');
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refTarget, setRefTarget] = useState<RelatedRef | null>(null);

  const send = async () => {
    const q = question.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(
        await ask({
          question: q,
          jurisdiction,
          lang,
          workspace: useBooks ? ws : null,
          as_of: asOf || null,
        }),
      );
      setAsked(q);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>{t('research.title')}</h1>
      </div>

      <div className={refTarget ? 'grid cols-2' : ''}>
        <div className="stack">
          <Section title={t('research.ask')}>
            <textarea
              value={question}
              rows={3}
              placeholder={t('research.placeholder')}
              style={{ width: '100%' }}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <div className="row" style={{ marginTop: 10, flexWrap: 'wrap' }}>
              <label className="field">
                {t('research.jurisdiction')}
                <select
                  value={jurisdiction}
                  onChange={(e) => setJurisdiction(e.target.value as Jurisdiction | 'both')}
                >
                  <option value="MX">MX</option>
                  <option value="US">US</option>
                  <option value="both">{t('research.both')}</option>
                </select>
              </label>
              <label className="field" title={t('research.as_of_hint')}>
                {t('research.as_of')}
                <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
              </label>
              <label className="row small" style={{ gap: 6 }}>
                <input type="checkbox" checked={useBooks} onChange={(e) => setUseBooks(e.target.checked)} />
                {ws}
              </label>
              <div style={{ flex: 1 }} />
              <button
                type="button"
                className="btn primary"
                onClick={() => void send()}
                disabled={busy || !question.trim()}
              >
                {t('research.send')}
              </button>
            </div>
            <p className="small muted" style={{ marginTop: 6 }}>
              {t('research.as_of_hint')}
            </p>
            {busy && <p className="small muted">{t('research.thinking')}</p>}
            {error && <p className="err">{error}</p>}
          </Section>

          {answer && (
            <Section title={t('research.answer')}>
              {asked && <p className="small muted">“{asked}”</p>}
              {answer.abstained ? (
                <div className="banner warn">{t('research.abstained')}</div>
              ) : (
                <>
                  <p className="chat-answer">{answer.answer}</p>
                  <div className="row small muted">
                    <span>
                      {t('research.confidence')}: {formatPct(answer.confidence, lang)}
                    </span>
                    {asOf && (
                      <span>
                        {t('research.as_of')} {asOf}
                      </span>
                    )}
                  </div>
                  {answer.citations.length > 0 && (
                    <div className="stack" style={{ gap: 8, marginTop: 14 }}>
                      <h3>{t('research.citations')}</h3>
                      {answer.citations.map((c, i) => (
                        <CitationWithRelated
                          key={`${c.law}-${c.article}-${i}`}
                          citation={c}
                          onOpenRef={setRefTarget}
                        />
                      ))}
                    </div>
                  )}
                </>
              )}
            </Section>
          )}

          <p className="notice">{t('research.footer')}</p>
        </div>

        {refTarget && <RefsPanel target={refTarget} onClose={() => setRefTarget(null)} />}
      </div>
    </>
  );
}
