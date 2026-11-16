import { useEffect, useState } from 'react';
import { Briefcase, Calendar } from 'lucide-react';
import { formatBRL, formatDateBR, formatNumber, formatPct, STRATEGY_LABELS } from '../formatters';
import { StrategyName, StrategyResult } from '../types';

interface Props {
  results: Record<string, StrategyResult>;
}

export function PortfolioInspector({ results }: Props) {
  const availableStrategies = Object.keys(results) as StrategyName[];
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyName>(
    availableStrategies[0] ?? 'acquirers_multiple',
  );
  const [selectedRebalanceIdx, setSelectedRebalanceIdx] = useState<number>(0);

  useEffect(() => {
    if (!results[selectedStrategy] && availableStrategies.length > 0) {
      setSelectedStrategy(availableStrategies[0]);
    }
  }, [results, selectedStrategy, availableStrategies]);

  const currentResult = results[selectedStrategy];
  const rebalances = currentResult?.rebalances ?? [];

  useEffect(() => {
    if (rebalances.length > 0) {
      // Default to latest portfolio rebalance so user immediately sees current/final portfolio
      setSelectedRebalanceIdx(rebalances.length - 1);
    } else {
      setSelectedRebalanceIdx(0);
    }
  }, [selectedStrategy, rebalances.length]);

  if (!currentResult || rebalances.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
        Nenhum rebalanceamento disponível para inspeção.
      </div>
    );
  }

  const safeIdx = Math.min(selectedRebalanceIdx, rebalances.length - 1);
  const event = rebalances[safeIdx];
  const isMagicFormula = selectedStrategy === 'magic_formula';

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex items-center gap-2">
          {availableStrategies.map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setSelectedStrategy(st)}
              className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition ${
                selectedStrategy === st
                  ? st === 'acquirers_multiple'
                    ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/50'
                    : 'bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/50'
                  : 'bg-slate-800/70 text-slate-400 hover:text-slate-200'
              }`}
            >
              {STRATEGY_LABELS[st]}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <Calendar className="h-4 w-4 text-slate-400" />
            <span>Data da Carteira:</span>
            <select
              value={safeIdx}
              onChange={(e) => setSelectedRebalanceIdx(Number(e.target.value))}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-medium text-slate-100 focus:border-emerald-500 focus:outline-none"
            >
              {rebalances.map((reb, idx) => (
                <option key={reb.date} value={idx}>
                  #{idx + 1} — {formatDateBR(reb.date)} ({reb.holdings_count} ativos ·{' '}
                  {formatBRL(reb.portfolio_equity)})
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {(event.turnover_tickers_added.length > 0 || event.turnover_tickers_removed.length > 0) && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <div className="mb-2 text-xs font-semibold text-emerald-400">
              Entraram na Carteira ({event.turnover_tickers_added.length})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {event.turnover_tickers_added.length > 0 ? (
                event.turnover_tickers_added.map((t) => (
                  <span
                    key={t}
                    className="rounded bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300"
                  >
                    +{t}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">Nenhuma adição</span>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
            <div className="mb-2 text-xs font-semibold text-rose-400">
              Saíram da Carteira ({event.turnover_tickers_removed.length})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {event.turnover_tickers_removed.length > 0 ? (
                event.turnover_tickers_removed.map((t) => (
                  <span
                    key={t}
                    className="rounded bg-rose-500/15 px-2 py-0.5 text-[11px] font-medium text-rose-300"
                  >
                    −{t}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">Nenhuma saída (montagem inicial ou manutenção)</span>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Briefcase className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-100">
              Composição em {formatDateBR(event.date)} — {STRATEGY_LABELS[selectedStrategy]}
            </h3>
          </div>
          <div className="text-xs text-slate-400">
            Patrimônio alocado:{' '}
            <span className="font-semibold text-slate-200">{formatBRL(event.portfolio_equity)}</span> ·{' '}
            {event.holdings_count} ativos em pesos iguais
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950/60 text-slate-400 uppercase">
              <tr>
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3">Empresa</th>
                <th className="px-4 py-3 text-right">Peso</th>
                <th className="px-4 py-3 text-right">Preço Ajust.</th>
                <th className="px-4 py-3 text-right">EBITDA / EV (EY)</th>
                <th className="px-4 py-3 text-right">EV / EBITDA</th>
                <th className="px-4 py-3 text-right">ROIC (12m)</th>
                {isMagicFormula && (
                  <>
                    <th className="px-4 py-3 text-right">Rank EY</th>
                    <th className="px-4 py-3 text-right">Rank ROIC</th>
                    <th className="px-4 py-3 text-right">Nota (Soma)</th>
                  </>
                )}
                <th className="px-4 py-3 text-right">EBITDA (mil)</th>
                <th className="px-4 py-3 text-right">EV (mil)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {event.holdings.map((h, idx) => {
                const evMultiple = h.earnings_yield > 0 ? 1 / h.earnings_yield : null;
                return (
                  <tr key={h.ticker} className="hover:bg-slate-800/40">
                    <td className="px-4 py-2.5 text-slate-500">{idx + 1}</td>
                    <td className="px-4 py-2.5 font-mono font-semibold text-slate-100">{h.ticker}</td>
                    <td className="px-4 py-2.5 text-slate-300">{h.company_name}</td>
                    <td className="px-4 py-2.5 text-right text-slate-300">
                      {formatPct(h.weight * 100, 2)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-200">{formatBRL(h.price)}</td>
                    <td className="px-4 py-2.5 text-right font-semibold text-emerald-400">
                      {formatPct(h.earnings_yield * 100, 2)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-300">
                      {evMultiple !== null ? `${formatNumber(evMultiple)}x` : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right text-sky-300">
                      {h.roic !== null ? formatPct(h.roic, 2) : '—'}
                    </td>
                    {isMagicFormula && (
                      <>
                        <td className="px-4 py-2.5 text-right text-slate-400">
                          {formatNumber(h.rank_yield)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-400">
                          {formatNumber(h.rank_roic)}
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold text-sky-400">
                          {formatNumber(h.score)}
                        </td>
                      </>
                    )}
                    <td className="px-4 py-2.5 text-right text-slate-400">{formatNumber(h.ebitda)}</td>
                    <td className="px-4 py-2.5 text-right text-slate-400">{formatNumber(h.ev)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
