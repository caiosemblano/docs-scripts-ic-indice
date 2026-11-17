import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Copy, Download, FileWarning, Terminal } from 'lucide-react';
import { fetchDatasetAudit } from '../api';
import { AuditRecord, DatasetAuditResponse } from '../types';

export function AuditPanel() {
  const [audit, setAudit] = useState<DatasetAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<'ebitda_12m' | 'duplicate' | 'invalid'>(
    'ebitda_12m',
  );
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    fetchDatasetAudit(false)
      .then((res) => setAudit(res))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading && !audit) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
        Carregando diagnóstico dos arquivos Economatica...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-5 text-sm text-rose-200">
        {error}
      </div>
    );
  }

  if (!audit) return null;

  const listMap: Record<'ebitda_12m' | 'duplicate' | 'invalid', AuditRecord[]> = {
    ebitda_12m: audit.ebitda_12m_records,
    duplicate: audit.duplicate_records,
    invalid: audit.invalid_records,
  };

  const rawRecords = listMap[filterCategory];
  const filtered = rawRecords.filter((r) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      r.ticker.toLowerCase().includes(q) ||
      r.filename.toLowerCase().includes(q) ||
      r.company_name.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Válidos (EBITDA 3 meses)</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-emerald-400">
            {audit.summary.valid_3m_count.toLocaleString('pt-BR')}
          </div>
          <p className="mt-1 text-[11px] text-slate-500">Convertidos automaticamente para LTM (4T)</p>
        </div>

        <button
          type="button"
          onClick={() => setFilterCategory('ebitda_12m')}
          className={`rounded-xl border p-4 text-left transition ${
            filterCategory === 'ebitda_12m'
              ? 'border-amber-500/60 bg-amber-950/20'
              : 'border-slate-800 bg-slate-900/70 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-amber-300">
            <span>EBITDA de 12 meses</span>
            <AlertTriangle className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-amber-300">
            {audit.summary.ebitda_12m_count}
          </div>
          <p className="mt-1 text-[11px] text-slate-400">Separados para re-exportação em 3 meses</p>
        </button>

        <button
          type="button"
          onClick={() => setFilterCategory('duplicate')}
          className={`rounded-xl border p-4 text-left transition ${
            filterCategory === 'duplicate'
              ? 'border-sky-500/60 bg-sky-950/20'
              : 'border-slate-800 bg-slate-900/70 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-sky-300">
            <span>Cópias Duplicadas</span>
            <Copy className="h-4 w-4 text-sky-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-sky-300">{audit.summary.duplicate_count}</div>
          <p className="mt-1 text-[11px] text-slate-400">Ignorados automaticamente no backtest</p>
        </button>

        <button
          type="button"
          onClick={() => setFilterCategory('invalid')}
          className={`rounded-xl border p-4 text-left transition ${
            filterCategory === 'invalid'
              ? 'border-rose-500/60 bg-rose-950/20'
              : 'border-slate-800 bg-slate-900/70 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-rose-300">
            <span>Inválidos / Fora do Padrão</span>
            <FileWarning className="h-4 w-4 text-rose-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-rose-300">{audit.summary.invalid_count}</div>
          <p className="mt-1 text-[11px] text-slate-400">Planilhas sem colunas financeiras</p>
        </button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex items-start gap-3">
          <Terminal className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
          <div className="space-y-1 text-xs">
            <div className="font-semibold text-slate-200">
              Separar fisicamente os arquivos divergentes no terminal:
            </div>
            <code className="block rounded bg-slate-950 px-2.5 py-1.5 font-mono text-[11px] text-emerald-300">
              python scripts/audit_economatica_files.py --data-dir ./data --move
            </code>
          </div>
        </div>

        <a
          href="/api/dataset/audit/reexport-csv"
          className="inline-flex items-center gap-2 rounded-lg bg-amber-500/20 px-4 py-2 text-xs font-semibold text-amber-200 ring-1 ring-amber-500/40 transition hover:bg-amber-500/30"
        >
          <Download className="h-4 w-4" />
          Baixar CSV ({audit.summary.ebitda_12m_count} Tickers EBITDA 12m)
        </a>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
          <h3 className="text-sm font-semibold text-slate-100">
            {filterCategory === 'ebitda_12m' &&
              `Arquivos com EBITDA de 12 meses (${filtered.length})`}
            {filterCategory === 'duplicate' && `Arquivos Duplicados (${filtered.length})`}
            {filterCategory === 'invalid' && `Arquivos Inválidos (${filtered.length})`}
          </h3>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filtrar por ticker, empresa ou arquivo..."
            className="w-64 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 border-b border-slate-800 bg-slate-950 text-slate-400 uppercase">
              <tr>
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3">Empresa</th>
                <th className="px-4 py-3">Arquivo</th>
                <th className="px-4 py-3">Diagnóstico</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {filtered.map((rec) => (
                <tr key={rec.filename} className="hover:bg-slate-800/40">
                  <td className="px-4 py-2.5 font-mono font-semibold text-slate-100">
                    {rec.ticker}
                  </td>
                  <td className="px-4 py-2.5 text-slate-300">{rec.company_name}</td>
                  <td className="px-4 py-2.5 font-mono text-slate-400">{rec.filename}</td>
                  <td className="px-4 py-2.5 text-slate-300">{rec.reason}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                    Nenhum arquivo encontrado nesta categoria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
