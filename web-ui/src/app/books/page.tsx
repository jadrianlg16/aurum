'use client';

/**
 * Books — journal, accounts tree with balances, and the BQL box.
 *
 * The accounts "tree" is built in the browser by splitting Beancount account names on ':'
 * and indenting; the API returns a flat `account → amounts` map, and inventing
 * a tree endpoint would be an API change. Balances are shown per commodity, unsummed,
 * because summing across currencies is arithmetic the UI must never do.
 */
import { useCallback, useMemo, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { RowActions } from '@/components/Form';
import { TransactionDialog, VoidTransactionDialog } from '@/components/TxnForm';
import { errorMessage, getBalances, getJournal, getLedgerAccounts, runQuery } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodRange } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { QueryRows, Transaction } from '@/lib/types';

type Tab = 'journal' | 'accounts' | 'query';

export default function BooksPage() {
  const { t, lang } = useI18n();
  const { ws, current } = useWorkspace();
  const [tab, setTab] = useState<Tab>('journal');
  // `null` = closed; `{txn: null}` = create; `{txn}` = edit that transaction.
  const [txnForm, setTxnForm] = useState<{ txn: Transaction | null; id: string | null } | null>(null);
  const [voidForm, setVoidForm] = useState<{ id: string; narration: string } | null>(null);

  const defaults = periodRange(closePeriod());
  const [start, setStart] = useState(defaults.start);
  const [end, setEnd] = useState(defaults.end);
  const [prefix, setPrefix] = useState('');

  const journal = useResource(
    useCallback(
      () => getJournal(ws, { start: start || undefined, end: end || undefined, account_prefix: prefix || undefined }),
      [ws, start, end, prefix],
    ),
    [ws, start, end, prefix],
  );
  const balances = useResource(useCallback(() => getBalances(ws), [ws]), [ws]);
  const accounts = useResource(useCallback(() => getLedgerAccounts(ws), [ws]), [ws]);

  const [bql, setBql] = useState('SELECT account, sum(position) GROUP BY account');
  const [rows, setRows] = useState<QueryRows | null>(null);
  const [qErr, setQErr] = useState<string | null>(null);
  const [qBusy, setQBusy] = useState(false);

  const tree = useMemo(() => {
    const names = accounts.data ?? Object.keys(balances.data ?? {});
    return [...names].sort();
  }, [accounts.data, balances.data]);

  const runBql = async () => {
    setQBusy(true);
    setQErr(null);
    try {
      setRows(await runQuery(ws, bql));
    } catch (e) {
      setQErr(errorMessage(e));
      setRows(null);
    } finally {
      setQBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>{t('books.title')}</h1>
      </div>

      <div className="tabs" role="tablist">
        {(['journal', 'accounts', 'query'] as Tab[]).map((x) => (
          <button key={x} type="button" role="tab" aria-selected={tab === x} onClick={() => setTab(x)}>
            {t(x === 'journal' ? 'books.journal' : x === 'accounts' ? 'books.accounts' : 'books.query')}
          </button>
        ))}
      </div>

      {tab === 'journal' && (
        <Section
          title={t('books.journal')}
          actions={
            <div className="row" style={{ gap: 8 }}>
              <button type="button" className="btn primary" onClick={() => setTxnForm({ txn: null, id: null })}>
                {t('txn.new')}
              </button>
              <label className="field">
                {t('books.from')}
                <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              </label>
              <label className="field">
                {t('books.to')}
                <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
              </label>
              <label className="field">
                {t('books.account_prefix')}
                <input
                  type="text"
                  value={prefix}
                  placeholder="Assets:"
                  onChange={(e) => setPrefix(e.target.value)}
                />
              </label>
            </div>
          }
        >
          {journal.loading ? (
            <Loading />
          ) : journal.error ? (
            <ErrorBox message={journal.error} onRetry={journal.reload} />
          ) : (journal.data?.length ?? 0) === 0 ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('common.date')}</th>
                    <th>{t('common.payee')}</th>
                    <th>{t('books.narration')}</th>
                    <th>{t('books.postings')}</th>
                    <th>{t('common.label')}</th>
                    <th className="num">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {journal.data!.map((tx) => (
                    <tr key={tx.links[0] ?? `${tx.date}-${tx.narration}`}>
                      <td>{formatDate(tx.date, lang)}</td>
                      <td>{tx.payee ?? '—'}</td>
                      <td>{tx.narration}</td>
                      <td>
                        {tx.postings.map((p, i) => (
                          <div key={`${p.account}-${i}`} className="row small" style={{ gap: 8 }}>
                            <span className="money">{p.account}</span>
                            <span style={{ marginLeft: 'auto' }}>
                              {p.amount ? <Money value={p.amount} sign /> : <span className="muted">auto</span>}
                            </span>
                          </div>
                        ))}
                      </td>
                      <td>
                        {tx.meta.label ? <span className="badge neutral">{tx.meta.label}</span> : '—'}
                        {tx.meta.source && <span className="rule-chip" style={{ marginLeft: 4 }}>{tx.meta.source}</span>}
                      </td>
                      <td className="num">
                        {tx.links[0] ? (
                          <RowActions
                            onEdit={() => setTxnForm({ txn: tx, id: tx.links[0] })}
                            onDelete={() => setVoidForm({ id: tx.links[0], narration: tx.narration })}
                          />
                        ) : (
                          <span className="muted small">{t('txn.no_id')}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {tab === 'accounts' && (
        <Section title={t('books.accounts')}>
          {balances.loading ? (
            <Loading />
          ) : balances.error ? (
            <ErrorBox message={balances.error} onRetry={balances.reload} />
          ) : tree.length === 0 ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('common.account')}</th>
                    <th className="num">{t('books.balance')}</th>
                  </tr>
                </thead>
                <tbody>
                  {tree.map((name) => {
                    const depth = name.split(':').length - 1;
                    const leaf = name.split(':').pop();
                    const amounts = balances.data?.[name] ?? [];
                    return (
                      <tr key={name}>
                        <td style={{ paddingLeft: 8 + depth * 16 }} className="money">
                          {leaf}
                          <span className="muted small" style={{ marginLeft: 8 }}>
                            {name}
                          </span>
                        </td>
                        <td className="num">
                          {amounts.length === 0 ? (
                            <span className="muted">—</span>
                          ) : (
                            amounts.map((a, i) => (
                              <div key={`${a.currency}-${i}`}>
                                <Money value={a} sign />
                              </div>
                            ))
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {tab === 'query' && (
        <Section title={t('books.query')}>
          <p className="notice">{t('books.query.hint')}</p>
          <textarea
            value={bql}
            onChange={(e) => setBql(e.target.value)}
            rows={3}
            style={{ width: '100%', fontFamily: 'var(--mono)', marginTop: 10 }}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" className="btn primary" onClick={() => void runBql()} disabled={qBusy}>
              {t('books.query.run')}
            </button>
          </div>
          {qErr && <p className="err">{qErr}</p>}
          {rows && rows.length > 0 && (
            <div className="table-scroll" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    {Object.keys(rows[0]).map((k) => (
                      <th key={k}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      {Object.keys(rows[0]).map((k) => (
                        <td key={k} className="money">
                          {String(r[k] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {txnForm && (
        <TransactionDialog
          ws={ws}
          accounts={accounts.data ?? []}
          baseCurrency={current?.base_currency ?? 'MXN'}
          txn={txnForm.txn}
          txnId={txnForm.id}
          onClose={(saved) => {
            setTxnForm(null);
            if (saved) {
              journal.reload();
              balances.reload();
            }
          }}
        />
      )}
      {voidForm && (
        <VoidTransactionDialog
          ws={ws}
          txnId={voidForm.id}
          narration={voidForm.narration}
          onClose={(saved) => {
            setVoidForm(null);
            if (saved) {
              journal.reload();
              balances.reload();
            }
          }}
        />
      )}
    </>
  );
}
