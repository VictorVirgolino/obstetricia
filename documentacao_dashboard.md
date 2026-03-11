# Documentacao do Dashboard Obstetricia - Campina Grande 2025

## Fontes de Dados

| Arquivo | Descricao |
|---------|-----------|
| `Producao AIH's Obstetricia CG_ISEA_CLIPSI_2025.xlsx` | Planilha Excel com 5 abas: CLIPSI por procedimento (aba 0), CLIPSI por municipio (aba 1), ISEA por procedimento (aba 2), ISEA por municipio (aba 3) e **Planilha1** (CPN - Centro de Parto Normal) |
| `pactuacao_paes_2025.csv` | CSV com pactuacao PPI/PAES: municipio encaminhador, quantidade pactuada, valor unitario e valor total |
| `itens_programacao.csv` | CSV com codigos e descricoes dos procedimentos da programacao MC/Obstetricia |

### Estrutura das abas do Excel

- **Abas de Procedimento (CLIPSI e ISEA):** Divididas em secao "QUANTITATIVO" (quantidade de AIH's por mes) e secao "VALORES" (custo SUS por mes). Cada linha comeca com o codigo SIGTAP de 10 digitos seguido da descricao, e colunas de Jan a Dez + Total.
- **Abas de Municipio (CLIPSI e ISEA):** Mesma estrutura de QUANTITATIVO/VALORES, mas cada linha comeca com codigo IBGE de 6 digitos seguido do nome do municipio.
- **Planilha1 (CPN):** Duas secoes separadas por headers "Procedimentos realizados". Primeira secao = quantidades, segunda secao = custos SUS. Unico procedimento: `0310010055 - PARTO NORMAL EM CENTRO DE PARTO NORMAL`.

### Tratamento do CPN

O CPN e separado do ISEA durante o carregamento:
- O procedimento `0310010055` e removido dos DataFrames do ISEA (`isea_pq` e `isea_pv`)
- Os valores do CPN sao subtraidos da linha de Campina Grande nas abas municipais do ISEA (`isea_mq` e `isea_mv`)
- O CPN passa a ser tratado como uma unidade independente

### Constantes

- `BONUS_CLIPSI = R$ 800,00` por procedimento (bonificacao contratual paga a CLIPSI)

---

## Secao 1: Visao Geral

### Metricas - Resumo Executivo Financeiro

| Metrica | Formula | Dados Utilizados |
|---------|---------|------------------|
| **Receita Total (Pactuacao)** | `sum(pactuacao["valor_pactuado"])` | Soma de todos os valores pactuados do CSV PAES (todas as cidades) |
| **Custo Total Estimado (SUS + Bonif.)** | `total_custo_sus + clipsi_bonus` | Soma do custo SUS de todos os hospitais + bonificacao CLIPSI |
| **Custo Producao SUS** | `isea_total_val + clipsi_total_val + cpn_total_val` | Soma dos valores SUS de todas as abas de procedimento (ISEA + CLIPSI + CPN), colunas Jan-Dez |
| **Custo c/ Bonificacao CLIPSI** | `clipsi_total_qty * 800` | Total de procedimentos CLIPSI multiplicado por R$ 800 |

### Metricas - Detalhamento dos Custos de Producao

| Metrica | Formula | Dados Utilizados |
|---------|---------|------------------|
| **Custo Municipios Pactuados (Estimado)** | `custo_total - (excedente + nao_pactuadas + cg_interno)` | Custo total menos as parcelas deficitarias e uso interno. Representa o custo "coberto" pela pactuacao |
| **Uso Interno (CG)** | `comp[mun_norm == "CAMPINA GRANDE"]["custo_producao"]` | Custo de producao dos procedimentos de residentes de Campina Grande (municipio executor, sem pactuacao) |
| **Nao Pactuadas (Deficitario)** | `sum(custo_producao)` das cidades com `pactuado == 0` e `realizado > 0` | Custo gerado por municipios que encaminharam pacientes sem ter pactuacao formal |
| **Uso Acima da Meta (Deficitario)** | `(qtde_acima / realizado) * valor_realizado` por cidade | Proporcao do custo SUS correspondente a quantidade que excedeu o pactuado, para cada cidade pactuada |

### Metrica - Resultado Financeiro

| Metrica | Formula |
|---------|---------|
| **Saldo Liquido** | `receita_total - custo_total` (Receita Pactuacao - Custo SUS+Bonif). Positivo = superavit, negativo = deficit |

### Grafico: Composicao do Custo Operacional (Pizza/Donut)

- **Tipo:** Grafico de pizza com furo central (donut)
- **Fatias:** ISEA (SUS), CLIPSI (SUS), CPN (SUS), Bonificacao CLIPSI
- **Valores:** `isea_total_val`, `clipsi_total_val`, `cpn_total_val`, `clipsi_bonus`
- **Fonte:** Soma das colunas Jan-Dez de cada aba de valores do Excel + calculo da bonificacao
- **Exibicao:** Percentual + valor absoluto em cada fatia

### Grafico: Distribuicao do Custo por Perfil de Atendimento (Pizza/Donut)

- **Tipo:** Grafico de pizza com furo central (donut)
- **Fatias:** Coberto (Pactuado), Uso Interno (CG), Nao Pactuadas, Excedente Pactuadas
- **Valores:**
  - Coberto = `custo_total - (excedente + nao_pactuadas + cg_interno)` (parcela do custo que e respaldada por pactuacao)
  - Uso Interno = custo SUS dos atendimentos de Campina Grande
  - Nao Pactuadas = custo SUS de cidades sem pactuacao que geraram producao
  - Excedente = custo proporcional da producao que ultrapassou a meta pactuada

### Tabelas

| Tabela | Conteudo | Ordenacao |
|--------|----------|-----------|
| **Top 10 Cidades Nao Pactuadas** | Municipio, Qtde Utilizada, Custo Gerado | Maior custo de producao primeiro |
| **Top 10 Cidades com Maior Excedente** | Municipio, Pactuado, Realizado, Excedente Qtde, Custo Excedente | Maior custo excedente primeiro |
| **Uso Interno - Campina Grande** | Municipio, Qtde Utilizada, Custo Producao | Dados de CG apenas |

---

## Secao 2: Por Hospital

### Metricas por Hospital (3 colunas: ISEA, CLIPSI, CPN)

**ISEA:**
| Metrica | Formula |
|---------|---------|
| Procedimentos | `sum(isea_pq[Jan:Dez])` - total de AIH's aprovadas |
| Receita SUS | `sum(isea_pv[Jan:Dez])` - valor total pago pelo SUS |
| Ticket Medio | `isea_val_total / isea_qty_total` |
| Tipos de Procedimento | `len(isea_pq)` - quantidade de linhas/codigos distintos |
| Municipios Atendidos | `len(isea_mq)` - quantidade de municipios na aba municipal |

**CLIPSI:**
| Metrica | Formula |
|---------|---------|
| Procedimentos | `sum(clipsi_pq[Jan:Dez])` |
| Receita SUS | `sum(clipsi_pv[Jan:Dez])` |
| Bonificacao CLIPSI | `clipsi_qty_total * 800` |
| Receita SUS + Bonificacao | `clipsi_val_total + clipsi_qty_total * 800` |
| Ticket Medio (SUS) | `clipsi_val_total / clipsi_qty_total` |
| Ticket Medio (SUS + Bonif.) | `ticket_medio_sus + 800` |
| Tipos de Procedimento | `len(clipsi_pq)` |

**CPN:**
| Metrica | Formula |
|---------|---------|
| Procedimentos | `sum(cpn_pq[Jan:Dez])` |
| Custo SUS Estimado | `sum(cpn_pv[Jan:Dez])` - valor SUS associado (tratado como custo) |
| Ticket Medio (Custo) | `cpn_val_total / cpn_qty_total` |
| Tipos de Procedimento | `len(cpn_pq)` (sempre 1) |

### Grafico: Parto Normal vs Cesariano (2 pizzas lado a lado)

- **ISEA:** Partos Normais (codigos `0310010039`, `0310010047`, `0310010055`), Cesarianos (codigos `0411010026`, `0411010034`, `0411010042`), Outros (diferenca)
- **CLIPSI:** Parto Normal (`0310010039`), Cesariano (`0411010034`), Outros (diferenca)
- **Tipo:** Pizza donut para cada hospital

### Graficos: Principais em "Outros" (2 barras horizontais)

- **Tipo:** Barras horizontais, top 5
- **Dados:** Procedimentos do hospital que nao sao parto normal nem cesariano, ordenados por total
- **Fonte:** `isea_pq` / `clipsi_pq` filtrando os codigos de parto normal e cesariano

### Grafico: Evolucao Mensal Comparativa (Linhas)

- **Tipo:** Linhas com marcadores, 3 series (ISEA, CLIPSI, CPN)
- **Eixo X:** Meses (Jan-Dez)
- **Eixo Y:** Quantidade de procedimentos
- **Dados:** Soma mensal de `isea_pq[MESES]`, `clipsi_pq[MESES]`, `cpn_pq[MESES]`

### Graficos: Procedimentos por Hospital (3 barras horizontais)

- **Tipo:** Barras horizontais, uma coluna por hospital
- **Dados:** Cada procedimento do hospital e sua quantidade total anual
- **Ordenacao:** Crescente (menor em cima, maior embaixo)
- **Escala de cor:** Blues (ISEA), Oranges (CLIPSI), Greens (CPN)

---

## Secao 3: Por Procedimento

### Filtros (Sidebar)

- **Hospital:** Ambos, ISEA, CLIPSI ou CPN
  - "Ambos" concatena e agrupa por codigo (soma de todos os hospitais)

### Metricas (4 colunas)

| Metrica | Formula |
|---------|---------|
| Total Anual | `row_q["total"]` - total do procedimento selecionado |
| Media Mensal | `total / 12` |
| Receita Total | `row_v["total"]` - valor SUS total do procedimento |
| Valor Medio/Proc | `valor_total / quantidade_total` |

### Grafico: Tendencia Mensal (Barras + Linha, eixo duplo)

- **Tipo:** Grafico combinado - barras (quantidade) + linha (valor R$)
- **Eixo Y esquerdo:** Quantidade de procedimentos por mes (barras azuis)
- **Eixo Y direito:** Valor em R$ por mes (linha rosa)
- **Dados:** Colunas Jan-Dez do procedimento selecionado, tanto de `pq` (quantidade) quanto `pv` (valor)

### Grafico: Evolucao de Todos os Procedimentos (Linhas multiplas)

- **Tipo:** Linhas, uma serie por procedimento
- **Dados:** `pq` derretido (melt) - cada procedimento vira uma linha com valor mensal
- **Legenda:** Horizontal abaixo do grafico

### Grafico: Valor Medio por Procedimento (Barras horizontais)

- **Tipo:** Barras horizontais
- **Dados:** Merge de `pq` (quantidade) com `pv` (valor) por codigo. `valor_medio = valor_total / quantidade_total`
- **Escala de cor:** Viridis
- **Exibido apenas** quando ha dados de valor disponivel

### Tabela Expansivel: Itens de Programacao

- **Dados:** CSV `itens_programacao.csv` com codigo e descricao dos procedimentos MC/Obstetricia

---

## Secao 4: Por Municipio

### Filtros (Sidebar)

- **Hospital:** Ambos, ISEA, CLIPSI, CPN (CPN redireciona para ISEA com aviso)
- **Excluir Campina Grande:** Checkbox (padrao: ativo)
- **Top N:** Slider de 10 a 50 (padrao: 20)

### Info Box: Campina Grande

- Exibido quando CG nao esta excluida
- Mostra: total de procedimentos de CG e % em relacao ao total

### Grafico: Top N Municipios - Quantidade AIH's (Barras verticais)

- **Tipo:** Barras verticais
- **Dados:** `mq` (aba municipal do hospital selecionado), coluna "total", ordenado decrescente
- **Escala de cor:** Blues

### Grafico: Top N Municipios - Receita Pactuado (Barras verticais)

- **Tipo:** Barras verticais
- **Dados:** `mv` (aba municipal de valores) com merge da pactuacao PAES. Coluna `valor_pactuado`
- **Escala de cor:** Greens

### Grafico: Top N Municipios - Custo SUS (Barras verticais)

- **Tipo:** Barras verticais
- **Dados:** `mv` coluna "total" (custo SUS por municipio)
- **Escala de cor:** Reds

### Grafico: Comparativo Financeiro Mensal - Municipio Selecionado (Barras + Linha)

- **Tipo:** Barras vermelhas (custo real mensal) + linha tracejada verde (receita estimada = pactuacao anual / 12)
- **Dados:**
  - Custo Real: colunas Jan-Dez do municipio na aba `mv`
  - Receita Estimada: `valor_pactuado / 12` (distribuicao uniforme da pactuacao anual)

### Grafico: Evolucao Mensal de Producao (Barras empilhadas ou simples)

- **Tipo:** Se "Ambos": barras empilhadas ISEA (azul) + CLIPSI (laranja). Se hospital unico: barras simples
- **Dados:** Colunas Jan-Dez do municipio selecionado na aba municipal de quantidade

### Tabelas Expansiveis

- **Quantitativo:** Tabela completa de `mq` com municipio + Jan-Dez + total
- **Valores (R$):** Tabela completa de `mv` com municipio + Jan-Dez + total

---

## Secao 5: Pactuacao vs Realizado

### Filtros (Sidebar)

- **Apenas com pactuacao:** Checkbox (padrao: ativo)
- **Top N:** Slider de 10 a 50 (padrao: 25)

**Nota:** Campina Grande e sempre excluida desta secao (e municipio executor, nao encaminhador).

### Metricas (5 colunas)

| Metrica | Formula | Dados |
|---------|---------|-------|
| Total Pactuado | `sum(df_c["pactuado"])` | Soma da quantidade pactuada (CSV PAES) de todos os municipios filtrados |
| Total Realizado | `sum(df_c["realizado"])` | Soma da producao real (ISEA+CLIPSI municipal) |
| % Execucao | `total_realizado / total_pactuado * 100` | Percentual geral de execucao |
| Acima da Meta | `count(pct_execucao > 100)` | Quantidade de municipios que ultrapassaram a meta |
| Abaixo da Meta | `count(pct_execucao <= 100 e pactuado > 0)` | Quantidade de municipios abaixo da meta |

### Info Box: Campina Grande

- Mostra quantidade de procedimentos e custo base SUS da demanda propria de CG

### Grafico: Pactuado vs Realizado (Barras agrupadas)

- **Tipo:** Barras agrupadas lado a lado
- **Series:** Pactuado (azul claro) e Realizado (azul escuro)
- **Dados:** Top N municipios com pactuacao, ordenados por quantidade pactuada
- **Eixo X:** Municipios

### Grafico: % Execucao da Pactuacao por Municipio (Barras horizontais)

- **Tipo:** Barras horizontais com texto do percentual
- **Dados:** `pct_execucao = realizado / pactuado * 100` para cada municipio com pactuacao
- **Escala de cor:** RdYlGn (vermelho = baixo, verde = alto)
- **Referencia:** Linha vertical tracejada vermelha em 100% ("Meta")
- **Ordenacao:** Crescente (menor execucao no topo)

### Tabelas: Acima e Abaixo da Meta (2 colunas)

| Tabela | Colunas | Filtro |
|--------|---------|--------|
| **Acima da Meta (>100%)** | Municipio, Pactuado, Realizado, % Exec., Custo Excedente | `pct_execucao > 100` |
| **Abaixo da Meta** | Municipio, Pactuado, Realizado, % Exec. | `pct_execucao < 100` |

### Grafico + Tabela: Municipios Sem Pactuacao

- **Grafico:** Top 15 cidades sem pactuacao por quantidade realizada (barras verticais, escala Reds)
- **Tabela:** Todos os municipios sem pactuacao com producao - Municipio, Realizado, Custo Gerado (R$)
- **Exibido apenas** quando existem municipios nessa condicao

### Tabela Expansivel: Tabela Completa (Cidades Pactuadas)

- Municipio, Pactuado, Realizado, % Execucao, Custo Excedente (R$)

---

## Secao 6: Custos Detalhados (SUS)

**Nota importante:** Nesta secao, o CPN NAO esta incluido nos calculos (apenas ISEA e CLIPSI). A variavel `receita_total` aqui e recalculada localmente como `isea_val + clipsi_val + clipsi_bonus`.

### Metricas (4 colunas)

| Metrica | Formula |
|---------|---------|
| Custo Total (SUS + Bonif.) | `isea_val_total + clipsi_val_total + clipsi_bonus_total` |
| ISEA (Custo SUS) | `sum(isea_pv[Jan:Dez])` |
| CLIPSI (Custo SUS) | `sum(clipsi_pv[Jan:Dez])` |
| CLIPSI (Custo Bonificacao) | `clipsi_qty_total * 800` |

### Grafico: Composicao dos Custos Gerais (Pizza/Donut)

- **Fatias:** ISEA (SUS), CLIPSI (SUS), CLIPSI (Bonificacao R$800)
- **Valores:** `isea_val_total`, `clipsi_val_total`, `clipsi_bonus_total`

### Grafico: Custo Mensal por Fonte (Barras empilhadas + Linha)

- **Tipo:** Barras empilhadas + linha de total
- **Series em barra:** ISEA SUS (azul), CLIPSI SUS (laranja), CLIPSI Bonif. (amarelo)
- **Linha:** Total mensal (rosa)
- **Dados:** Soma mensal de cada aba de valores + `clipsi_pq[mes] * 800` para bonificacao mensal

### Graficos: Ticket Medio por Procedimento (2 barras horizontais)

**ISEA (coluna esquerda):**
- **Tipo:** Barras horizontais
- **Dados:** Merge de `isea_pq` com `isea_pv` por codigo. `ticket = valor / quantidade`
- **Escala:** Blues

**CLIPSI (coluna direita):**
- **Tipo:** Barras horizontais empilhadas
- **Series:** SUS (laranja) + Bonificacao R$800 (amarelo) = ticket total
- **Dados:** `ticket_sus = valor / quantidade`, `ticket_total = ticket_sus + 800`

### Grafico: Custo por Municipio (Barras empilhadas verticais)

- **Filtros:** Excluir CG (checkbox), Top N (slider)
- **Tipo:** Barras empilhadas verticais
- **Series:** ISEA SUS, CLIPSI SUS, CLIPSI Bonif.
- **Dados:**
  - `isea_mun_sus`: soma do total de `isea_mv` agrupado por municipio
  - `clipsi_mun_sus`: soma do total de `clipsi_mv` agrupado por municipio
  - `clipsi_bonus`: `clipsi_mun_qty * 800` por municipio
  - `custo_total = isea_sus + clipsi_sus + clipsi_bonus`

### Tabela Expansivel: Tabela Financeira Completa

- Colunas: Municipio, ISEA (SUS), CLIPSI (SUS), CLIPSI (Bonif.), Custo Total

---

## Glossario de Variaveis Principais

| Variavel | Descricao |
|----------|-----------|
| `isea_pq` / `isea_pv` | DataFrames de procedimentos ISEA: quantidade (pq) e valores (pv) |
| `clipsi_pq` / `clipsi_pv` | DataFrames de procedimentos CLIPSI: quantidade e valores |
| `cpn_pq` / `cpn_pv` | DataFrames do CPN: quantidade e custos SUS |
| `isea_mq` / `isea_mv` | DataFrames municipais ISEA: quantidade e valores |
| `clipsi_mq` / `clipsi_mv` | DataFrames municipais CLIPSI: quantidade e valores |
| `pactuacao` | DataFrame com dados do CSV PAES (municipio, quantidade pactuada, valor) |
| `comp` | DataFrame consolidado: merge de pactuacao com producao real (ISEA+CLIPSI) por municipio |
| `cidades_pactuadas` | Subset de `comp`: municipios com pactuacao > 0 (exclui CG) |
| `cidades_nao_pactuadas` | Subset de `comp`: municipios sem pactuacao mas com producao (exclui CG) |
| `BONUS_CLIPSI` | R$ 800,00 - bonificacao por procedimento paga a CLIPSI |
