# Documentacao das Novas Secoes do Dashboard

Este documento descreve os graficos, metricas e filtros das tres novas secoes adicionadas ao dashboard: **Estatisticas de Internacao**, **Estatisticas de Urgencia** e **Qualidade (NAQ)**.

---

## 1. Estatisticas de Internacao

Dados extraidos da tabela `estat_internacao` do sistema hospitalar. Registra cada entrada de paciente com dados de ala, especialidade, cidade de origem, hora e data.

### Filtros disponiveis (sidebar)

| Filtro | Descricao |
|---|---|
| **Periodo de internacao** | Selecao de intervalo de datas (formato DD/MM/AAAA). Filtra todas as metricas e graficos. |
| **Ala** | Multiselecao de alas (Flores, Ala Nova, Alto Risco, CPN, etc.). Quando vazio, considera todas. |
| **Especialidade** | Multiselecao de especialidades medicas (Obstetricia, Pediatria, Ala Medica, etc.). |
| **Cidade** | Multiselecao de cidades de origem dos pacientes. |
| **Excluir Campina Grande** | Remove Campina Grande de todos os graficos e metricas, permitindo visualizar apenas a demanda regional. |
| **Agrupar por (Dia / Mes)** | Altera a granularidade dos graficos temporais. "Mes" agrupa por mes (ex: 2025-05), "Dia" mostra cada dia individualmente. |

### KPIs (cards no topo)

| Metrica | O que representa |
|---|---|
| **Total de Internacoes** | Quantidade total de internacoes no periodo filtrado. |
| **Media Diaria** | Total de internacoes dividido pelo numero de dias do periodo selecionado. Indica o volume medio de entrada por dia. |
| **Cidades Atendidas** | Numero de cidades distintas de onde vieram os pacientes internados. Mede a abrangencia geografica do hospital. |
| **Top Especialidade** | Especialidade medica com maior numero de internacoes no periodo. |

### Graficos

#### 1. Internacoes por Mes / por Dia (grafico de linha)

- **Tipo:** Linha com marcadores (mes) ou linha continua (dia)
- **Eixo X:** Periodo (mes ou dia, conforme agrupamento selecionado)
- **Eixo Y:** Numero de internacoes
- **O que mostra:** Evolucao temporal do volume de internacoes. Permite identificar sazonalidade, tendencias de crescimento ou queda na demanda hospitalar. No modo diario, revela padroes como quedas em finais de semana ou feriados.

#### 2. Top 15 Cidades (barras horizontais)

- **Tipo:** Barras horizontais
- **Eixo X:** Numero de internacoes
- **Eixo Y:** Nome da cidade
- **O que mostra:** Ranking das 15 cidades que mais encaminharam pacientes para internacao. Util para entender a area de abrangencia do hospital e a demanda regional. Quando "Excluir Campina Grande" esta ativado, permite visualizar melhor as cidades menores que normalmente ficam ofuscadas pelo volume de CG.

#### 3. Distribuicao por Especialidade (grafico donut)

- **Tipo:** Pizza com furo central (donut)
- **Fatias:** Top 8 especialidades + "Outros" (agrupando as demais)
- **O que mostra:** Proporcao de internacoes por especialidade medica. Mostra quais areas concentram maior volume de atendimento (ex: obstetricia domina com ~34%, seguida de pediatria ~32% e clinica medica ~22%). Util para dimensionamento de recursos por area.

#### 4. Internacoes por Dia da Semana x Hora (heatmap)

- **Tipo:** Mapa de calor (heatmap)
- **Eixo X:** Hora do dia (0-23)
- **Eixo Y:** Dia da semana (Seg a Dom)
- **Cor:** Intensidade = numero de internacoes
- **O que mostra:** Concentracao de internacoes por horario e dia da semana. Areas mais escuras indicam picos de demanda. Permite identificar os horarios mais criticos para dimensionamento de equipe medica e de enfermagem, e quais plantoes (diurno/noturno) recebem mais pacientes.

#### 5. Internacoes por Ala ao Longo do Tempo (barras empilhadas)

- **Tipo:** Barras empilhadas
- **Eixo X:** Periodo (mes ou dia)
- **Eixo Y:** Numero de internacoes
- **Cores:** Cada cor representa uma ala (Flores, Ala Nova, Alto Risco, Sala de Parto, etc.)
- **O que mostra:** Distribuicao das internacoes por setor hospitalar ao longo do tempo. Permite visualizar a evolucao da ocupacao de cada ala, identificar tendencias de crescimento em setores especificos, e comparar a demanda relativa entre alas.

#### 6. Tabela Detalhada

- **Colunas:** Prontuario, Paciente, CPF, CNS, Data Internacao, Hora Internacao, Cidade, Medico, Ala, Enfermaria, Leito, Especialidade, CID, Sexo, Idade, Atendente Responsavel
- **O que mostra:** Todos os registros de internacao filtrados, para consulta individual e exportacao.

---

## 2. Estatisticas de Urgencia

Dados extraidos da tabela `estat_urgencia`. Registra cada atendimento de urgencia/emergencia, incluindo motivo, desfecho (status final), e tempos.

### Filtros disponiveis (sidebar)

| Filtro | Descricao |
|---|---|
| **Periodo de atendimento** | Selecao de intervalo de datas (formato DD/MM/AAAA). |
| **Status Final** | Multiselecao de desfechos: Alta, Internado, Retorno, Evadiu, Transferido, etc. |
| **Cidade** | Multiselecao de cidades de origem. |
| **Buscar motivo (texto)** | Busca textual livre no campo motivo (ex: "sangramento", "parto"). Case-insensitive. |
| **Excluir Campina Grande** | Remove CG de todos os graficos e metricas para visualizar demanda regional. |
| **Agrupar por (Dia / Mes)** | Altera granularidade do grafico temporal. |

### KPIs (cards no topo)

| Metrica | O que representa |
|---|---|
| **Total de Atendimentos** | Quantidade total de atendimentos de urgencia no periodo. |
| **Media Diaria** | Total dividido pelo numero de dias. Indica a carga diaria media do pronto-socorro. |
| **Taxa de Internacao** | Percentual de atendimentos que resultaram em internacao (status "Internado" / total). Valores tipicos ~34%. Indica a gravidade media dos casos atendidos. |
| **Taxa de Evasao** | Percentual de pacientes que evadiram antes do atendimento completo (status "Evadiu" / total). Valores tipicos ~4%. Indicador de qualidade — taxas altas podem indicar tempo de espera excessivo. |

### Graficos

#### 1. Atendimentos por Mes / por Dia (grafico de linha)

- **Tipo:** Linha com marcadores (mes) ou continua (dia)
- **O que mostra:** Volume de atendimentos de urgencia ao longo do tempo. Permite identificar periodos de maior demanda no pronto-socorro, sazonalidade, e tendencias.

#### 2. Distribuicao por Status Final (barras verticais)

- **Tipo:** Barras verticais com cores semanticas
- **Cores:** Verde = Alta, Azul = Internado, Laranja = Retorno, Vermelho = Evadiu, Roxo = outros
- **O que mostra:** Quantidade absoluta de atendimentos por desfecho. Permite visualizar a proporcao entre pacientes que receberam alta direta, os que precisaram internar, os que retornaram para reavaliacao e os que evadiram. E um indicador importante de resolubilidade do pronto-socorro.

#### 3. Top 10 Motivos de Atendimento (barras horizontais)

- **Tipo:** Barras horizontais
- **O que mostra:** Os 10 motivos mais frequentes que levaram pacientes ao pronto-socorro. "Avaliacao Obstetrica" tipicamente domina (~82%), seguido de "Sangramento Vaginal", "Atendimento Ginecologico", etc. Importante para planejamento de protocolos e equipes especializadas.

#### 4. Heatmap — Atendimentos por Dia da Semana x Hora

- **Tipo:** Mapa de calor
- **Eixo X:** Hora do dia (0-23)
- **Eixo Y:** Dia da semana (Segunda a Domingo)
- **O que mostra:** Padroes de demanda do pronto-socorro por horario e dia. Essencial para dimensionamento de equipe: identifica os horarios de pico (tipicamente manha e inicio da tarde em dias uteis), horarios de baixa demanda (madrugada), e diferencas entre dias uteis e fins de semana.

#### 5. Top 15 Cidades de Origem (barras horizontais)

- **Tipo:** Barras horizontais
- **O que mostra:** Cidades que mais geraram atendimentos de urgencia. Semelhante ao grafico de internacao, mas especifico para a porta de entrada do hospital. Util para identificar de onde vem a demanda espontanea e planejar acoes de regulacao.

#### 6. Tabela Detalhada

- **Colunas:** Prontuario, Paciente, CPF, CNS, Data Atendimento, Hora Atendimento, Cidade, Motivo, Gerador Ficha, CID, Atendido Por, Especialidade, Status Final, Hora Status Final
- **O que mostra:** Todos os atendimentos de urgencia filtrados, com detalhamento completo para auditoria e consulta.

---

## 3. Qualidade (NAQ)

Indicadores de qualidade hospitalar extraidos do sistema NAQ (Nucleo de Acesso a Qualidade). Engloba dados de 5 tabelas: taxa de ocupacao geral, ocupacao por ala, detalhamento de permanencia, censo geral de leitos e tempo de espera.

### KPIs (cards no topo — dados do ultimo mes disponivel)

| Metrica | O que representa |
|---|---|
| **Taxa de Ocupacao Atual (%)** | Percentual de ocupacao dos leitos no periodo mais recente. Valores acima de 100% indicam superlotacao (pacientes em leitos extras, macas, etc.). Inclui delta (variacao) em relacao ao mes anterior. |
| **Tempo Medio de Permanencia (dias)** | Media de dias que os pacientes ficam internados. Valores altos podem indicar casos mais complexos ou dificuldade de alta/transferencia. |
| **Media de Pacientes/Dia** | Numero medio de pacientes internados simultaneamente em um dia. Reflete a carga operacional diaria do hospital. |
| **Leitos Monitorados (censo)** | Total de leitos registrados no censo hospitalar mais recente (inclui vagos e ocupados). |

### Graficos

#### 1. Evolucao da Taxa de Ocupacao (grafico de linha)

- **Tipo:** Linha com marcadores
- **Eixo X:** Periodo mensal (ex: Mai/25, Jun/25...)
- **Eixo Y:** Taxa de ocupacao (%)
- **Linha vermelha tracejada:** Referencia de 100% (capacidade nominal)
- **O que mostra:** Tendencia historica da ocupacao hospitalar. No caso do ISEA, observa-se uma queda significativa de ~242% em mai/25 para ~103% em mar/26. Valores acima de 100% sao criticos e indicam necessidade de ampliacao de leitos ou gestao de fluxo.

#### 2. Evolucao do Tempo Medio de Permanencia (grafico de linha)

- **Tipo:** Linha com marcadores (cor laranja)
- **O que mostra:** Como o tempo medio de internacao variou ao longo dos meses. Tendencias de aumento podem indicar pacientes mais graves, dificuldade em dar alta, ou problemas de fluxo. Quedas podem indicar melhoria nos protocolos de alta.

#### 3. Ocupacao por Ala — Periodo Mais Recente (barras verticais)

- **Tipo:** Barras verticais com gradiente de cor
- **Eixo X:** Nome da ala
- **Eixo Y:** Numero de pacientes ocupando leitos
- **O que mostra:** Snapshot da ocupacao atual de cada setor. Identifica quais alas estao mais sobrecarregadas. Flores e Flores RN tipicamente tem maior ocupacao, seguidas de Alto Risco e Sala de Parto.

#### 4. Gauge — Taxa de Ocupacao Atual (indicador velocimetro)

- **Tipo:** Indicador gauge (velocimetro)
- **Faixas de cor:** Verde (0-80%), Amarelo (80-100%), Vermelho (>100%)
- **Ponteiro:** Marca de referencia em 100%
- **O que mostra:** Visualizacao imediata e intuitiva da taxa de ocupacao atual. O formato de velocimetro facilita a comunicacao com gestores — verde significa situacao confortavel, amarelo requer atencao, vermelho indica superlotacao.

#### 5. Distribuicao do Tempo de Permanencia por Ala (box plot)

- **Tipo:** Box plot (diagrama de caixa)
- **Eixo X:** Ala
- **Eixo Y:** Tempo de permanencia no periodo (dias)
- **Filtro:** Exclui outliers acima de 60 dias para melhor visualizacao
- **O que mostra:** Distribuicao estatistica do tempo de internacao em cada ala. A caixa mostra mediana e quartis (50% dos pacientes ficam dentro da caixa), as hastes mostram a variabilidade, e pontos isolados sao outliers. Alas com caixas mais altas tem pacientes que ficam mais tempo. Util para comparar eficiencia de fluxo entre setores — ex: CPN e Bloco Cirurgico tem permanencia curta (~2 dias), enquanto BI e Canguru tem permanencia mais longa (~15 dias).

#### 6. Censo Hospitalar — Leitos Ocupados vs Vagos (barras horizontais empilhadas)

- **Tipo:** Barras horizontais empilhadas
- **Cores:** Azul escuro = Ocupado, Azul claro = Vago
- **O que mostra:** Mapa visual do estado atual de cada ala — quantos leitos estao ocupados e quantos estao disponiveis. E um snapshot do ultimo censo disponivel. Permite identificar rapidamente onde ha disponibilidade de leitos e onde a ocupacao esta proxima de 100%.

#### 7. Top 20 Pacientes com Maior Tempo de Internacao (tabela)

- **Colunas:** Prontuario, Paciente, Ala, Especialidade, Cidade, Medico, Data Internacao, Tempo Permanencia Total (dias)
- **O que mostra:** Lista dos 20 pacientes com maior tempo total de internacao. Identifica casos de longa permanencia que podem necessitar de atencao especial, encaminhamento ou revisao do plano terapeutico. Pacientes com centenas de dias de internacao podem representar casos sociais ou de dificuldade de transferencia.
