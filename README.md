# IC Índice — Carteiras e Backtest Quantitativo (Acquirer's Multiple & Magic Formula)

Aplicação web completa (**FastAPI + React/TypeScript**) e ferramentas de linha de comando para montagem de carteiras e simulação histórica de rentabilidade usando **The Acquirer's Multiple** e **The Magic Formula** a partir de planilhas `.xlsx` exportadas do **Economatica** (ou planilhas Excel padronizadas) em `./data` ou `./dados`.

## Principais Recursos

- **Estratégias Quantitativas (isoladas ou lado a lado)**:
  - **The Acquirer's Multiple**: ordena por `EBITDA / EV` decrescente (`EV > 0`), selecionando os Top `N` ativos com pesos iguais (`1/N`).
  - **The Magic Formula**: soma os ranks de `EBITDA / EV` (decrescente) e `ROIC` (decrescente), selecionando os `N` ativos de menor soma com pesos iguais (`1/N`).
- **Janelas de Tempo e Matriz Multi-Janelas**:
  - Simulação nas janelas de **1, 3, 5, 10, 15 e 20 anos** (simultaneamente na matriz comparativa e individualmente nos gráficos) ou a partir de **qualquer data inicial escolhida até o final da base**.
- **Aportes Mensais (DCA) e Rebalanceamento Configuráveis**:
  - **Aportes mensais opcionais** com dois modos de alocação: *Reequilíbrio Inteligente* (compra os ativos mais descontados da carteira vigente) ou *Pesos Iguais (`1/N`)* na carteira atual.
  - **Frequência de rebalanceamento**: `Anual` (padrão), `Semestral`, `Trimestral`, `Mensal` ou `Buy & Hold`.
- **Métricas Financeiras Separadas (Estratégia vs. Investidor)**:
  - **Sistema de Cotas (TWR)** e **CAGR (% a.a.)**: medem o retorno puro da estratégia sem distorção pelos aportes.
  - **TIR / XIRR (% a.a.)**: mede a rentabilidade anualizada ponderada pelo dinheiro sobre todos os fluxos de aportes mensais.
  - **Patrimônio Final**, **Total Aportado**, **Lucro Líquido**, **MOIC**, **Volatilidade Anualizada** e **Max Drawdown**.
- **Ingestão Economatica Ultra-Rápida & Higiene de Dados**:
  - Leitor XML streaming paralelo em C (`pyexpat`) + cache binário/Parquet invalidado por `mtime`/tamanho dos arquivos (`2.000+` planilhas processadas em segundos e recarregadas em `~1s`).
  - Cálculo automático de **EBITDA LTM (soma dos últimos 4 trimestres)** para séries exportadas como `EBITDA de 3 meses`.
  - Filtro configurável de **1 ação por emissor** (`ON` / `PN` / `UNIT`), priorizando a classe de maior presença em pregão nos últimos 63 dias.
  - Script dedicado `scripts/audit_economatica_files.py` para listar e separar planilhas exportadas com `EBITDA de 12 meses`, cópias duplicadas `(1).xlsx` e arquivos fora do padrão.

---

## Formato dos Dados (`./data` ou `./dados`)

A aplicação procura automaticamente arquivos `.xlsx` em `./data` (ou `./dados`, ou no caminho definido na variável de ambiente `DATA_DIR`). Ambas as pastas estão no `.gitignore`.

São aceitos automaticamente dois layouts de planilha:

1. **Exportação padrão do Economatica** (cabeçalho na linha 4, nome da empresa em `A1`, ticker no nome da 1ª aba, ausentes representados por `'-'`):
   - `Data`
   - `Fechamento ajust p/ prov Em moeda orig`
   - `EBITDA Em moeda orig em milhares de 3 meses consolid:sim*`
   - `EV Em moeda orig em milhares consolid:sim*`
   - `ROIC (IC fim) % de 12 meses consolid:sim*`
2. **Planilha simplificada** (cabeçalho na linha 1):
   - `Date` (ou `Data`), `Price` (ou `Close`, `Fechamento`, `Preco`), `EBITDA`, `EV` e `ROIC`.

---

## Executando a Aplicação Web

### Opção 1: Docker Compose (Recomendado para execução imediata)

```bash
docker compose up --build
```

Acesse em **http://localhost:8000**.

### Opção 2: Execução Local (Python + Node.js)

1. Instale as dependências Python e construa o frontend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..
```

2. Suba o servidor unificado FastAPI:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Acesse em **http://localhost:8000** (para desenvolvimento com hot-reload no frontend, rode `npm run dev` dentro de `frontend/` em paralelo ao `uvicorn`, acessando `http://localhost:5173`).

---

## Auditoria e Separação de Planilhas com `EBITDA de 12 meses`

Para inspecionar todos os arquivos `.xlsx` em `./data` e gerar os relatórios CSV (`audit_reports/reexportar_ebitda_12m.csv` e `audit_reports/economatica_audit_completo.csv`) com os tickers que precisam ser re-exportados em janela de 3 meses:

```bash
python scripts/audit_economatica_files.py --data-dir ./data
```

Para **mover fisicamente** os arquivos de `EBITDA de 12 meses`, duplicados `(1)` e inválidos para pastas separadas (`data_reexportar_12m/`, `data_duplicados/` e `data_invalidos/`):

```bash
python scripts/audit_economatica_files.py --data-dir ./data --move
```

*(Caso prefira apenas copiar sem remover de `./data`, utilize `--copy-12m` no lugar de `--move`.)*

---

## Scripts de Linha de Comando (CLI)

Os scripts originais de ranking pontual continuam disponíveis e compatíveis com o formato Economatica:

```bash
python scripts/acquirers_multiple.py --data-dir ./data --date 2026-11-10 --n 20
python scripts/magic_formula.py --data-dir ./data --date 2026-11-10 --n 20
```

Para permitir mais de uma classe de ação da mesma empresa no ranking CLI, adicione `--allow-duplicate-issuers`.

---

## Testes Automatizados

```bash
pytest
```
