'use client';

/**
 * Plan › Investments (`aurum/holdings` + `aurum/fx`).
 *
 * Positions, realized gains, allocation, contributions-vs-limits and the two write forms
 * (trade, manual price). Every figure is the API's: the allocation bar's *widths* are the only
 * place a decimal becomes a number, and a width is geometry, never a displayed value.
 *
 * FX is deliberately failure-tolerant: `GET /fx/rate` 404s whenever there is no Banxico token
 * and no fixture, which is the normal offline case, so a missing rate renders as a plain
 * explanation rather than an error box.
 */
import { useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { AccountField, DecimalField, Dialog, SelectField, TextField } from '@/components/Form';
import { VerifyChip } from '@/components/VerifyChips';
import {
  createPrice,
  createTrade,
  errorMessage,
  getFxRate,
  getHoldings,
  getLedgerAccounts,
} from '@/lib/api';
import { formatDate, toChartNumber } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { HoldingsOverview, TradeKind } from '@/lib/types';

const KINDS: TradeKind[] = ['buy', 'sell', 'dividend', 'interest', 'contribution'];
const KIND_KEY = {
  buy: 'hold.kind.buy',
  sell: 'hold.kind.sell',
  dividend: 'hold.kind.dividend',
  interest: 'hold.kind.interest',
  contribution: 'hold.kind.contribution',
} as const;

const today = () => new Date().toISOString().slice(0, 10);

/** Allocation as a single stacked bar; the palette repeats after six classes, which is plenty. */
function AllocationBar({ by }: { by: Record<string, string> }) {
  const entries = Object.entries(by);
  const nums = entries.map(([, v]) => toChartNumber({ amount: v, currency: '' }));
  const total = nums.reduce((a, b) => a + b, 0);
  if (entries.length === 0 || total <= 0) return null;
  const tones = ['var(--gold)', 'var(--pos, #4a7)', 'var(--info, #58a)', 'var(--warn, #c94)', '#87a', '#a78'];
  return (
    <>
      <div className="row" style={{ gap: 0, height: 14, borderRadius: 7, overflow: 'hidden', margin: '8px 0' }}>
        {entries.map(([k], i) => (
          <span
            key={k}
            title={`${k}: ${by[k]}`}
            style={{ width: `${(nums[i] / total) * 100}%`, background: tones[i % tones.length], height: '100%' }}
          />
        ))}
      </div>
      <div className="row small" style={{ flexWrap: 'wrap', gap: 10 }}>
        {entries.map(([k, v], i) => (
          <span key={k} className="row" style={{ gap: 4 }}>
            <span
              aria-hidden="true"
              style={{ width: 9, height: 9, borderRadius: 2, background: tones[i % tones.length] }}
            />
            {k} <span className="money">{v}</span>
          </span>
        ))}
      </div>
    </>
  );
}

function TradeDialog({
  ws,
  data,
  accounts,
  onClose,
}: {
  ws: string;
  data: HoldingsOverview;
  accounts: string[];
  onClose: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const [date, setDate] = useState(today());
  const [account, setAccount] = useState(data.positions[0]?.account ?? 'Assets:Investments:Brokerage');
  const [symbol, setSymbol] = useState(data.symbols[0]?.symbol ?? '');
  const [kind, setKind] = useState<TradeKind>('buy');
  const [units, setUnits] = useState('');
  const [price, setPrice] = useState('');
  const [currency, setCurrency] = useState(data.symbols[0]?.currency ?? 'USD');
  const [fees, setFees] = useState('');
  const [counter, setCounter] = useState('');
  const [limitKey, setLimitKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await createTrade(ws, {
        date,
        account,
        symbol,
        kind,
        units,
        price: { amount: price, currency },
        fees: fees ? { amount: fees, currency } : null,
        counter_account: counter || null,
        limit_key: limitKey || null,
      });
      onClose(true);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <Dialog title={t('hold.add_trade')} onCancel={() => onClose(false)} onSubmit={() => void submit()} busy={busy} error={error} wide>
      <div className="grid cols-2">
        <div>
          <TextField label={t('common.date')} type="date" value={date} onChange={setDate} required />
          <AccountField
            label={t('common.account')}
            value={account}
            onChange={setAccount}
            accounts={accounts}
            required
          />
          <TextField
            label={t('hold.symbol')}
            value={symbol}
            onChange={(v) => setSymbol(v.toUpperCase())}
            list="aurum-symbols"
            required
          />
          <datalist id="aurum-symbols">
            {data.symbols.map((s) => (
              <option key={s.symbol} value={s.symbol} />
            ))}
          </datalist>
          <SelectField
            label={t('common.kind')}
            value={kind}
            onChange={(v) => setKind(v as TradeKind)}
            options={KINDS.map((k) => ({ value: k, label: t(KIND_KEY[k]) }))}
          />
        </div>
        <div>
          <DecimalField label={t('hold.units')} value={units} onChange={setUnits} required />
          <DecimalField label={t('hold.price')} value={price} onChange={setPrice} required />
          <TextField label={t('common.currency')} value={currency} onChange={(v) => setCurrency(v.toUpperCase())} />
          <DecimalField label={t('hold.fees')} value={fees} onChange={setFees} />
          <AccountField
            label={t('hold.counter_account')}
            value={counter}
            onChange={setCounter}
            accounts={accounts}
          />
          <SelectField
            label={t('hold.limit_key')}
            value={limitKey}
            onChange={setLimitKey}
            options={[
              { value: '', label: t('common.none') },
              ...data.contributions.limits.map((l) => ({ value: l.key, label: l.label })),
            ]}
          />
        </div>
      </div>
    </Dialog>
  );
}

function PriceDialog({
  ws,
  data,
  onClose,
}: {
  ws: string;
  data: HoldingsOverview;
  onClose: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const [symbol, setSymbol] = useState(data.positions[0]?.symbol ?? data.symbols[0]?.symbol ?? '');
  const [date, setDate] = useState(today());
  const [price, setPrice] = useState('');
  const [currency, setCurrency] = useState(data.symbols[0]?.currency ?? 'USD');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await createPrice(ws, { symbol, date, price: { amount: price, currency } });
      onClose(true);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <Dialog title={t('hold.add_price')} onCancel={() => onClose(false)} onSubmit={() => void submit()} busy={busy} error={error}>
      <TextField label={t('hold.symbol')} value={symbol} onChange={(v) => setSymbol(v.toUpperCase())} required />
      <TextField label={t('common.date')} type="date" value={date} onChange={setDate} required />
      <DecimalField label={t('hold.price')} value={price} onChange={setPrice} required />
      <TextField label={t('common.currency')} value={currency} onChange={(v) => setCurrency(v.toUpperCase())} />
    </Dialog>
  );
}

/** The FX card: a rate when one exists, a plain explanation when the lookup 404s. */
function FxCard() {
  const { t, lang } = useI18n();
  const [base, setBase] = useState('USD');
  const [quote, setQuote] = useState('MXN');
  const [date, setDate] = useState(today());
  const [pair, setPair] = useState<{ base: string; quote: string; date: string } | null>(null);

  const rate = useResource(
    useCallback(
      () => (pair ? getFxRate(pair.base, pair.quote, pair.date) : Promise.resolve(null)),
      [pair],
    ),
    [pair],
  );

  return (
    <Section title={t('fx.title')}>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <label className="field">
          {t('fx.base')}
          <input value={base} onChange={(e) => setBase(e.target.value.toUpperCase())} style={{ width: 76 }} />
        </label>
        <label className="field">
          {t('fx.quote')}
          <input value={quote} onChange={(e) => setQuote(e.target.value.toUpperCase())} style={{ width: 76 }} />
        </label>
        <label className="field">
          {t('common.date')}
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => setPair({ base, quote, date })}>
          {t('fx.lookup')}
        </button>
      </div>
      {pair && rate.loading && <Loading />}
      {pair && !rate.loading && (rate.error || !rate.data) && (
        <p className="small muted" style={{ marginTop: 8 }}>
          {t('fx.none')}
        </p>
      )}
      {rate.data && (
        <div className="row" style={{ marginTop: 8 }}>
          <span className="metric-label">
            {rate.data.base}/{rate.data.quote}
          </span>
          <strong className="money">{rate.data.rate}</strong>
          <span className="small muted">{formatDate(rate.data.date, lang)}</span>
          {rate.data.source && <span className="badge neutral">{rate.data.source}</span>}
        </div>
      )}
    </Section>
  );
}

export function HoldingsPanel({ ws }: { ws: string }) {
  const { t, lang } = useI18n();
  const holdings = useResource(useCallback(() => getHoldings(ws), [ws]), [ws]);
  const accounts = useResource(useCallback(() => getLedgerAccounts(ws), [ws]), [ws]);
  const [tradeOpen, setTradeOpen] = useState(false);
  const [priceOpen, setPriceOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  if (holdings.loading) return <Loading />;
  if (holdings.error) return <ErrorBox message={holdings.error} onRetry={holdings.reload} />;
  if (!holdings.data) return <Empty />;
  const d = holdings.data;

  return (
    <div className="stack">
      {note && <div className="banner info">{note}</div>}

      <Section
        title={t('hold.positions')}
        actions={
          <div className="row" style={{ gap: 6 }}>
            <button type="button" className="btn" onClick={() => setPriceOpen(true)}>
              {t('hold.add_price')}
            </button>
            <button type="button" className="btn primary" onClick={() => setTradeOpen(true)}>
              + {t('hold.add_trade')}
            </button>
          </div>
        }
      >
        {d.positions.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('hold.symbol')}</th>
                  <th>{t('common.account')}</th>
                  <th>{t('hold.asset_class')}</th>
                  <th className="num">{t('hold.units')}</th>
                  <th className="num">{t('hold.cost')}</th>
                  <th className="num">{t('hold.market_value')}</th>
                  <th className="num">{t('hold.unrealized')}</th>
                </tr>
              </thead>
              <tbody>
                {d.positions.map((p) => (
                  <tr key={`${p.account}-${p.symbol}`}>
                    <td>
                      <strong>{p.symbol}</strong>
                      {p.name && <div className="small muted">{p.name}</div>}
                    </td>
                    <td className="small" style={{ fontFamily: 'var(--mono)' }}>
                      {p.account}
                    </td>
                    <td>{p.asset_class && <span className="badge neutral">{p.asset_class}</span>}</td>
                    <td className="num money">{p.units}</td>
                    <td className="num">
                      <Money value={p.cost_basis} />
                    </td>
                    <td className="num">
                      {p.market_value ? (
                        <>
                          <Money value={p.market_value} />
                          {p.price_as_of && <div className="small muted">{formatDate(p.price_as_of, lang)}</div>}
                        </>
                      ) : (
                        <span className="small muted">{t('hold.no_price')}</span>
                      )}
                    </td>
                    <td className="num">
                      {p.unrealized_gain ? <Money value={p.unrealized_gain} sign /> : <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Explain explain={d.explain} />
      </Section>

      <Section title={t('hold.allocation')}>
        {Object.keys(d.allocation.by_asset_class).length === 0 ? (
          <p className="small muted">{t('hold.no_allocation')}</p>
        ) : (
          <AllocationBar by={d.allocation.by_asset_class} />
        )}
        <div className="row small muted" style={{ marginTop: 8 }}>
          <span>{t('hold.total_market_value')}</span>
          <strong className="money">{d.allocation.total_market_value}</strong>
        </div>
      </Section>

      <Section title={t('hold.realized')}>
        {d.realized_gains.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('common.date')}</th>
                  <th>{t('hold.symbol')}</th>
                  <th className="num">{t('hold.units')}</th>
                  <th className="num">{t('hold.proceeds')}</th>
                  <th className="num">{t('hold.cost')}</th>
                  <th className="num">{t('hold.gain')}</th>
                </tr>
              </thead>
              <tbody>
                {d.realized_gains.map((g, i) => (
                  <tr key={`${g.symbol}-${g.date}-${i}`}>
                    <td>{formatDate(g.date, lang)}</td>
                    <td>
                      {g.symbol}
                      {g.acquired && (
                        <div className="small muted">
                          {t('hold.acquired')} {formatDate(g.acquired, lang)}
                        </div>
                      )}
                    </td>
                    <td className="num money">{g.units}</td>
                    <td className="num">
                      <Money value={g.proceeds} />
                    </td>
                    <td className="num">
                      <Money value={g.cost_basis} />
                    </td>
                    <td className="num">
                      <Money value={g.gain} sign />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title={`${t('hold.contributions')} · ${d.contributions.year}`}>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('common.label')}</th>
                <th>{t('watch.jurisdiction')}</th>
                <th className="num">{t('hold.contributed')}</th>
                <th className="num">{t('hold.limit')}</th>
                <th className="num">{t('hold.remaining')}</th>
              </tr>
            </thead>
            <tbody>
              {d.contributions.limits.map((l) => (
                <tr key={l.key}>
                  <td>
                    {l.label} {!l.verified && <VerifyChip />}
                  </td>
                  <td>
                    <span className="badge neutral">{l.jurisdiction}</span>
                  </td>
                  <td className="num">
                    <Money value={l.contributed} />
                  </td>
                  <td className="num">
                    <Money value={l.limit} />
                  </td>
                  <td className="num">
                    <Money value={l.remaining} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={t('hold.tax_lens')}>
        <Explain explain={d.tax_explain} defaultOpen />
      </Section>

      <FxCard />

      {tradeOpen && (
        <TradeDialog
          ws={ws}
          data={d}
          accounts={accounts.data ?? []}
          onClose={(saved) => {
            setTradeOpen(false);
            if (saved) {
              setNote(t('hold.trade_saved'));
              holdings.reload();
            }
          }}
        />
      )}
      {priceOpen && (
        <PriceDialog
          ws={ws}
          data={d}
          onClose={(saved) => {
            setPriceOpen(false);
            if (saved) {
              setNote(t('hold.price_saved'));
              holdings.reload();
            }
          }}
        />
      )}
    </div>
  );
}
