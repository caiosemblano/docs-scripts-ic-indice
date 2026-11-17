import { useCallback, useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  AlertCircle,
  BarChart3,
  Briefcase,
  Calendar,
  Database,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { fetchDatasetSummary, runBacktest, runMultiWindow } from './api';
import { AuditPanel } from './components/AuditPanel';
import { MultiWindowPanel } from './components/MultiWindowPanel';
import { PortfolioInspector } from './components/PortfolioInspector';
import {
  formatBRL,
  formatBRLCompact,
  formatDateBR,
  formatPct,
  STRATEGY_LABELS,
} from './formatters';
import {
  BacktestFormState,
  BacktestRunResponse,
  DatasetSummary,
  MultiWindowResponse,
  PerformanceSummary,
  RollingSubWindow,
  StrategyName,
} from './types';

function computeDefaultStartDate(minDateIso: string, maxDateIso: string, yearsBack = 20): string {
  const parts = maxDateIso.slice(0, 10).split('-').map(Number);
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) {
    return minDateIso;
  }
  const [y, m, d] = parts;
  const targetYear = Math.max(1, y - yearsBack);
  const maxDayInMonth = new Date(targetYear, m, 0).getDate();
  const safeDay = Math.min(d, maxDayInMonth);
  const candidate = `${String(targetYear).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(safeDay).padStart(2, '0')}`;
  return candidate < minDateIso ? minDateIso : candidate;
}

const INITIAL_FORM: BacktestFormState = {
  strategies: ['acquirers_multiple', 'magic_formula'],
  start_date: '2006-11-13',
  end_date: '',
  portfolio_size: 20,
  initial_capital: 10000,
  enable_monthly_contribution: true,
  monthly_contribution: 1000,
  contribution_mode: 'underweight',
  rebalance_frequency: 'annual',
  ebitda_mode: 'ltm',
  reporting_lag_days: 0,
  deduplicate_issuers: true,
  exclude_ebitda_12m_files: false,
  require_positive_ebitda: true,
  min_presence_63d: 10,
  risk_free_rate_annual: 0,
};

function StrategySummaryCard({
  strategy,
  summary,
}: {
  strategy: StrategyName;
  summary: PerformanceSummary;
}) {
  const isAM = strategy === 'acquirers_multiple';
  const accentText = isAM ? 'text-emerald-400' : 'text-sky-400';
  const accentBadge = isAM
    ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
    : 'bg-sky-500/15 text-sky-300 ring-sky-500/30';

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/75 p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`rounded-md px-2.5 py-1 text-xs font-semibold ring-1 ${accentBadge}`}>
          {STRATEGY_LABELS[strategy]}
        </span>
        <span className="text-xs text-slate-400">
          {formatDateBR(summary.start_date)} → {formatDateBR(summary.end_date)} (
          {summary.elapsed_years.toFixed(1)} anos)
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <div className="text-[11px] font-medium text-slate-400 uppercase">Patrimônio Final</div>
          <div className="mt-1 text-lg font-bold text-slate-100">
            {formatBRL(summary.final_equity)}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-400">
            Investido: {formatBRL(summary.total_invested)} ({summary.moic.toFixed(2)}x)
          </div>
        </div>

        <div>
          <div className="text-[11px] font-medium text-slate-400 uppercase">Lucro Líquido</div>
          <div
            className={`mt-1 text-lg font-bold ${
              summary.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {formatBRL(summary.net_profit)}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-400">
            {summary.contributions_count} aportes mensais
          </div>
        </div>

        <div>
          <div className="text-[11px] font-medium text-slate-400 uppercase">
            CAGR Cota / TIR (XIRR)
          </div>
          <div className={`mt-1 text-lg font-bold ${accentText}`}>
            {formatPct(summary.cagr_pct, 2, true)}{' '}
            <span className="text-xs font-normal text-slate-400">a.a.</span>
          </div>
          <div className="mt-0.5 text-[11px] text-slate-300">
            TIR: <span className="font-semibold">{formatPct(summary.xirr_pct, 2, true)}</span> · TWR:{' '}
            {formatPct(summary.twr_total_pct, 1, true)}
          </div>
        </div>

        <div>
          <div className="text-[11px] font-medium text-slate-400 uppercase">Risco & Giro</div>
          <div className="mt-1 text-lg font-bold text-rose-400">
            {formatPct(summary.max_drawdown_pct, 2)}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-400">
            Vol: {formatPct(summary.volatility_annual_pct, 1)} · {summary.rebalances_count} rebal.
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [form, setForm] = useState<BacktestFormState>(INITIAL_FORM);
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [runData, setRunData] = useState<BacktestRunResponse | null>(null);
  const [multiWindowData, setMultiWindowData] = useState<MultiWindowResponse | null>(null);

  const [loadingRun, setLoadingRun] = useState(false);
  const [loadingMulti, setLoadingMulti] = useState(false);
  const [refreshingDataset, setRefreshingDataset] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [chartTab, setChartTab] = useState<'equity' | 'twr' | 'drawdown'>('equity');
  const [mainTab, setMainTab] = useState<'multi_window' | 'portfolios' | 'audit'>('multi_window');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [inspectedSubWindow, setInspectedSubWindow] = useState<{
    horizonYears: number;
    sub: RollingSubWindow;
  } | null>(null);

  const executeSimulation = useCallback(async (targetForm: BacktestFormState) => {
    setError(null);
    setInspectedSubWindow(null);
    setLoadingRun(true);
    setLoadingMulti(true);

    try {
      const [singleRes, multiRes] = await Promise.all([
        runBacktest(targetForm),
        runMultiWindow(targetForm),
      ]);
      setRunData(singleRes);
      setMultiWindowData(multiRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro inesperado ao executar simulação.');
    } finally {
      setLoadingRun(false);
      setLoadingMulti(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingRun(true);
      setLoadingMulti(true);
      try {
        const summary = await fetchDatasetSummary(false);
        if (cancelled) return;
        setDataset(summary);
        const defaultStart = computeDefaultStartDate(summary.min_date, summary.max_date, 20);
        const initialWithDates: BacktestFormState = {
          ...INITIAL_FORM,
          start_date: defaultStart,
          end_date: '',
        };
        setForm(initialWithDates);
        await executeSimulation(initialWithDates);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Erro ao inicializar aplicação.');
          setLoadingRun(false);
          setLoadingMulti(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [executeSimulation]);

  const handleRefreshDataset = async () => {
    setRefreshingDataset(true);
    setError(null);
    try {
      const summary = await fetchDatasetSummary(true);
      setDataset(summary);
      await executeSimulation(form);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao recarregar base.');
    } finally {
      setRefreshingDataset(false);
    }
  };

  const toggleStrategy = (s: StrategyName) => {
    setForm((prev) => {
      const exists = prev.strategies.includes(s);
      if (exists && prev.strategies.length === 1) return prev;
      const next = exists ? prev.strategies.filter((x) => x !== s) : [...prev.strategies, s];
      return { ...prev, strategies: next };
    });
  };

  const handleInspectRollingSubWindow = (horizonYears: number, sub: RollingSubWindow) => {
    setError(null);
    setInspectedSubWindow({ horizonYears, sub });
    setLoadingRun(true);
    runBacktest(form, {
      start_date: sub.requested_start_date,
      end_date: sub.requested_end_date,
    })
      .then((res) => {
        setRunData(res);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingRun(false));
  };

  const handleRestoreBaseRange = () => {
    setError(null);
    setInspectedSubWindow(null);
    setLoadingRun(true);
    runBacktest(form)
      .then((res) => setRunData(res))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingRun(false));
  };

  const hasAM = Boolean(runData?.results.acquirers_multiple);
  const hasMF = Boolean(runData?.results.magic_formula);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/40">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-slate-100">
                IC Índice — Acquirer&apos;s Multiple &amp; Magic Formula
              </h1>
              <p className="text-xs text-slate-400">
                 Simulador Quantitativo de Carteiras, Janelas de Tempo (1 a 20 Anos) e Aportes Mensais
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {dataset && (
              <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-300">
                <Database className="h-3.5 w-3.5 text-emerald-400" />
                <span>
                  <strong>{dataset.active_tickers.toLocaleString('pt-BR')}</strong> ativos ·{' '}
                  {formatDateBR(dataset.min_date)} → {formatDateBR(dataset.max_date)}
                </span>
              </div>
            )}

            {dataset && dataset.ebitda_12m_count > 0 && (
              <button
                type="button"
                onClick={() => setMainTab('audit')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-300 ring-1 ring-amber-500/30 hover:bg-amber-500/25"
              >
                <AlertCircle className="h-3.5 w-3.5" />
                {dataset.ebitda_12m_count} arquivos EBITDA 12m detectados
              </button>
            )}

            <button
              type="button"
              onClick={handleRefreshDataset}
              disabled={refreshingDataset}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-800 disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshingDataset ? 'animate-spin' : ''}`} />
              Atualizar Base
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-6 px-6 py-6 lg:grid-cols-12">
        {/* Sidebar Controls */}
        <aside className="space-y-5 lg:col-span-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              executeSimulation(form);
            }}
            className="space-y-5 rounded-xl border border-slate-800 bg-slate-900/75 p-5"
          >
            {/* Estrategias */}
            <div>
              <label className="mb-2 block text-xs font-semibold tracking-wider text-slate-300 uppercase">
                Estratégias
              </label>
              <div className="grid grid-cols-1 gap-2">
                {(['acquirers_multiple', 'magic_formula'] as StrategyName[]).map((s) => {
                  const active = form.strategies.includes(s);
                  const isAM = s === 'acquirers_multiple';
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => toggleStrategy(s)}
                      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left text-xs font-medium transition ${
                        active
                          ? isAM
                            ? 'border-emerald-500/60 bg-emerald-500/15 text-emerald-200'
                            : 'border-sky-500/60 bg-sky-500/15 text-sky-200'
                          : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      <span>{STRATEGY_LABELS[s]}</span>
                      <span className="text-[10px] opacity-80">
                        {isAM ? 'EBITDA / EV' : 'EY + ROIC'}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Período Base da Simulação */}
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wider text-slate-300 uppercase">
                <Calendar className="h-3.5 w-3.5 text-emerald-400" />
                <span>Período da Simulação</span>
              </div>
              <div className="space-y-2.5 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                <div>
                  <label className="block text-[11px] text-slate-400">Data Inicial</label>
                  <input
                    type="date"
                    value={form.start_date}
                    min={dataset?.min_date}
                    max={dataset?.max_date}
                    onChange={(e) => setForm((prev) => ({ ...prev, start_date: e.target.value }))}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400">
                    Data Final (vazio = última da base)
                  </label>
                  <input
                    type="date"
                    value={form.end_date}
                    min={dataset?.min_date}
                    max={dataset?.max_date}
                    onChange={(e) => setForm((prev) => ({ ...prev, end_date: e.target.value }))}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
                <p className="text-[11px] leading-relaxed text-slate-500">
                  As janelas móveis anuais de <strong className="text-slate-300">1, 3, 5, 10, 15 e 20 anos</strong> são calculadas automaticamente dentro deste intervalo.
                </p>
              </div>
            </div>

            {/* Capital Inicial & Aportes Mensais */}
            <div className="space-y-3 border-t border-slate-800 pt-4">
              <div className="flex items-center gap-2 text-xs font-semibold tracking-wider text-slate-300 uppercase">
                <Wallet className="h-3.5 w-3.5 text-emerald-400" />
                <span>Capital &amp; Aportes Mensais</span>
              </div>

              <div>
                <label className="block text-xs text-slate-400">Capital Inicial (R$)</label>
                <input
                  type="number"
                  min={100}
                  step={500}
                  value={form.initial_capital}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      initial_capital: Math.max(1, Number(e.target.value)),
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm font-medium text-slate-100 focus:border-emerald-500 focus:outline-none"
                />
              </div>

              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
                <span className="text-xs font-medium text-slate-200">Habilitar Aportes Mensais</span>
                <input
                  type="checkbox"
                  checked={form.enable_monthly_contribution}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      enable_monthly_contribution: e.target.checked,
                    }))
                  }
                  className="h-4 w-4 accent-emerald-500"
                />
              </label>

              {form.enable_monthly_contribution && (
                <div className="space-y-2.5 rounded-lg border border-slate-800/80 bg-slate-950/50 p-3">
                  <div>
                    <label className="block text-xs text-slate-400">Valor do Aporte Mensal (R$)</label>
                    <input
                      type="number"
                      min={0}
                      step={100}
                      value={form.monthly_contribution}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          monthly_contribution: Math.max(0, Number(e.target.value)),
                        }))
                      }
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm font-medium text-slate-100 focus:border-emerald-500 focus:outline-none"
                    />
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {[250, 500, 1000, 2500, 5000].map((val) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => setForm((prev) => ({ ...prev, monthly_contribution: val }))}
                          className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
                        >
                          R$ {val.toLocaleString('pt-BR')}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] text-slate-400">Alocação do Aporte</label>
                    <select
                      value={form.contribution_mode}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          contribution_mode: e.target.value as BacktestFormState['contribution_mode'],
                        }))
                      }
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
                    >
                      <option value="underweight">
                        Reequilíbrio Inteligente (comprar descontados)
                      </option>
                      <option value="equal_current">
                        Pesos Iguais (1/N na carteira vigente)
                      </option>
                    </select>
                  </div>
                </div>
              )}
            </div>

            {/* Regras da Carteira */}
            <div className="space-y-3 border-t border-slate-800 pt-4">
              <div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Ativos na Carteira (Top N)</span>
                  <span className="font-bold text-emerald-400">{form.portfolio_size} ações</span>
                </div>
                <input
                  type="range"
                  min={5}
                  max={50}
                  step={1}
                  value={form.portfolio_size}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, portfolio_size: Number(e.target.value) }))
                  }
                  className="mt-1.5 w-full accent-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400">Frequência de Rebalanceamento</label>
                <select
                  value={form.rebalance_frequency}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      rebalance_frequency: e.target.value as BacktestFormState['rebalance_frequency'],
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none"
                >
                  <option value="annual">Anual (12 meses — Padrão)</option>
                  <option value="semiannual">Semestral (6 meses)</option>
                  <option value="quarterly">Trimestral (3 meses)</option>
                  <option value="monthly">Mensal (1 mês)</option>
                  <option value="buy_and_hold">Buy &amp; Hold (Sem rebalanceamento)</option>
                </select>
              </div>
            </div>

            {/* Filtros Avancados */}
            <div className="border-t border-slate-800 pt-3">
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="flex w-full items-center justify-between text-xs font-medium text-slate-400 hover:text-slate-200"
              >
                <span className="inline-flex items-center gap-1.5">
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  Filtros Quantitativos Avançados
                </span>
                <span>{showAdvanced ? '−' : '+'}</span>
              </button>

              {showAdvanced && (
                <div className="mt-3 space-y-2.5 rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs">
                  <label className="flex cursor-pointer items-center justify-between">
                    <span className="text-slate-300">1 ação por empresa (ON/PN/UNIT)</span>
                    <input
                      type="checkbox"
                      checked={form.deduplicate_issuers}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, deduplicate_issuers: e.target.checked }))
                      }
                      className="h-4 w-4 accent-emerald-500"
                    />
                  </label>

                  <label className="flex cursor-pointer items-center justify-between">
                    <span className="text-slate-300">Exigir EBITDA &gt; 0</span>
                    <input
                      type="checkbox"
                      checked={form.require_positive_ebitda}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, require_positive_ebitda: e.target.checked }))
                      }
                      className="h-4 w-4 accent-emerald-500"
                    />
                  </label>

                  <label className="flex cursor-pointer items-center justify-between">
                    <span className="text-slate-300">Ignorar arquivos EBITDA 12m</span>
                    <input
                      type="checkbox"
                      checked={form.exclude_ebitda_12m_files}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          exclude_ebitda_12m_files: e.target.checked,
                        }))
                      }
                      className="h-4 w-4 accent-emerald-500"
                    />
                  </label>

                  <div>
                    <label className="block text-[11px] text-slate-400">Cálculo do EBITDA</label>
                    <select
                      value={form.ebitda_mode}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          ebitda_mode: e.target.value as BacktestFormState['ebitda_mode'],
                        }))
                      }
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    >
                      <option value="ltm">LTM Anualizado (Soma últimos 4T)</option>
                      <option value="raw">Valor Bruto da Planilha (Trimestral)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] text-slate-400">
                      Defasagem de Divulgação CVM (dias)
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={180}
                      value={form.reporting_lag_days}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          reporting_lag_days: Math.max(0, Number(e.target.value)),
                        }))
                      }
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-[11px]">
                      <label className="text-slate-400">
                        Presença Mínima em Pregão (Liquidez)
                      </label>
                      <span className="font-semibold text-emerald-400">
                        {form.min_presence_63d === 0
                          ? 'Sem filtro (0/63)'
                          : `${form.min_presence_63d} de 63 pregões (${Math.round(
                              (form.min_presence_63d / 63) * 100
                            )}%)`}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={63}
                      step={1}
                      value={form.min_presence_63d}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          min_presence_63d: Number(e.target.value),
                        }))
                      }
                      className="mt-1.5 w-full accent-emerald-500"
                    />
                    <div className="mt-0.5 flex justify-between text-[10px] text-slate-500">
                      <span>0 pregões</span>
                      <span>63 pregões (~3 meses úteis)</span>
                    </div>
                    <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                      Unidade: <strong className="text-slate-400">nº de pregões com cotação válida</strong>{' '}
                      nos últimos 63 pregões reais da bolsa (não é volume financeiro em R$). Valores
                      muito altos (ex.: 60–63) descartam ações que ficaram sem negócio em um único dia
                      e podem reduzir os ativos elegíveis.
                    </p>
                  </div>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loadingRun}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-bold text-slate-950 shadow-lg shadow-emerald-500/15 transition hover:bg-emerald-400 disabled:opacity-50"
            >
              <Play className="h-4 w-4 fill-current" />
              {loadingRun ? 'Simulando...' : 'Executar Backtest'}
            </button>
          </form>
        </aside>

        {/* Main Workspace */}
        <main className="space-y-6 lg:col-span-9">
          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
              <div>{error}</div>
            </div>
          )}

          {inspectedSubWindow && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/40 bg-emerald-950/25 px-4 py-3 text-xs text-emerald-200">
              <div>
                <span className="font-semibold">
                  Inspecionando janela móvel de {inspectedSubWindow.horizonYears}{' '}
                  {inspectedSubWindow.horizonYears === 1 ? 'ano' : 'anos'} (#
                  {inspectedSubWindow.sub.index}):
                </span>{' '}
                {formatDateBR(inspectedSubWindow.sub.effective_start_date)} →{' '}
                {formatDateBR(inspectedSubWindow.sub.effective_end_date)}
              </div>
              <button
                type="button"
                onClick={handleRestoreBaseRange}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3 py-1.5 font-semibold text-emerald-200 ring-1 ring-emerald-500/40 transition hover:bg-emerald-500/30"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Voltar ao período completo ({formatDateBR(form.start_date)} →{' '}
                {formatDateBR(form.end_date || dataset?.max_date)})
              </button>
            </div>
          )}

          {/* Strategy Summary Cards */}
          {runData && (
            <div className="grid grid-cols-1 gap-4">
              {Object.entries(runData.results).map(([stratKey, res]) => (
                <StrategySummaryCard
                  key={stratKey}
                  strategy={stratKey as StrategyName}
                  summary={res.summary}
                />
              ))}
            </div>
          )}

          {/* Primary Interactive Chart */}
          {runData && runData.comparison_chart.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/75 p-5">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-100">
                    {chartTab === 'equity' && 'Evolução Patrimonial (R$) vs. Capital Aportado'}
                    {chartTab === 'twr' && 'Rentabilidade Acumulada da Cota (TWR %)'}
                    {chartTab === 'drawdown' && 'Drawdown Histórico (% abaixo do topo)'}
                  </h2>
                  <p className="text-xs text-slate-400">
                    {inspectedSubWindow
                      ? `Janela móvel selecionada (${inspectedSubWindow.horizonYears} ${
                          inspectedSubWindow.horizonYears === 1 ? 'Ano' : 'Anos'
                        }): ${formatDateBR(
                          inspectedSubWindow.sub.effective_start_date,
                        )} → ${formatDateBR(inspectedSubWindow.sub.effective_end_date)}`
                      : `Período base selecionado: ${formatDateBR(form.start_date)} → ${formatDateBR(
                          form.end_date || dataset?.max_date,
                        )}`}
                  </p>
                </div>

                <div className="flex rounded-lg border border-slate-800 bg-slate-950 p-1 text-xs">
                  <button
                    type="button"
                    onClick={() => setChartTab('equity')}
                    className={`rounded-md px-3 py-1.5 font-medium transition ${
                      chartTab === 'equity'
                        ? 'bg-slate-800 text-slate-100'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Patrimônio (R$)
                  </button>
                  <button
                    type="button"
                    onClick={() => setChartTab('twr')}
                    className={`rounded-md px-3 py-1.5 font-medium transition ${
                      chartTab === 'twr'
                        ? 'bg-slate-800 text-slate-100'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Cota TWR (%)
                  </button>
                  <button
                    type="button"
                    onClick={() => setChartTab('drawdown')}
                    className={`rounded-md px-3 py-1.5 font-medium transition ${
                      chartTab === 'drawdown'
                        ? 'bg-slate-800 text-slate-100'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Drawdown (%)
                  </button>
                </div>
              </div>

              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  {chartTab === 'equity' ? (
                    <AreaChart data={runData.comparison_chart}>
                      <defs>
                        <linearGradient id="gradAM" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.28} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                        </linearGradient>
                        <linearGradient id="gradMF" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.24} />
                          <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="date"
                        stroke="#94a3b8"
                        fontSize={11}
                        minTickGap={40}
                        tickFormatter={(d) => formatDateBR(d)}
                      />
                      <YAxis
                        stroke="#94a3b8"
                        fontSize={11}
                        tickFormatter={(v) => formatBRLCompact(v)}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#334155',
                          borderRadius: '0.5rem',
                          fontSize: '12px',
                        }}
                        labelFormatter={(label) => `Data: ${formatDateBR(String(label))}`}
                        formatter={(val: number, name: string) => [formatBRL(val), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px' }} />
                      <Area
                        type="monotone"
                        dataKey="invested"
                        name="Total Aportado"
                        stroke="#94a3b8"
                        strokeDasharray="5 5"
                        fill="none"
                        strokeWidth={1.8}
                      />
                      {hasAM && (
                        <Area
                          type="monotone"
                          dataKey="acquirers_equity"
                          name="The Acquirer's Multiple"
                          stroke="#10b981"
                          fill="url(#gradAM)"
                          strokeWidth={2.2}
                        />
                      )}
                      {hasMF && (
                        <Area
                          type="monotone"
                          dataKey="magic_equity"
                          name="The Magic Formula"
                          stroke="#38bdf8"
                          fill="url(#gradMF)"
                          strokeWidth={2.2}
                        />
                      )}
                    </AreaChart>
                  ) : chartTab === 'twr' ? (
                    <LineChart data={runData.comparison_chart}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="date"
                        stroke="#94a3b8"
                        fontSize={11}
                        minTickGap={40}
                        tickFormatter={(d) => formatDateBR(d)}
                      />
                      <YAxis stroke="#94a3b8" fontSize={11} tickFormatter={(v) => `${v}%`} />
                      <ReferenceLine y={0} stroke="#475569" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#334155',
                          borderRadius: '0.5rem',
                          fontSize: '12px',
                        }}
                        labelFormatter={(label) => `Data: ${formatDateBR(String(label))}`}
                        formatter={(val: number, name: string) => [formatPct(val, 2, true), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px' }} />
                      {hasAM && (
                        <Line
                          type="monotone"
                          dataKey="acquirers_twr_pct"
                          name="Acquirer's Multiple (TWR %)"
                          stroke="#10b981"
                          dot={false}
                          strokeWidth={2}
                        />
                      )}
                      {hasMF && (
                        <Line
                          type="monotone"
                          dataKey="magic_twr_pct"
                          name="Magic Formula (TWR %)"
                          stroke="#38bdf8"
                          dot={false}
                          strokeWidth={2}
                        />
                      )}
                    </LineChart>
                  ) : (
                    <AreaChart data={runData.comparison_chart}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="date"
                        stroke="#94a3b8"
                        fontSize={11}
                        minTickGap={40}
                        tickFormatter={(d) => formatDateBR(d)}
                      />
                      <YAxis stroke="#94a3b8" fontSize={11} tickFormatter={(v) => `${v}%`} />
                      <ReferenceLine y={0} stroke="#475569" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#334155',
                          borderRadius: '0.5rem',
                          fontSize: '12px',
                        }}
                        labelFormatter={(label) => `Data: ${formatDateBR(String(label))}`}
                        formatter={(val: number, name: string) => [formatPct(val, 2), name]}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px' }} />
                      {hasAM && (
                        <Area
                          type="monotone"
                          dataKey="acquirers_drawdown_pct"
                          name="Drawdown Acquirer's"
                          stroke="#10b981"
                          fill="#10b981"
                          fillOpacity={0.14}
                          strokeWidth={1.8}
                        />
                      )}
                      {hasMF && (
                        <Area
                          type="monotone"
                          dataKey="magic_drawdown_pct"
                          name="Drawdown Magic Formula"
                          stroke="#38bdf8"
                          fill="#38bdf8"
                          fillOpacity={0.14}
                          strokeWidth={1.8}
                        />
                      )}
                    </AreaChart>
                  )}
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Bottom Navigation Tabs */}
          <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-3">
            <button
              type="button"
              onClick={() => setMainTab('multi_window')}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                mainTab === 'multi_window'
                  ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              <BarChart3 className="h-4 w-4" />
              Janelas Móveis Anuais (1, 3, 5, 10, 15 e 20 Anos)
            </button>

            <button
              type="button"
              onClick={() => setMainTab('portfolios')}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                mainTab === 'portfolios'
                  ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Briefcase className="h-4 w-4" />
              Carteiras &amp; Rebalanceamentos
            </button>

            <button
              type="button"
              onClick={() => setMainTab('audit')}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                mainTab === 'audit'
                  ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              <ShieldCheck className="h-4 w-4" />
              Auditoria da Base Economatica
              {dataset && dataset.ebitda_12m_count > 0 && (
                <span className="rounded-full bg-amber-500/25 px-2 py-0.5 text-[10px] text-amber-300">
                  {dataset.ebitda_12m_count}
                </span>
              )}
            </button>
          </div>

          {mainTab === 'multi_window' && (
            <MultiWindowPanel
              data={multiWindowData}
              loading={loadingMulti}
              inspectedSubWindow={inspectedSubWindow}
              onInspectSubWindow={handleInspectRollingSubWindow}
            />
          )}

          {mainTab === 'portfolios' && runData && (
            <PortfolioInspector results={runData.results} />
          )}

          {mainTab === 'audit' && <AuditPanel />}

          {!runData && loadingRun && (
            <div className="flex items-center justify-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-12 text-sm text-slate-300">
              <Activity className="h-5 w-5 animate-pulse text-emerald-400" />
              Processando séries históricas e simulando carteiras...
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
