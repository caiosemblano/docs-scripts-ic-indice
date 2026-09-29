# Ranking de carteiras — Acquirer's Multiple e Magic Formula

Scripts que leem vários arquivos Excel (um por ativo), filtram por uma data e montam uma carteira com pesos iguais.

## Formato dos dados (Excel)

### Organização dos arquivos

- Coloque um arquivo `.xlsx` **por ativo** na pasta de dados (padrão: `./dados`).
- O **nome do ativo** é o nome do arquivo sem extensão.
  - Exemplo: `PETR4.xlsx` → ativo `PETR4`
- Dentro de cada arquivo: **indicadores nas colunas**, **datas nas linhas** (uma linha por dia).

```
dados/
  PETR4.xlsx
  VALE3.xlsx
  ITUB4.xlsx
  ...
```

### Colunas esperadas

Os nomes das colunas são case-insensitive. Aceitos:

| Coluna | Aliases | Obrigatória | Descrição |
|--------|---------|-------------|-----------|
| Date | `Date`, `Data` | Sim (ambos os scripts) | Data da observação (uma por linha) |
| EBITDA | `EBITDA` | Sim (ambos) | Lucro operacional usado no yield |
| EV | `EV` | Sim (ambos) | Enterprise Value (> 0) |
| ROIC | `ROIC` | Só Magic Formula | Return on Invested Capital |
| Close | `Close`, `Preco`, `Adj Close` | Só o estudo de janelas | Preço para retorno da carteira entre rebalances |

### Exemplo de planilha (`PETR4.xlsx`)

| Date       | EBITDA | EV      | ROIC |
|------------|--------|---------|------|
| 2024-03-14 | 98000  | 520000  | 0.18 |
| 2024-03-15 | 99000  | 510000  | 0.19 |
| 2024-03-18 | 100000 | 505000  | 0.19 |

- Use **uma linha por dia**.
- A data passada na CLI (`--date`) precisa existir exatamente nesse arquivo; caso contrário o ativo é ignorado.
- Valores inválidos, nulos ou `EV <= 0` fazem o ativo ser descartado (com aviso no stderr).

### O que cada script usa

| Script | Métricas | Nota (`nota`) | Ranking |
|--------|----------|---------------|---------|
| Acquirer's Multiple | `EBITDA`, `EV` | `EBITDA / EV` (maior = melhor) | Top N pelo yield |
| Magic Formula | `EBITDA`, `EV`, `ROIC` | Soma dos ranks de yield e ROIC (menor = melhor) | Top N pelo rank combinado |

Em ambos, o **peso** de cada ativo na carteira é `1/n` (pesos iguais).

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
python scripts/acquirers_multiple.py --data-dir ./dados --date 2024-03-15 --n 30
python scripts/magic_formula.py --data-dir ./dados --date 2024-03-15 --n 30
```

Se `--date` ou `--n` não forem informados, o script pede via input. Se `--data-dir` for omitido, usa `./dados` (ou pergunta se a pasta não existir).

### Estudo com janelas históricas (Acquirer's Multiple)

Percorre o passado em rebalances mensais (`M`), trimestrais (`Q`) ou anuais (`Y`). Em cada data usa o **último fundamental disponível até aquele dia** (não exige a data exata na planilha). Sem coluna `Close`, gera só as carteiras e o turnover; com `Close`, também estima o retorno da janela e um NAV começando em `1000`.

```bash
python scripts/study_acquirers.py --data-dir ./dados --start 2020-01-01 --end 2024-12-31 --freq M --n 30 --out-dir ./out
docker compose run --rm study-acquirers --start 2020-01-01 --end 2024-12-31 --freq M --n 30
```

`--max-age-days 180` descarta EBITDA/EV mais velhos que isso na data do rebalance. Os CSVs `out/holdings.csv` e `out/summary.csv` listam a carteira de cada janela.

## Docker

Coloque os arquivos `.xlsx` em `./dados` (montada no container). Sem `--date` ou `--n`, o Compose abre o prompt interativo.

```bash
docker compose build
docker compose run --rm acquirers --date 2024-03-15 --n 30
docker compose run --rm magic-formula --date 2024-03-15 --n 30
```

Sem Compose:

```bash
docker build -t ic-indice-ranking .
docker run --rm -v "$(pwd)/dados:/app/dados:ro" ic-indice-ranking --date 2024-03-15 --n 30
docker run --rm -v "$(pwd)/dados:/app/dados:ro" \
  --entrypoint python ic-indice-ranking \
  scripts/magic_formula.py --data-dir /app/dados --date 2024-03-15 --n 30
```

### Saída

Lista de tuplas `(ativo, nota, peso)`:

```python
[('BBB', 0.4, 0.3333333333333333), ('DDD', 0.3, 0.3333333333333333), ('AAA', 0.2, 0.3333333333333333)]
```
