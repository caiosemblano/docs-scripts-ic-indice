# Leitura dos exports da Economatica

Os arquivos em `dados/` são exports crus da Economatica. A aplicação **não grava** de volta nessa pasta: o mapeamento de colunas acontece só em memória.

## Layout do `.xlsx`

Cada arquivo tem três linhas de metadados e um cabeçalho multilinha:

| Linha | Conteúdo |
|-------|----------|
| 1 | Nome da empresa na célula A1 e a marca `Economatica` na última coluna |
| 2–3 | Vazias |
| 4 | Cabeçalho: primeira linha do rótulo + unidades/período nas linhas seguintes da mesma célula |
| 5+ | Uma linha por dia. Células sem dado vêm como `-` |

O **nome do ativo** no ranking continua sendo o nome do arquivo sem extensão (`path.stem`). O nome da empresa não é extraído para lugar nenhum — fica só no arquivo.

Isso importa para arquivos cujo nome é o código numérico da Economatica, por exemplo `18970 ON.xlsx`. A célula A1 (`AES Tiete E ON`) é o único identificador humano; regravar a planilha com cabeçalho na primeira linha apagaria esse nome.

## Mapeamento de colunas

O leitor (`scripts/economatica.py`) abre o Excel com `header=None`, acha a primeira linha cuja coluna A é `Data` ou `Date`, e usa essa linha como nomes. O restante vira dado.

A correspondência usa a **primeira linha do rótulo** (case-insensitive, por prefixo):

| Economatica (1ª linha do rótulo) | Nome canônico | Uso no ranking |
|----------------------------------|---------------|----------------|
| `Data` / `Date` | `Date` | Data da observação |
| `Fechamento...` | (inalterado) | Ignorado |
| `EBITDA...` | `EBITDA` | Acquirer's Multiple e Magic Formula |
| `EV...` | `EV` | Acquirer's Multiple e Magic Formula |
| `ROIC...` | `ROIC` | Só Magic Formula |

O traço `-` da Economatica vira NaN. Arquivos que já venham com `Date` / `EBITDA` / `EV` / `ROIC` na primeira linha seguem o mesmo caminho (o cabeçalho é a linha 0).

O ROIC exportado em **%** não é convertido para fração: o rank da Magic Formula não muda se todos os ativos estão na mesma unidade.

O EBITDA (e em geral o ROIC) costuma aparecer só em datas de fim de trimestre. Nas demais datas o ativo é ignorado por valor inválido — comportamento já existente, não um bug de coluna.

## Por que não gravar em `dados/`

- Preserva o nome da empresa em A1.
- Evita divergência entre o export original e uma cópia “normalizada”.
- Permite reimportar da Economatica sem um passo extra de conversão.

Não há saída `.xlsx` normalizada, nem in-place nem em pasta nova. Arquivos também não são renomeados (código numérico não vira ticker).

## Como usar os exports crus

Coloque os `.xlsx` em `./dados` (ou outro diretório) e rode a interface ou a CLI como de costume. Não é preciso pré-processar as planilhas.

```bash
uv run streamlit run app.py
uv run python scripts/acquirers_multiple.py --data-dir ./dados --date 2025-06-30 --n 30
uv run python scripts/magic_formula.py --data-dir ./dados --date 2025-06-30 --n 30
```

Escolha uma data em que EBITDA/EV (e ROIC, na Magic Formula) sejam numéricos — em geral o último dia do trimestre.
