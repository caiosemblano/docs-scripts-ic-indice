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
import { ArrowUpRight, Layers } from 'lucide-react';
import { formatBRL, formatBRLCompact, formatDateBR, formatPct } from '../formatters';
import { MultiWindowResponse } from '../types';

interface Props {
  data: MultiWindowResponse | null;
  loading: boolean;
  activeWindowYears: number | null;
  onSelectWindow: (years: number) => void;
}

export function MultiWindowPanel({ data, loading, activeWindowYears, onSelectWindow }: Props) {
  if (loading && !data) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
        Calculando janelas de 1, 3, 5, 10, 15 e 20 anos...
      </div>
    );
  }

  if (!data || data.windows.length === 0) {
    return null;
  }

  const chartData = data.windows.map((w) => {
    const am = w.strategies.acquirers_multiple;
    const mf = w.strategies.magic_formula;
    return {
      label: `${w.window_years}A`,
      years: w.window_years,
      am_cagr: am?.cagr_pct ?? null,
      mf_cagr: mf?.cagr_pct ?? null,
      am_xirr: am?.xirr_pct ?? null,
      mf_xirr: mf?.xirr_pct ?? null,
      am_equity: am?.final_equity ?? null,
      mf_equity: mf?.final_equity ?? null,
      invested: am?.total_invested ?? mf?.total_invested ?? null,
    };
  });

  const hasAM = data.windows.some((w) => Boolean(w.strategies.acquirers_multiple));
  const hasMF = data.windows.some((w) => Boolean(w.strategies.magic_formula));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
          <h3 className="mb-1 text-sm font-semibold text-slate-200">
            CAGR Anualizado da Cota (TWR % a.a.) por Janela
          </h3>
          <p className="mb-4 text-xs text-slate-400">
            Rentabilidade anual composta pura da estratégia em 1, 3, 5, 10, 15 e 20 anos
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
                  formatter={(val: number, name: string) => [formatPct(val, 2, true), name]}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                {hasAM && (
                  <Bar
                    dataKey="am_cagr"
                    name="Acquirer's Multiple (CAGR)"
                    fill="#10b981"
                    radius={[4, 4, 0, 0]}
                  />
                )}
                {hasMF && (
                  <Bar
                    dataKey="mf_cagr"
                    name="Magic Formula (CAGR)"
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
            Patrimônio Acumulado vs. Total Aportado por Janela
          </h3>
          <p className="mb-4 text-xs text-slate-400">
            Efeito combinado dos juros compostos + aportes mensais em cada horizonte
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
                  formatter={(val: number, name: string) => [formatBRL(val), name]}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="invested" name="Total Aportado" fill="#64748b" radius={[4, 4, 0, 0]} />
                {hasAM && (
                  <Bar
                    dataKey="am_equity"
                    name="Patrimônio Acquirer's"
                    fill="#10b981"
                    radius={[4, 4, 0, 0]}
                  />
                )}
                {hasMF && (
                  <Bar
                    dataKey="mf_equity"
                    name="Patrimônio Magic Formula"
                    fill="#38bdf8"
                    radius={[4, 4, 0, 0]}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-100">
              Matriz Comparativa Multi-Janelas (1, 3, 5, 10, 15 e 20 Anos)
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Clique em uma janela para abrir a curva detalhada e as carteiras
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950/60 text-slate-400 uppercase">
              <tr>
                <th className="px-4 py-3">Janela</th>
                <th className="px-4 py-3">Período Efetivo</th>
                <th className="px-4 py-3 text-right">Total Aportado</th>
                {hasAM && (
                  <>
                    <th className="px-4 py-3 text-right text-emerald-400">Patrimônio AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">CAGR AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">TIR (XIRR) AM</th>
                    <th className="px-4 py-3 text-right text-emerald-400">Max DD AM</th>
                  </>
                )}
                {hasMF && (
                  <>
                    <th className="px-4 py-3 text-right text-sky-400">Patrimônio MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">CAGR MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">TIR (XIRR) MF</th>
                    <th className="px-4 py-3 text-right text-sky-400">Max DD MF</th>
                  </>
                )}
                <th className="px-4 py-3 text-center">Detalhar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {data.windows.map((w) => {
                const am = w.strategies.acquirers_multiple;
                const mf = w.strategies.magic_formula;
                const refStrat = am ?? mf;
                const isSelected = activeWindowYears === w.window_years;

                return (
                  <tr
                    key={w.window_years}
                    onClick={() => onSelectWindow(w.window_years)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-emerald-950/30' : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <td className="px-4 py-3.5 font-semibold text-slate-100">
                      <span className="inline-flex items-center gap-1.5">
                        {w.window_years} {w.window_years === 1 ? 'Ano' : 'Anos'}
                        {w.window_clamped && (
                          <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
                            Ajustado
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-400">
                      {formatDateBR(w.effective_start_date)} → {formatDateBR(w.effective_end_date)}
                    </td>
                    <td className="px-4 py-3.5 text-right font-medium text-slate-300">
                      {formatBRL(refStrat?.total_invested)}
                    </td>
                    {hasAM && (
                      <>
                        <td className="px-4 py-3.5 text-right font-semibold text-slate-100">
                          {formatBRL(am?.final_equity)}
                        </td>
                        <td
                          className={`px-4 py-3.5 text-right font-medium ${
                            (am?.cagr_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(am?.cagr_pct, 2, true)}
                        </td>
                        <td
                          className={`px-4 py-3.5 text-right ${
                            (am?.xirr_pct ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(am?.xirr_pct, 2, true)}
                        </td>
                        <td className="px-4 py-3.5 text-right text-rose-400">
                          {formatPct(am?.max_drawdown_pct, 2)}
                        </td>
                      </>
                    )}
                    {hasMF && (
                      <>
                        <td className="px-4 py-3.5 text-right font-semibold text-slate-100">
                          {formatBRL(mf?.final_equity)}
                        </td>
                        <td
                          className={`px-4 py-3.5 text-right font-medium ${
                            (mf?.cagr_pct ?? 0) >= 0 ? 'text-sky-400' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(mf?.cagr_pct, 2, true)}
                        </td>
                        <td
                          className={`px-4 py-3.5 text-right ${
                            (mf?.xirr_pct ?? 0) >= 0 ? 'text-sky-300' : 'text-rose-400'
                          }`}
                        >
                          {formatPct(mf?.xirr_pct, 2, true)}
                        </td>
                        <td className="px-4 py-3.5 text-right text-rose-400">
                          {formatPct(mf?.max_drawdown_pct, 2)}
                        </td>
                      </>
                    )}
                    <td className="px-4 py-3.5 text-center">
                      <span className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-700">
                        Ver <ArrowUpRight className="h-3 w-3" />
                      </span>
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
