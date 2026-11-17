import { ReactNode, useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowUpRight,
  Award,
  Eye,
  Layers,
  LineChart as LineChartIcon,
  ShieldAlert,
  TrendingUp,
  X,
} from 'lucide-react';
import { formatBRL, formatBRLCompact, formatDateBR, formatPct } from '../formatters';
import { MultiWindowResponse, RollingSubWindow, WindowComparisonEntry } from '../types';

interface Props {
  data: MultiWindowResponse | null;
  loading: boolean;
  inspectedSubWindow: { horizonYears: number; sub: RollingSubWindow } | null;
  onInspectSubWindow: (horizonYears: number, sub: RollingSubWindow) => void;
}

export function MultiWindowPanel({
  data,
  loading,
  inspectedSubWindow,
  onInspectSubWindow,
}: Props) {
  const [selectedHorizonYears, setSelectedHorizonYears] = useState<number | null>(null);
  const [detailChartMode, setDetailChartMode] = useState<'cagr' | 'equity'>('cagr');

  useEffect(() => {
    if (!data || selectedHorizonYears === null) return;
    const match = data.windows.find((w) => w.window_years === selectedHorizonYears);
    if (!match || match.window_count === 0) {
      setSelectedHorizonYears(null);
    }
  }, [data, selectedHorizonYears]);

  useEffect(() => {
    if (selectedHorizonYears === null) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedHorizonYears(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedHorizonYears]);

  if (loading && !data) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
        Calculando janelas móveis anuais de 1, 3, 5, 10, 15 e 20 anos...
      </div>
    );
  }

  if (!data || data.windows.length === 0) {
    return null;
  }

  const validHorizons = data.windows.filter((w) => w.window_count > 0);
  const chartData = validHorizons.map((w) => {
    const am = w.aggregates.acquirers_multiple;
    const mf = w.aggregates.magic_formula;
    return {
      label: `${w.window_years}A`,
      years: w.window_years,
      windowCount: w.window_count,
      am_cagr: am?.mean_cagr_pct ?? null,
      am_median_cagr: am?.median_cagr_pct ?? null,
      mf_cagr: mf?.mean_cagr_pct ?? null,
      mf_median_cagr: mf?.median_cagr_pct ?? null,
      am_equity: am?.mean_final_equity ?? null,
      mf_equity: mf?.mean_final_equity ?? null,
      invested: am?.mean_total_invested ?? mf?.mean_total_invested ?? null,
    };
  });

  const hasAM = data.windows.some((w) => Boolean(w.aggregates.acquirers_multiple));
  const hasMF = data.windows.some((w) => Boolean(w.aggregates.magic_formula));
  const baseRangeRef = data.windows[0];

  const activeModalEntry: WindowComparisonEntry | undefined =
    selectedHorizonYears !== null
      ? data.windows.find((w) => w.window_years === selectedHorizonYears && w.window_count > 0)
      : undefined;

  return (
    <div className="space-y-6">
      {/* Top Overview Charts across Rolling Horizons */}
      {chartData.length > 0 && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
            <h3 className="mb-1 text-sm font-semibold text-slate-200">
              CAGR Médio nas Janelas Móveis Anuais (% a.a.)
            </h3>
            <p className="mb-4 text-xs text-slate-400">
              Rentabilidade anualizada média da cota (TWR) em todas as janelas móveis de cada prazo
            </p>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="label" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(v) => `${v}%`} />
                  <ReferenceLine y={0} stroke="#475569" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#334155',
                      borderRadius: '0.5rem',
                      fontSize: '12px',
                    }}
                    labelFormatter={(lbl, payload) => {
                      const cnt = payload?.[0]?.payload?.windowCount;
                      return cnt ? `Horizonte ${lbl} (${cnt} janelas móveis)` : `Horizonte ${lbl}`;
                    }}
                    formatter={(val: number, name: string) => [formatPct(val, 2, true), name]}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  {hasAM && (
                    <Bar
                      dataKey="am_cagr"
                      name="Acquirer's Multiple (CAGR Médio)"
                      fill="#10b981"
                      radius={[4, 4, 0, 0]}
                    />
                  )}
                  {hasMF && (
                    <Bar
                      dataKey="mf_cagr"
                      name="Magic Formula (CAGR Médio)"
                      fill="#38bdf8"
                      radius={[4, 4, 0, 0]}
                    />
                  )}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
            <h3 className="mb-1 text-sm font-semibold text-slate-200">
              Patrimônio Final Médio vs. Total Aportado Médio por Prazo
            </h3>
            <p className="mb-4 text-xs text-slate-400">
              Média do patrimônio acumulado ao final de cada janela móvel anual
            </p>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="label" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(v) => formatBRLCompact(v)} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#334155',
                      borderRadius: '0.5rem',
                      fontSize: '12px',
                    }}
                    labelFormatter={(lbl, payload) => {
                      const cnt = payload?.[0]?.payload?.windowCount;
                      return cnt ? `Horizonte ${lbl} (${cnt} janelas móveis)` : `Horizonte ${lbl}`;
                    }}
                    formatter={(val: number, name: string) => [formatBRL(val), name]}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Bar
                    dataKey="invested"
                    name="Total Aportado Médio"
                    fill="#64748b"
                    radius={[4, 4, 0, 0]}
                  />
                  {hasAM && (
                    <Bar
                      dataKey="am_equity"
                      name="Patrimônio Médio Acquirer's"
                      fill="#10b981"
                      radius={[4, 4, 0, 0]}
                    />
                  )}
                  {hasMF && (
                    <Bar
                      dataKey="mf_equity"
                      name="Patrimônio Médio Magic Formula"
                      fill="#38bdf8"
                      radius={[4, 4, 0, 0]}
                    />
                  )}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Rolling Window Summary Matrix */}
      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-emerald-400" />
            <div>
              <h3 className="text-sm font-semibold text-slate-100">
                Matriz Estatística de Janelas Móveis Anuais (1, 3, 5, 10, 15 e 20 Anos)
              </h3>
              {baseRangeRef && (
                <p className="text-[11px] text-slate-400">
                  Recorte base: {formatDateBR(baseRangeRef.base_start_date)} →{' '}
                  {formatDateBR(baseRangeRef.base_end_date)} · Estatísticas consolidadas de todas as
                  janelas móveis anuais
                </p>
              )}
            </div>
          </div>
          <span className="text-xs text-slate-400">
            Clique em <strong className="text-slate-200">Ver</strong> para inspecionar cada janela
            anual individualmente
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950/60 text-[11px] text-slate-400 uppercase">
              <tr>
                <th className="px-4 py-3">Horizonte</th>
                <th className="px-4 py-3">Janelas Móveis</th>
                <th className="px-4 py-3 text-right">Aportado Médio</th>
                {hasAM && (
                  <>
                    <th className="px-4 py-3 text-right text-emerald-400">Patrimônio Médio AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">CAGR Médio / Med. AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">Faixa CAGR AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">Consistência &amp; Risco AM</th>
                  </>
                )}
                {hasMF && (
                  <>
                    <th className="px-4 py-3 text-right text-sky-400">Patrimônio Médio MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">CAGR Médio / Med. MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">Faixa CAGR MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">Consistência &amp; Risco MF</th>
                  </>
                )}
                <th className="px-4 py-3 text-center">Janelas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {data.windows.map((w) => {
                const am = w.aggregates.acquirers_multiple;
                const mf = w.aggregates.magic_formula;
                const refAgg = am ?? mf;
                const hasWindows = w.window_count > 0 && Boolean(refAgg);
                const isSelected = selectedHorizonYears === w.window_years;

                if (!hasWindows) {
                  const totalCols = 4 + (hasAM ? 4 : 0) + (hasMF ? 4 : 0);
                  return (
                    <tr key={w.window_years} className="bg-slate-950/30 text-slate-500">
                      <td className="px-4 py-3.5 font-semibold text-slate-400">
                        {w.window_years} {w.window_years === 1 ? 'Ano' : 'Anos'}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="rounded bg-slate-800/80 px-2 py-0.5 text-[11px] text-slate-400">
                          0 janelas
                        </span>
                      </td>
                      <td colSpan={totalCols - 3} className="px-4 py-3.5 text-slate-500">
                        {w.error ??
                          `O intervalo selecionado não comporta janelas completas de ${w.window_years} anos.`}
                      </td>
                      <td className="px-4 py-3.5 text-center text-slate-600">—</td>
                    </tr>
                  );
                }

                const firstWin = w.rolling_windows[0];
                const lastWin = w.rolling_windows[w.rolling_windows.length - 1];

                return (
                  <tr
                    key={w.window_years}
                    onClick={() => setSelectedHorizonYears(w.window_years)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-emerald-950/30' : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <td className="px-4 py-3.5 font-semibold whitespace-nowrap text-slate-100">
                      {w.window_years} {w.window_years === 1 ? 'Ano' : 'Anos'}
                    </td>

                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-300 ring-1 ring-emerald-500/30">
                        {w.window_count} {w.window_count === 1 ? 'janela' : 'janelas'}
                      </div>
                      {firstWin && lastWin && (
                        <div className="mt-1 text-[11px] text-slate-400">
                          {w.window_count === 1
                            ? firstWin.label
                            : `${firstWin.label.split(' → ')[0]} → ${lastWin.label.split(' → ')[1]}`}
                        </div>
                      )}
                    </td>

                    <td className="px-4 py-3.5 text-right font-medium whitespace-nowrap text-slate-300">
                      <div>{formatBRL(refAgg?.mean_total_invested)}</div>
                      <div className="mt-0.5 text-[10px] text-slate-500">média / janela</div>
                    </td>

                    {hasAM && (
                      <>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div className="font-semibold text-slate-100">
                            {formatBRL(am?.mean_final_equity)}
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-400">
                            Med: {formatBRLCompact(am?.median_final_equity)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div
                            className={`font-semibold ${
                              (am?.mean_cagr_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {formatPct(am?.mean_cagr_pct, 2, true)}
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-400">
                            Med: {formatPct(am?.median_cagr_pct, 2, true)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div className="text-[11px] font-medium text-slate-200">
                            <span
                              className={
                                (am?.min_cagr_pct ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-400'
                              }
                            >
                              {formatPct(am?.min_cagr_pct, 1, true)}
                            </span>{' '}
                            <span className="text-slate-500">→</span>{' '}
                            <span className="text-emerald-400">
                              {formatPct(am?.max_cagr_pct, 1, true)}
                            </span>
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-500">
                            TIR méd: {formatPct(am?.mean_xirr_pct, 1, true)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div className="font-medium text-emerald-300">
                            {formatPct(am?.win_rate_pct, 0)} pos. ({am?.positive_cagr_count}/
                            {am?.window_count})
                          </div>
                          <div className="mt-0.5 text-[10px] text-rose-400">
                            Pior DD: {formatPct(am?.worst_max_drawdown_pct, 1)}
                          </div>
                        </td>
                      </>
                    )}

                    {hasMF && (
                      <>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div className="font-semibold text-slate-100">
                            {formatBRL(mf?.mean_final_equity)}
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-400">
                            Med: {formatBRLCompact(mf?.median_final_equity)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div
                            className={`font-semibold ${
                              (mf?.mean_cagr_pct ?? 0) >= 0 ? 'text-sky-400' : 'text-rose-400'
                            }`}
                          >
                            {formatPct(mf?.mean_cagr_pct, 2, true)}
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-400">
                            Med: {formatPct(mf?.median_cagr_pct, 2, true)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div className="text-[11px] font-medium text-slate-200">
                            <span
                              className={
                                (mf?.min_cagr_pct ?? 0) >= 0 ? 'text-sky-300' : 'text-rose-400'
                              }
                            >
                              {formatPct(mf?.min_cagr_pct, 1, true)}
                            </span>{' '}
                            <span className="text-slate-500">→</span>{' '}
                            <span className="text-sky-400">
                              {formatPct(mf?.max_cagr_pct, 1, true)}
                            </span>
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-500">
                            TIR méd: {formatPct(mf?.mean_xirr_pct, 1, true)}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <div className="font-medium text-sky-300">
                            {formatPct(mf?.win_rate_pct, 0)} pos. ({mf?.positive_cagr_count}/
                            {mf?.window_count})
                          </div>
                          <div className="mt-0.5 text-[10px] text-rose-400">
                            Pior DD: {formatPct(mf?.worst_max_drawdown_pct, 1)}
                          </div>
                        </td>
                      </>
                    )}

                    <td className="px-4 py-3.5 text-center whitespace-nowrap">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedHorizonYears(w.window_years);
                        }}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold text-emerald-300 ring-1 ring-emerald-500/40 transition hover:bg-emerald-500/25"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        Ver ({w.window_count})
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal / Overlay for Detailed Annual Rolling Windows of Selected Horizon */}
      {activeModalEntry && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setSelectedHorizonYears(null)}
        >
          <div
            className="flex max-h-[90vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 bg-slate-950/80 px-6 py-4">
              <div>
                <div className="flex items-center gap-2.5">
                  <span className="rounded-lg bg-emerald-500/20 px-2.5 py-1 text-xs font-bold text-emerald-300 ring-1 ring-emerald-500/40">
                    {activeModalEntry.window_years}{' '}
                    {activeModalEntry.window_years === 1 ? 'Ano' : 'Anos'}
                  </span>
                  <h3 className="text-base font-bold text-slate-100">
                    Todas as Janelas Móveis Anuais ({activeModalEntry.window_count}{' '}
                    {activeModalEntry.window_count === 1 ? 'janela' : 'janelas'})
                  </h3>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Período base analisado: {formatDateBR(activeModalEntry.base_start_date)} →{' '}
                  {formatDateBR(activeModalEntry.base_end_date)} · Deslocamento anual de entrada
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-1">
                  {data.windows.map((hw) => {
                    const disabled = hw.window_count === 0;
                    const active = hw.window_years === activeModalEntry.window_years;
                    return (
                      <button
                        key={hw.window_years}
                        type="button"
                        disabled={disabled}
                        onClick={() => setSelectedHorizonYears(hw.window_years)}
                        className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                          active
                            ? 'bg-emerald-500 text-slate-950'
                            : disabled
                              ? 'cursor-not-allowed text-slate-600'
                              : 'text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        {hw.window_years}A ({hw.window_count})
                      </button>
                    );
                  })}
                </div>

                <button
                  type="button"
                  onClick={() => setSelectedHorizonYears(null)}
                  className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-slate-300 transition hover:bg-slate-700 hover:text-white"
                  title="Fechar (Esc)"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Modal Scrollable Body */}
            <div className="flex-1 space-y-6 overflow-y-auto p-6">
              <RollingHorizonDetailContent
                entry={activeModalEntry}
                hasAM={hasAM}
                hasMF={hasMF}
                chartMode={detailChartMode}
                onChangeChartMode={setDetailChartMode}
                inspectedSubWindow={inspectedSubWindow}
                onSelectSubWindow={(sub) => {
                  onInspectSubWindow(activeModalEntry.window_years, sub);
                  setSelectedHorizonYears(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RollingHorizonDetailContent({
  entry,
  hasAM,
  hasMF,
  chartMode,
  onChangeChartMode,
  inspectedSubWindow,
  onSelectSubWindow,
}: {
  entry: WindowComparisonEntry;
  hasAM: boolean;
  hasMF: boolean;
  chartMode: 'cagr' | 'equity';
  onChangeChartMode: (m: 'cagr' | 'equity') => void;
  inspectedSubWindow: { horizonYears: number; sub: RollingSubWindow } | null;
  onSelectSubWindow: (sub: RollingSubWindow) => void;
}) {
  const amAgg = entry.aggregates.acquirers_multiple;
  const mfAgg = entry.aggregates.magic_formula;
  const primaryAgg = amAgg ?? mfAgg;

  const rollingChartData = entry.rolling_windows.map((rw) => {
    const am = rw.strategies.acquirers_multiple;
    const mf = rw.strategies.magic_formula;
    return {
      label: rw.label,
      fullPeriod: `${formatDateBR(rw.effective_start_date)} → ${formatDateBR(rw.effective_end_date)}`,
      invested: am?.total_invested ?? mf?.total_invested ?? null,
      am_cagr: am?.cagr_pct ?? null,
      mf_cagr: mf?.cagr_pct ?? null,
      am_equity: am?.final_equity ?? null,
      mf_equity: mf?.final_equity ?? null,
    };
  });

  return (
    <div className="space-y-6">
      {/* KPI Highlight Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-400 uppercase">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
            <span>CAGR Médio / Mediano</span>
          </div>
          {amAgg && (
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-xs text-slate-400">Acquirer&apos;s:</span>
              <span className="text-sm font-bold text-emerald-400">
                {formatPct(amAgg.mean_cagr_pct, 2, true)}{' '}
                <span className="text-[11px] font-normal text-slate-400">
                  (Med {formatPct(amAgg.median_cagr_pct, 1, true)})
                </span>
              </span>
            </div>
          )}
          {mfAgg && (
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xs text-slate-400">Magic Formula:</span>
              <span className="text-sm font-bold text-sky-400">
                {formatPct(mfAgg.mean_cagr_pct, 2, true)}{' '}
                <span className="text-[11px] font-normal text-slate-400">
                  (Med {formatPct(mfAgg.median_cagr_pct, 1, true)})
                </span>
              </span>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-400 uppercase">
            <Award className="h-3.5 w-3.5 text-emerald-400" />
            <span>Melhor Janela de {entry.window_years}A</span>
          </div>
          {amAgg && (
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-xs text-slate-400">AM ({amAgg.best_window_label}):</span>
              <span className="text-sm font-bold text-emerald-400">
                {formatPct(amAgg.max_cagr_pct, 2, true)}
              </span>
            </div>
          )}
          {mfAgg && (
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xs text-slate-400">MF ({mfAgg.best_window_label}):</span>
              <span className="text-sm font-bold text-sky-400">
                {formatPct(mfAgg.max_cagr_pct, 2, true)}
              </span>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-400 uppercase">
            <ShieldAlert className="h-3.5 w-3.5 text-rose-400" />
            <span>Pior Janela de {entry.window_years}A</span>
          </div>
          {amAgg && (
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-xs text-slate-400">AM ({amAgg.worst_window_label}):</span>
              <span
                className={`text-sm font-bold ${
                  amAgg.min_cagr_pct >= 0 ? 'text-emerald-300' : 'text-rose-400'
                }`}
              >
                {formatPct(amAgg.min_cagr_pct, 2, true)}
              </span>
            </div>
          )}
          {mfAgg && (
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-xs text-slate-400">MF ({mfAgg.worst_window_label}):</span>
              <span
                className={`text-sm font-bold ${
                  mfAgg.min_cagr_pct >= 0 ? 'text-sky-300' : 'text-rose-400'
                }`}
              >
                {formatPct(mfAgg.min_cagr_pct, 2, true)}
              </span>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-400 uppercase">
            <LineChartIcon className="h-3.5 w-3.5 text-amber-400" />
            <span>
              {hasAM && hasMF ? 'Disputa Direta (AM vs. MF)' : 'Taxa de Janelas Positivas'}
            </span>
          </div>
          {hasAM && hasMF && amAgg && mfAgg ? (
            <>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-xs text-slate-400">Vitórias Acquirer&apos;s:</span>
                <span className="text-sm font-bold text-emerald-400">
                  {amAgg.beat_other_count}/{entry.window_count} (
                  {formatPct(amAgg.beat_other_pct, 1)})
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="text-xs text-slate-400">Vitórias Magic Formula:</span>
                <span className="text-sm font-bold text-sky-400">
                  {mfAgg.beat_other_count}/{entry.window_count} (
                  {formatPct(mfAgg.beat_other_pct, 1)})
                </span>
              </div>
            </>
          ) : primaryAgg ? (
            <div className="mt-2">
              <div className="text-lg font-bold text-emerald-400">
                {formatPct(primaryAgg.win_rate_pct, 1)} positivas
              </div>
              <div className="text-xs text-slate-400">
                {primaryAgg.positive_cagr_count} de {primaryAgg.window_count} janelas com CAGR &gt;
                0%
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Chronological Rolling Window Bar Chart */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-100">
              {chartMode === 'cagr'
                ? `CAGR (% a.a.) em Cada Janela Móvel de ${entry.window_years} ${
                    entry.window_years === 1 ? 'Ano' : 'Anos'
                  }`
                : `Patrimônio Final Acumulado (R$) em Cada Janela de ${entry.window_years} ${
                    entry.window_years === 1 ? 'Ano' : 'Anos'
                  }`}
            </h4>
            <p className="text-xs text-slate-400">
              Comparação cronológica janela a janela conforme o ano de início do investimento
            </p>
          </div>

          <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-1 text-xs">
            <button
              type="button"
              onClick={() => onChangeChartMode('cagr')}
              className={`rounded-md px-3 py-1 font-medium transition ${
                chartMode === 'cagr'
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              CAGR (% a.a.)
            </button>
            <button
              type="button"
              onClick={() => onChangeChartMode('equity')}
              className={`rounded-md px-3 py-1 font-medium transition ${
                chartMode === 'equity'
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Patrimônio Final (R$)
            </button>
          </div>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rollingChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="label"
                stroke="#94a3b8"
                fontSize={11}
                interval={entry.rolling_windows.length > 14 ? 1 : 0}
                angle={entry.rolling_windows.length > 8 ? -25 : 0}
                textAnchor={entry.rolling_windows.length > 8 ? 'end' : 'middle'}
                height={entry.rolling_windows.length > 8 ? 52 : 30}
              />
              <YAxis
                stroke="#94a3b8"
                fontSize={11}
                tickFormatter={(v) => (chartMode === 'cagr' ? `${v}%` : formatBRLCompact(v))}
              />
              <ReferenceLine y={0} stroke="#475569" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0f172a',
                  borderColor: '#334155',
                  borderRadius: '0.5rem',
                  fontSize: '12px',
                }}
                labelFormatter={(lbl, payload) => {
                  const full = payload?.[0]?.payload?.fullPeriod;
                  return full ? `Janela ${lbl} (${full})` : `Janela ${lbl}`;
                }}
                formatter={(val: number, name: string) =>
                  chartMode === 'cagr' ? [formatPct(val, 2, true), name] : [formatBRL(val), name]
                }
              />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {chartMode === 'equity' && (
                <Bar
                  dataKey="invested"
                  name="Total Aportado"
                  fill="#64748b"
                  radius={[3, 3, 0, 0]}
                />
              )}
              {hasAM && (
                <Bar
                  dataKey={chartMode === 'cagr' ? 'am_cagr' : 'am_equity'}
                  name={
                    chartMode === 'cagr'
                      ? "Acquirer's Multiple (CAGR)"
                      : "Patrimônio Acquirer's"
                  }
                  fill="#10b981"
                  radius={[3, 3, 0, 0]}
                />
              )}
              {hasMF && (
                <Bar
                  dataKey={chartMode === 'cagr' ? 'mf_cagr' : 'mf_equity'}
                  name={chartMode === 'cagr' ? 'Magic Formula (CAGR)' : 'Patrimônio Magic Formula'}
                  fill="#38bdf8"
                  radius={[3, 3, 0, 0]}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Individual Rolling Windows Table */}
      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-5 py-3.5">
          <h4 className="text-xs font-semibold tracking-wider text-slate-200 uppercase">
            Listagem Individual das {entry.window_count} Janelas de {entry.window_years}{' '}
            {entry.window_years === 1 ? 'Ano' : 'Anos'}
          </h4>
          <span className="text-xs text-slate-400">
            Clique em <strong className="text-slate-200">Simular Curva</strong> para carregar a
            curva diária e as carteiras da janela no painel principal
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-900/90 text-[11px] text-slate-400 uppercase">
              <tr>
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Janela Anual</th>
                <th className="px-4 py-3">Datas Efetivas</th>
                <th className="px-4 py-3 text-right">Total Aportado</th>
                {hasAM && (
                  <>
                    <th className="px-4 py-3 text-right text-emerald-400">Patrimônio AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">CAGR AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">TIR AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">Max DD AM</th>
                  </>
                )}
                {hasMF && (
                  <>
                    <th className="px-4 py-3 text-right text-sky-400">Patrimônio MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">CAGR MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">TIR MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">Max DD MF</th>
                  </>
                )}
                {hasAM && hasMF && <th className="px-4 py-3 text-center">Vencedora</th>}
                <th className="px-4 py-3 text-center">Curva &amp; Carteira</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {entry.rolling_windows.map((rw) => {
                const am = rw.strategies.acquirers_multiple;
                const mf = rw.strategies.magic_formula;
                const refStrat = am ?? mf;
                const isInspected =
                  inspectedSubWindow?.horizonYears === entry.window_years &&
                  inspectedSubWindow?.sub.index === rw.index;

                let winnerBadge: ReactNode = null;
                if (hasAM && hasMF && am && mf) {
                  if (am.cagr_pct > mf.cagr_pct) {
                    winnerBadge = (
                      <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                        AM +{formatPct(am.cagr_pct - mf.cagr_pct, 1)}
                      </span>
                    );
                  } else if (mf.cagr_pct > am.cagr_pct) {
                    winnerBadge = (
                      <span className="rounded bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold text-sky-300">
                        MF +{formatPct(mf.cagr_pct - am.cagr_pct, 1)}
                      </span>
                    );
                  } else {
                    winnerBadge = <span className="text-[10px] text-slate-400">Empate</span>;
                  }
                }

                return (
                  <tr
                    key={rw.index}
                    className={`transition-colors ${
                      isInspected ? 'bg-emerald-950/35' : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <td className="px-4 py-3 font-mono text-slate-500">#{rw.index}</td>
                    <td className="px-4 py-3 font-semibold whitespace-nowrap text-slate-100">
                      {rw.label}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-400">
                      {formatDateBR(rw.effective_start_date)} →{' '}
                      {formatDateBR(rw.effective_end_date)}
                    </td>
                    <td className="px-4 py-3 text-right font-medium whitespace-nowrap text-slate-300">
                      {formatBRL(refStrat?.total_invested)}
                    </td>

                    {hasAM && (
                      <>
                        <td className="px-4 py-3 text-right font-semibold whitespace-nowrap text-slate-100">
                          {formatBRL(am?.final_equity)}
                        </td>
                        <td
                          className={`px-4 py-3 text-right font-semibold whitespace-nowrap ${
                            (am?.cagr_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(am?.cagr_pct, 2, true)}
                        </td>
                        <td
                          className={`px-4 py-3 text-right whitespace-nowrap ${
                            (am?.xirr_pct ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(am?.xirr_pct, 2, true)}
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap text-rose-400">
                          {formatPct(am?.max_drawdown_pct, 2)}
                        </td>
                      </>
                    )}

                    {hasMF && (
                      <>
                        <td className="px-4 py-3 text-right font-semibold whitespace-nowrap text-slate-100">
                          {formatBRL(mf?.final_equity)}
                        </td>
                        <td
                          className={`px-4 py-3 text-right font-semibold whitespace-nowrap ${
                            (mf?.cagr_pct ?? 0) >= 0 ? 'text-sky-400' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(mf?.cagr_pct, 2, true)}
                        </td>
                        <td
                          className={`px-4 py-3 text-right whitespace-nowrap ${
                            (mf?.xirr_pct ?? 0) >= 0 ? 'text-sky-300' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(mf?.xirr_pct, 2, true)}
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap text-rose-400">
                          {formatPct(mf?.max_drawdown_pct, 2)}
                        </td>
                      </>
                    )}

                    {hasAM && hasMF && <td className="px-4 py-3 text-center">{winnerBadge}</td>}

                    <td className="px-4 py-3 text-center whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => onSelectSubWindow(rw)}
                        className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-200 transition hover:bg-emerald-500 hover:text-slate-950"
                      >
                        Simular Curva <ArrowUpRight className="h-3 w-3" />
                      </button>
                    </td>
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
