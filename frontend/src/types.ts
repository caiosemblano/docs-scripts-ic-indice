export type StrategyName = 'acquirers_multiple' | 'magic_formula';
export type RebalanceFrequency = 'annual' | 'semiannual' | 'quarterly' | 'monthly' | 'buy_and_hold';
export type ContributionMode = 'underweight' | 'equal_current';
export type EbitdaMode = 'ltm' | 'raw';

export interface DatasetSummary {
  data_dir: string;
  min_date: string;
  max_date: string;
  total_files: number;
  active_tickers: number;
  trading_days_count: number;
  fundamental_dates_count: number;
  valid_3m_count: number;
  ebitda_12m_count: number;
  duplicate_count: number;
  invalid_count: number;
}

export interface AuditRecord {
  filename: string;
  ticker: string;
  company_name: string;
  category: string;
  ebitda_window_months: number | null;
  raw_ebitda_header: string;
  columns_detected: string;
  reason: string;
}

export interface DatasetAuditResponse {
  summary: DatasetSummary;
  ebitda_12m_records: AuditRecord[];
  duplicate_records: AuditRecord[];
  invalid_records: AuditRecord[];
}

export interface BacktestFormState {
  strategies: StrategyName[];
  window_mode: 'preset' | 'custom';
  window_years: number;
  start_date: string;
  end_date: string;
  portfolio_size: number;
  initial_capital: number;
  enable_monthly_contribution: boolean;
  monthly_contribution: number;
  contribution_mode: ContributionMode;
  rebalance_frequency: RebalanceFrequency;
  ebitda_mode: EbitdaMode;
  reporting_lag_days: number;
  deduplicate_issuers: boolean;
  exclude_ebitda_12m_files: boolean;
  require_positive_ebitda: boolean;
  min_presence_63d: number;
  risk_free_rate_annual: number;
}

export interface PerformanceSummary {
  start_date: string;
  end_date: string;
  elapsed_days: number;
  elapsed_years: number;
  initial_capital: number;
  monthly_contribution: number;
  contributions_count: number;
  total_invested: number;
  final_equity: number;
  net_profit: number;
  moic: number;
  twr_total_pct: number;
  cagr_pct: number;
  xirr_pct: number | null;
  volatility_annual_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number | null;
  rebalances_count: number;
}

export interface RankedHolding {
  ticker: string;
  company_name: string;
  issuer: string;
  weight: number;
  score: number;
  earnings_yield: number;
  roic: number | null;
  ev: number;
  ebitda: number;
  price: number | null;
  rank_yield: number | null;
  rank_roic: number | null;
}

export interface RebalanceEvent {
  date: string;
  portfolio_equity: number;
  holdings_count: number;
  turnover_tickers_added: string[];
  turnover_tickers_removed: string[];
  holdings: RankedHolding[];
}

export interface EquityCurvePoint {
  date: string;
  equity: number;
  invested: number;
  quota: number;
  twr_pct: number;
  drawdown_pct: number;
}

export interface StrategyResult {
  strategy: StrategyName;
  requested_start_date: string;
  effective_start_date: string;
  effective_end_date: string;
  window_clamped: boolean;
  summary: PerformanceSummary;
  curve: EquityCurvePoint[];
  rebalances: RebalanceEvent[];
}

export interface ComparisonChartPoint {
  date: string;
  invested: number | null;
  acquirers_equity: number | null;
  magic_equity: number | null;
  acquirers_twr_pct: number | null;
  magic_twr_pct: number | null;
  acquirers_drawdown_pct: number | null;
  magic_drawdown_pct: number | null;
}

export interface BacktestRunResponse {
  results: Record<string, StrategyResult>;
  comparison_chart: ComparisonChartPoint[];
}

export interface WindowComparisonEntry {
  window_years: number;
  requested_start_date: string;
  effective_start_date: string;
  effective_end_date: string;
  window_clamped: boolean;
  strategies: Record<string, PerformanceSummary>;
  error: string | null;
}

export interface MultiWindowResponse {
  windows: WindowComparisonEntry[];
}
