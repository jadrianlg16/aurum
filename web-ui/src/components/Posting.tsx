'use client';

/** The proposed/booked double-entry posting, rendered the same way everywhere. */
import { useI18n } from '@/lib/i18n';
import { formatDate } from '@/lib/format';
import type { Transaction } from '@/lib/types';
import { Money } from './Bits';

export function PostingTable({ txn }: { txn: Transaction }) {
  const { t, lang } = useI18n();
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row small">
        <strong>{formatDate(txn.date, lang)}</strong>
        <span>{txn.payee ?? <span className="muted">{t('common.none')}</span>}</span>
        <span className="muted">{txn.narration}</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('common.account')}</th>
              <th className="num">{t('common.amount')}</th>
            </tr>
          </thead>
          <tbody>
            {txn.postings.map((p, i) => (
              <tr key={`${p.account}-${i}`}>
                <td className="money">{p.account}</td>
                <td className="num">
                  {p.amount ? <Money value={p.amount} sign /> : <span className="muted">auto</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {Object.keys(txn.meta).length > 0 && (
        <div className="row small muted">
          {Object.entries(txn.meta).map(([k, v]) => (
            <span key={k} className="rule-chip">
              {k}: {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
