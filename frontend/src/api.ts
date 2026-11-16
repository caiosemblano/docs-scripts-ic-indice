import {
  BacktestFormState,
  BacktestRunResponse,
  DatasetAuditResponse,
  DatasetSummary,
  MultiWindowResponse,
} from './types';

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `Erro HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // ignore parse failure
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

function buildSharedPayload(form: BacktestFormState) {
  return {
    strategies: form.strategies,
    portfolio_size: form.portfolio_size,
    initial_capital: form.initial_capital,
    monthly_contribution: form.enable_monthly_contribution ? form.monthly_contribution : 0,
    contribution_mode: form.contribution_mode,
    rebalance_frequency: form.rebalance_frequency,
    ebitda_mode: form.ebitda_mode,
    reporting_lag_days: form.reporting_lag_days,
    deduplicate_issuers: form.deduplicate_issuers,
    exclude_ebitda_12m_files: form.exclude_ebitda_12m_files,
    require_positive_ebitda: form.require_positive_ebitda,
    min_presence_63d: form.min_presence_63d,
    risk_free_rate_annual: form.risk_free_rate_annual,
    end_date: form.end_date ? form.end_date : null,
  };
}

async function safeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new Error(
      'Falha de conexão com o servidor (verifique se o container/backend está em execução na porta 8000).',
    );
  }
}

export async function fetchDatasetSummary(refresh = false): Promise<DatasetSummary> {
  const res = await safeFetch(`/api/dataset/summary?refresh=${refresh}`);
  return handleJson<DatasetSummary>(res);
}

export async function fetchDatasetAudit(refresh = false): Promise<DatasetAuditResponse> {
  const res = await safeFetch(`/api/dataset/audit?refresh=${refresh}`);
  return handleJson<DatasetAuditResponse>(res);
}

export async function runBacktest(form: BacktestFormState): Promise<BacktestRunResponse> {
  const payload = {
    ...buildSharedPayload(form),
    window_mode: form.window_mode,
    window_years: form.window_mode === 'preset' ? form.window_years : null,
    start_date: form.window_mode === 'custom' ? form.start_date : null,
  };
  const res = await safeFetch('/api/backtest/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleJson<BacktestRunResponse>(res);
}

export async function runMultiWindow(form: BacktestFormState): Promise<MultiWindowResponse> {
  const payload = {
    ...buildSharedPayload(form),
    windows_years: [1, 3, 5, 10, 15, 20],
  };
  const res = await safeFetch('/api/backtest/multi-window', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleJson<MultiWindowResponse>(res);
}
