# Ranking de carteiras — Acquirer's Multiple e Magic Formula

Aplicação que lê vários arquivos Excel (um por ativo), filtra por uma data e monta uma carteira com pesos iguais. Há uma interface web em Streamlit e os scripts de linha de comando originais.

## Formato dos dados (Excel)

### Organização dos arquivos

- Coloque um arquivo `.xlsx` **por ativo** na pasta de dados (padrão: `./dados`).
- O **nome do ativo** é o nome do arquivo sem extensão.
  - Exemplo: `PETR4.xlsx` → ativo `PETR4`
- Dentro de cada arquivo: **indicadores nas colunas**, **datas nas linhas** (uma linha por dia).

Exports da Economatica (nome da empresa na primeira linha, cabeçalho multilinha com unidades) são lidos **em memória** e mapeados para as colunas abaixo. Os arquivos em `dados/` **não são alterados**. Detalhes do layout e do mapeamento: [docs/economatica.md](docs/economatica.md).

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

### Exemplo de planilha (`PETR4.xlsx`)

| Date       | EBITDA | EV      | ROIC |
|------------|--------|---------|------|
| 2024-03-14 | 98000  | 520000  | 0.18 |
| 2024-03-15 | 99000  | 510000  | 0.19 |
| 2024-03-18 | 100000 | 505000  | 0.19 |

- Use **uma linha por dia**.
- A data de referência precisa existir exatamente nesse arquivo; caso contrário o ativo é ignorado.
- Valores inválidos, nulos ou `EV <= 0` fazem o ativo ser descartado (com aviso).

### O que cada estratégia usa

| Estratégia | Métricas | Nota (`nota`) | Ranking |
|------------|----------|---------------|---------|
| Acquirer's Multiple | `EBITDA`, `EV` | `EBITDA / EV` (maior = melhor) | Top N pelo yield |
| Magic Formula | `EBITDA`, `EV`, `ROIC` | Soma dos ranks de yield e ROIC (menor = melhor) | Top N pelo rank combinado |

Em ambos, o **peso** de cada ativo na carteira é `1/n` (pesos iguais). A seleção por janela de tempo (data inicial e final) está fora do escopo atual; a interface já reserva esse modo para uma evolução futura.

## Instalação

Gerencie o ambiente com [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

## Interface web

```bash
uv run streamlit run app.py
```

Abre em `http://localhost:8501`. Na barra lateral você escolhe:

- o diretório dos arquivos `.xlsx`
- a estratégia (Acquirer's Multiple, Magic Formula ou as duas)
- a data de referência
- o número de ações na carteira (`n`)

A área principal mostra métricas, a tabela da carteira, exportação em CSV e os avisos de ativos descartados.

## CLI

```bash
uv run python scripts/acquirers_multiple.py --data-dir ./dados --date 2024-03-15 --n 30
uv run python scripts/magic_formula.py --data-dir ./dados --date 2024-03-15 --n 30
```

Se `--date` ou `--n` não forem informados, o script pede via input. Se `--data-dir` for omitido, usa `./dados` (ou pergunta se a pasta não existir).

### Saída da CLI

Lista de tuplas `(ativo, nota, peso)`:

```python
[('BBB', 0.4, 0.3333333333333333), ('DDD', 0.3, 0.3333333333333333), ('AAA', 0.2, 0.3333333333333333)]
```

## Docker

Coloque os arquivos `.xlsx` em `./dados` (montada no container).

```bash
docker build -t ic-indice-ranking .
docker run --rm -p 8501:8501 -v "$(pwd)/dados:/app/dados:ro" ic-indice-ranking
```

Para os scripts CLI:

```bash
docker run --rm -v "$(pwd)/dados:/app/dados:ro" \
  --entrypoint uv ic-indice-ranking \
  run --frozen --no-dev --no-sync python scripts/acquirers_multiple.py \
  --data-dir /app/dados --date 2024-03-15 --n 30
docker run --rm -v "$(pwd)/dados:/app/dados:ro" \
  --entrypoint uv ic-indice-ranking \
  run --frozen --no-dev --no-sync python scripts/magic_formula.py \
  --data-dir /app/dados --date 2024-03-15 --n 30
```
