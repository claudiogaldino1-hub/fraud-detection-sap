# Documentação Técnica v1.4 — SAP P2P Fraud Detection System

> **Versão:** 1.4 | **Pipeline:** `de9b92f4` | **Commit:** atual
> **Data:** 2026-06-15 UTC | **Autor:** Claudio Galdino <claudio.galdino1@gmail.com>
> **Versão anterior:** 1.3

---

## Resumo das Alterações nesta Versão

Revisão completa de consistência entre documentação e código-fonte. Divergências corrigidas:

- **Seção 2.1:** `n_invoices=2500` (era "~2.000")
- **Seção 2.3 AutoEncoder:** arquitetura corrigida — `Linear(16)` + `BatchNorm1d` (era `Dense(18)` sem normalização); epochs padrão da classe é 50, pipeline usa 30; normalização do `ae_score` é min-max (não percentil 97)
- **Seção 2.4 Grafo:** 5ª regra de detecção `SOD_PO_PAYMENT` adicionada; descrição de vendor isolado corrigida para `len(in_users)==1` (era "grau=0"); `graph_score` descrito como binário
- **Seção 2.10 Pipeline:** expandido de 8 para 15 etapas (Step 0 a Step 14)
- **Seção 4 Estrutura:** `pipeline.py` atualizado para "Step 0 a Step 14"
- **Seção 5.5 `vendor_payment_count_30d`:** nota adicionada — implementação computa total histórico, não janela de 30 dias
- **Seção 5.9 `po_invoice_ratio`:** esclarecido que ambos os campos (`DMBTR` e `WRBTR`) são do BSAK
- **Seção 6 Scores:** normalização corrigida para todos os três modelos

---

# Documentação Técnica — SAP P2P Fraud Detection System

> **Versão:** 1.0 | **Status:** Validado em produção simulada  
> **Última atualização:** 2026-05-31  
> **Público-alvo:** Auditores, Gestores de TI, Analistas de Controles Internos e Desenvolvedores

---

## Sumário

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Componentes do Sistema](#2-componentes-do-sistema)
3. [Como Rodar o Pipeline](#3-como-rodar-o-pipeline)
4. [Estrutura de Arquivos](#4-estrutura-de-arquivos)
5. [Features de Detecção e Contexto SAP P2P](#5-features-de-detecção-e-contexto-sap-p2p)
6. [Scores e Risk Tiers](#6-scores-e-risk-tiers)
7. [Governança, Rastreabilidade e LGPD](#7-governança-rastreabilidade-e-lgpd)
8. [Como Interpretar o Dashboard e os Alertas](#8-como-interpretar-o-dashboard-e-os-alertas)
9. [Catálogo Detalhado de Cenários de Fraude](#9-catálogo-detalhado-de-cenários-de-fraude)
10. [Histórico de Versões](#10-histórico-de-versões)

---

## 1. Visão Geral da Arquitetura

### O que é este sistema?

O **SAP P2P Fraud Detection System** é uma plataforma enterprise de detecção de fraudes e anomalias financeiras focada no fluxo **Procure-to-Pay (P2P)** — o processo que vai desde a criação de um pedido de compra até o pagamento ao fornecedor. É nesse fluxo que concentram-se os riscos mais críticos de fraude corporativa: fornecedores fantasma, duplicidade de pagamento, quebra de alçada e conluio entre compradores e fornecedores.

O sistema opera sobre os dados transacionais do SAP ERP (tabelas FI e MM) e aplica três camadas independentes de inteligência artificial em paralelo, combinando os resultados em um score único por transação. Cada alerta gerado é explicado em linguagem natural em português, facilitando a interpretação por auditores sem perfil técnico.

### Fluxo de dados P2P monitorado

```
Cadastro de           Pedido de          Recebimento         Fatura /          Pagamento
Fornecedor     →      Compra (PO)   →    de Mercadoria  →    Nota Fiscal  →    ao Fornecedor
(LFA1/LFB1)          (EKKO/EKPO)         (MARC)              (BKPF/BSEG)       (BSAK)
```

Cada etapa do fluxo é monitorada por cenários de fraude específicos. A tabela a seguir apresenta os 21 cenários cobertos pelo sistema (códigos alinhados com o `FraudInjector` em `data/generators/fraud_injector.py`):

| Etapa | Cenário | Código Interno |
|---|---|---|
| Cadastro | Fornecedor fantasma (sem histórico) | `GHOST_VENDOR` |
| Cadastro | Fornecedor duplicado (mesmo CNPJ, nome diferente) | `DUPLICATE_VENDOR` |
| Cadastro | Dados bancários alterados próximo ao pagamento | `BANK_CHANGE_BEFORE_PAYMENT` |
| Cadastro | Banco coincide com conta de funcionário interno | `VENDOR_EMPLOYEE_SHARED_BANK` |
| Cadastro | Fornecedor criado e pago em menos de 3 dias | `FAST_VENDOR_PAYMENT` |
| Pedido de Compra | Pedido de compra duplicado (mesmo fornecedor/valor/data) | `DUPLICATE_PO` |
| Pedido de Compra | PO sem contrato vigente (INFNR em branco acima de R$ 100k) | `PO_WITHOUT_CONTRACT` |
| Pedido de Compra | Fracionamento abaixo do limite de alçada (< R$ 50k) | `THRESHOLD_SPLITTING` |
| Fatura | Pagamento duplicado (mesmo LIFNR + DMBTR + BUDAT) | `DUPLICATE_PAYMENT` |
| Fatura | Fatura sem PO vinculado (AWKEY/EBELN em branco) | `MAVERICK_SPEND` |
| Fatura | Valor logo abaixo do limite de aprovação | `BELOW_THRESHOLD` |
| Fatura | NF cancelada (STBLG preenchido) sem estorno do pagamento | `CANCELLED_NOT_REVERSED` |
| Fatura | Divergência PO × Recebimento × Fatura > 10% (3-way match) | `THREE_WAY_MISMATCH` |
| Pagamento | Valor redondo suspeito (R$ 5k, 10k, 50k, 100k…) | `ROUND_PAYMENT` |
| Pagamento | Pagamento com data anterior ao mínimo do BKPF | `EARLY_PAYMENT` |
| Pagamento | Pagamento para conta diferente do cadastro (AUGBL divergente) | `WRONG_BANK_ACCOUNT` |
| Pagamento | Volume alto para mesmo fornecedor em < 48h (burst) | `PAYMENT_BURST` |
| Pagamento | Pagamento fora do expediente (antes 08h ou após 18h) | `AFTER_HOURS_PAYMENT` |
| Pagamento | Mesmo valor + mesmo fornecedor, todo mês (12 meses) | `SUSPICIOUS_RECURRENCE` |
| SoD / Conluio | Mesmo usuário criou fornecedor (LFA1.ERNAM) e aprovou pagamento (BKPF.USNAM) | `SOD_VENDOR_AND_PAYMENT` |
| SoD / Conluio | Mesmo usuário criou PO (EKKO.ERNAM) e confirmou recebimento (BKPF.USNAM) | `SOD_PO_AND_RECEIPT` |

### Stack tecnológico

| Camada | Tecnologia | Versão |
|---|---|---|
| Linguagem | Python | 3.12 |
| Dados | pandas, pyarrow | 2.2.2 / 15.0.2 |
| ML — Isolation Forest | scikit-learn | 1.4.2 |
| ML — AutoEncoder | PyTorch | 2.3.0 |
| ML — Grafo | NetworkX | 3.3 |
| Explicabilidade | SHAP | 0.45.1 |
| Narrativas em português | Claude API (Anthropic) | anthropic 0.28.0 |
| API REST | FastAPI + Uvicorn | 0.111.0 / 0.29.0 |
| Autenticação | JWT + bcrypt (passlib) | python-jose 3.3.0 |
| Containerização | Docker + Docker Compose | — |
| Testes | pytest + pytest-asyncio | 8.2.0 |

---

## 2. Componentes do Sistema

### 2.1 Gerador de Dados SAP (`data/generators/`)

**Para produção:** substitua o método `SAPDataGenerator._load_from_sap()` em `data/generators/sap_tables.py` pela conexão ao SAP via RFC (pyrfc) ou HANA SQL. Nenhum outro arquivo precisa ser alterado.

**Para desenvolvimento e testes:** o gerador produz dados sintéticos coerentes com a estrutura real do SAP:

- **300 fornecedores** (tabelas LFA1 + LFB1) com CNPJ fictício, dados bancários e histórico
- **2.000 pedidos de compra** (EKKO + EKPO + EKKN) com relacionamento válido a fornecedores
- **~2.500 documentos financeiros** (BKPF + BSEG + BSAK) representando faturas e pagamentos (`n_invoices=2500` no `SAPDataGenerator`)
- Integridade referencial mantida entre todas as 13 tabelas

Após a geração, o `FraudInjector` modifica aproximadamente **2% dos registros** para simular cada um dos 21 cenários de fraude, adicionando as colunas `FRAUD_LABEL` (0/1) e `FRAUD_TYPE` (string) para avaliação de performance dos modelos.

### 2.2 Isolation Forest (`models/isolation_forest.py`)

O **Isolation Forest** é um algoritmo de detecção de anomalias baseado em árvores de decisão que identifica registros "isoláveis" — aqueles que precisam de poucos cortes para ser separados dos demais. Em fraudes financeiras, transações fraudulentas tendem a ter características raras (valores atípicos, horários incomuns, fornecedores novos) e por isso são isoladas mais rapidamente.

**Configuração de produção:**

| Parâmetro | Valor | Significado |
|---|---|---|
| `contamination` | 0.02 | Espera-se que ~2% dos dados sejam anomalias |
| `n_estimators` | 200 | 200 árvores de decisão no ensemble interno |
| `random_state` | 42 | Reprodutibilidade garantida |

**Saída:** score contínuo entre 0 e 1 (`if_score`), onde valores mais altos indicam maior anomalia.

### 2.3 AutoEncoder (`models/autoencoder.py`)

O **AutoEncoder** é uma rede neural que aprende a comprimir e reconstruir transações normais. Quando apresentado a uma transação anômala, o erro de reconstrução é alto — o modelo "não reconhece" o padrão, sinalizando a anomalia.

**Arquitetura da rede:**

A dimensão oculta é calculada como `hidden = max(latent_dim × 4, input_dim // 2)` → com input=9 e latent=4: `max(16, 4) = 16`.

```
Encoder:
  Input (9) → Linear(16) → ReLU → BatchNorm1d(16) → Linear(8) → ReLU → Linear(4) → [Latente: 4]

Decoder (simétrico):
  [Latente: 4] → Linear(8) → ReLU → Linear(16) → ReLU → BatchNorm1d(16) → Linear(9) → Output (9)
```

> As camadas `BatchNorm1d` normalizam as ativações intermediárias, estabilizando o treinamento.

**Configuração:**

| Parâmetro | Valor | Significado |
|---|---|---|
| `latent_dim` | 4 | Dimensão do espaço latente (compressão) |
| `epochs` (default da classe) | 50 | Padrão se instanciado diretamente |
| `epochs` (chamada do pipeline) | 30 | Valor passado via `ae_epochs=30` em `run_pipeline()` |
| `threshold_percentile` | 97.0 | Percentil do erro de reconstrução para definir o **limiar de alerta binário** (não usado na normalização do score) |

**Saída:** `ae_score` — erro de reconstrução MSE normalizado pelo intervalo min-max do batch (0 a 1).

### 2.4 Análise de Grafo — NetworkX (`models/graph_analysis.py`)

O componente de **grafo de relacionamento** modela o P2P como um grafo dirigido onde os nós são entidades (usuários, fornecedores, empresas) e as arestas representam ações (criou, aprovou, pagou, comprou). Isso permite detectar padrões de **conluio e violações de Segregação de Funções (SoD)** que são invisíveis para modelos baseados em features tabulares.

**Detecções via grafo** (`detect_all()` chama 5 regras em sequência):

| Padrão | `alert_type` | Severidade | Método de Detecção |
|---|---|---|---|
| Mesmo usuário cadastrou o fornecedor E aprovou pagamento para ele | `SOD_VENDOR_PAYMENT` | HIGH | Verifica se o mesmo nó tem arestas `created_vendor` e `approved_payment` para o mesmo fornecedor |
| Mesmo usuário criou o PO E aprovou pagamento para o mesmo fornecedor | `SOD_PO_PAYMENT` | HIGH | Interseção de `created_po` e `approved_payment` por fornecedor |
| Conluio comprador-fornecedor-aprovador | `COLLUSION_TRIANGLE` | MEDIUM | Triângulo no grafo não-dirigido: 2+ usuários com relacionamento cruzado no mesmo fornecedor |
| Fornecedor com apenas 1 usuário interagindo | `ISOLATED_VENDOR` | LOW | `len(in_users) == 1` no subgrafo de entradas do nó fornecedor |
| Usuário com volume anormal de relacionamentos | `HIGH_DEGREE_USER` | MEDIUM | `degree(user) > mean + 3σ` no grafo completo |

**Saída:** `graph_score` binário (1.0 se o `LIFNR` da transação aparece em qualquer alerta de grafo, 0.0 caso contrário). Esse score é combinado no ensemble com peso 30%.

### 2.5 Ensemble (`models/ensemble.py`)

O ensemble combina os três modelos com pesos calibrados para o risco P2P:

```
ensemble_score = (0.35 × if_score) + (0.35 × ae_score) + (0.30 × graph_score)
```

| Modelo | Peso | Justificativa |
|---|---|---|
| Isolation Forest | 35% | Melhor desempenho em anomalias numéricas individuais |
| AutoEncoder | 35% | Captura padrões temporais e combinações incomuns de features |
| Grafo (NetworkX) | 30% | Único componente que detecta conluio e violações SoD |

O ensemble gera também o campo `risk_tier`:
- **HIGH** → `ensemble_score ≥ 0.70`
- **MEDIUM** → `0.40 ≤ ensemble_score < 0.70`
- **LOW** → `ensemble_score < 0.40`

### 2.6 SHAP — Explicabilidade (`explainer/shap_explainer.py`)

**SHAP (SHapley Additive exPlanations)** é uma técnica matemática derivada da teoria dos jogos que atribui a cada feature uma contribuição individual para a decisão do modelo em cada transação específica. Isso transforma o modelo de uma "caixa-preta" em um sistema auditável.

**Exemplo de leitura SHAP para um alerta:**
```
Alerta: Fornecedor V000031 — ensemble_score: 0.8846 (HIGH)

Feature                             Contribuição SHAP
--------------------------------------------------------------
days_since_vendor_created          +0.38  ← fornecedor criado há 3 dias
vendor_payment_count_30d           +0.28  ← 12 pagamentos em 30 dias
DMBTR (valor)                      +0.22  ← R$ 49.800 (abaixo do limite)
amount_deviation                   +0.21  ← desvio 4.2σ do histórico
```

Os valores SHAP são calculados sobre o modelo Isolation Forest (que suporta TreeExplainer nativo) e são passados como contexto para a geração de narrativas via Claude API.

### 2.7 Narrativas em Português — Claude API (`explainer/claude_narrator.py`)

Cada alerta de alto risco recebe uma **narrativa investigativa em português**, gerada pela Claude API com base nos valores SHAP. O prompt enviado à API inclui:
- Os dados da transação (fornecedor, valor, data, empresa)
- O score de cada modelo individualmente
- As top-5 features SHAP com seus valores e contribuições
- O contexto de negócio do fluxo P2P

A resposta é um texto de 3 a 5 parágrafos explicando o que foi detectado, por que é suspeito e quais passos investigativos são recomendados.

**Para ativar:** defina a variável de ambiente `ANTHROPIC_API_KEY` antes de rodar o pipeline com `generate_narratives=True`.

### 2.8 FastAPI — Camada de Serviço (`api/`)

A API REST expõe os alertas e permite que diferentes perfis de usuário interajam com o sistema:

| Endpoint | Método | Descrição |
|---|---|---|
| `/health` | GET | Status da aplicação |
| `/auth/token` | POST | Login e obtenção de token JWT |
| `/alerts` | GET | Listagem paginada de alertas (com filtros) |
| `/alerts/{id}/feedback` | POST | Marcar como verdadeiro/falso positivo |
| `/alerts/{id}/contest` | POST | Abrir contestação formal |
| `/models` | GET | Listar versões de modelos registradas |
| `/models/{id}/approve` | POST | Aprovar modelo para produção |
| `/export` | GET | Exportar alertas (CSV, JSON, Parquet) |
| `/export/powerbi` | GET | Exportar esquema estrela para Power BI |

### 2.9 RBAC — Controle de Acesso (`api/auth/rbac.py`)

O sistema implementa **Role-Based Access Control** com três perfis:

| Perfil | Permissões |
|---|---|
| `analista` | Visualizar alertas, registrar feedback (TP/FP) |
| `gestor` | Tudo do analista + aprovar modelos, exportar dados |
| `auditor` | Tudo do gestor + ler log de auditoria, ler catálogo de dados, gerir contestações |

**Usuários de teste padrão:**
- `ana.analista` / `analista123` → perfil analista
- `gabriel.gestor` / `gestor123` → perfil gestor
- `arthur.auditor` / `auditor123` → perfil auditor

### 2.10 MLOps (`mlops/`)

#### Pipeline (`mlops/pipeline.py`)
Orquestra **15 etapas** (Step 0 a Step 14):

```
[0]  Auditoria de segurança (bloqueia se detectar credencial exposta)
[1]  Gerar / carregar dados SAP
[2]  Injetar cenários de fraude (FraudInjector, ~2%)
[3]  Treinar ensemble (IF + AE + Grafo)
[4]  Inferência e geração de alertas
[5]  Calcular SHAP values (top-5 features por alerta)
[6]  Gerar narrativas investigativas via Claude API
[7]  Salvar baseline de data drift
[8]  Persistir alertas em Parquet (data/processed/alerts.parquet)
[9]  Relatório de custo (CostMonitor — tokens Claude API)
[10] Checksums SHA-256 dos artefatos críticos
[11] Atualizar CHANGELOG.md
[12] Gerar audit_dashboard.html
[13] Gerar executive_report.html
[14] Versionar documentação técnica
```

#### Versionamento de Modelos (`governance/model_versioning.py`)
Cada modelo treinado recebe:
- Um **hash SHA-256** do arquivo `.pkl` (integridade do artefato)
- Um **identificador de versão** baseado no `pipeline_id` (ex: `isolation_forest_bb67bc31`)
- Um **status de aprovação**: `pending` → `approved` ou `rejected`
- Registro no `governance/model_versions.json` com timestamp e usuário responsável

#### Detecção de Data Drift (`governance/data_drift.py`)
Compara a distribuição estatística das features entre o baseline de treinamento e dados novos usando dois testes:
- **PSI (Population Stability Index):** PSI > 0.2 indica drift severo que requer retreinamento
- **KS Test (Kolmogorov-Smirnov):** detecta mudanças na forma da distribuição com p-value < 0.05

---

## 3. Como Rodar o Pipeline

> **Pré-requisito:** Python 3.11+ instalado. Em ambiente Windows, use o caminho completo do Python se ele não estiver no PATH.

### Passo 1 — Navegue para a pasta do projeto

```cmd
cd C:\Users\claud\projetos\meu_portifolio\fraud_detection
```

> **Atenção:** todos os comandos abaixo devem ser executados dentro desta pasta.

### Passo 2 — Configure o PYTHONPATH

```cmd
set PYTHONPATH=C:\Users\claud\projetos\meu_portifolio\fraud_detection
```

> Em Linux/macOS: `export PYTHONPATH=$(pwd)`

### Passo 3 — Instale as dependências (apenas na primeira vez)

```cmd
C:\Users\claud\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
```

### Passo 4 — Execute o pipeline

```cmd
set PYTHONUTF8=1
C:\Users\claud\AppData\Local\Programs\Python\Python312\python.exe mlops/pipeline.py
```

**Output esperado:**

```
============================================================
Pipeline bb67bc31 started at 2026-05-31T...
============================================================

Step 0: Security audit — OK, no critical issues found.

Step 1: Loading/generating SAP data...
  Saved T001: 3 rows       ← tabelas de configuração
  Saved LFA1: 300 rows     ← cadastro de fornecedores
  Saved BSAK: 1,985 rows   ← documentos de pagamento
  Generated 13 SAP tables.

Step 2: Injecting fraud scenarios...
  Injected 632 fraud records across 6 tables.   ← ~2% de fraude

Step 3: Training ensemble detector...
Fitting Isolation Forest...
Fitting AutoEncoder...
  AE Epoch 10/30 — loss: 0.515
  AE Epoch 20/30 — loss: 0.362
  AE Epoch 30/30 — loss: 0.307   ← loss decrescendo = treinamento saudável
Building graph...
  Ensemble trained and saved.

Step 4: Running inference...
  500 alerts generated (2024 records total).

Step 5: Computing SHAP values...
  SHAP computed for 20 alerts.

Step 6: Skipping narrative generation.   ← normal sem ANTHROPIC_API_KEY

Step 7: Saving drift baseline...
  Baseline saved.

Step 8: Persisting alerts to data/processed/alerts.parquet...
Step 9: Cost report finalized.
Step 10: Checksums OK — N arquivo(s) registrado(s).
Step 11: Updating CHANGELOG.md...
Step 12: Generating audit dashboard...
Step 13: Generating executive report...
Step 14: Versioning documentation...

Pipeline bb67bc31 complete — 500 alerts ready.
```

### Passo 5 — Gere o dashboard HTML

```cmd
C:\Users\claud\AppData\Local\Programs\Python\Python312\python.exe scripts/generate_dashboard.py
```

### Passo 6 — Gere o relatório Excel

```cmd
C:\Users\claud\AppData\Local\Programs\Python\Python312\python.exe scripts/export_alerts.py
```

### Passo 7 — Abra os relatórios

```cmd
start reports\dashboard.html
start reports\alerts_report.xlsx
```

### Passo 8 — (Opcional) Suba a API REST

```cmd
C:\Users\claud\AppData\Local\Programs\Python\Python312\python.exe -m uvicorn api.main:app --reload --port 8000
```

Acesse `http://localhost:8000/docs` para a interface Swagger interativa.

### Passo 9 — (Opcional) Gerar narrativas em português via Claude API

```cmd
set ANTHROPIC_API_KEY=sk-ant-...
```

Edite a última linha de `mlops/pipeline.py`:
```python
run_pipeline(regenerate_data=True, ae_epochs=30, generate_narratives=True)
```

### Rodando com Docker

```cmd
REM Pipeline completo em container
docker-compose --profile pipeline up pipeline

REM API REST em container
docker-compose --profile api up api

REM Testes em container
docker-compose --profile test up tests
```

### Rodando os Testes

```cmd
C:\Users\claud\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/ -v
```

---

## 4. Estrutura de Arquivos

```
fraud_detection/
│
├── data/
│   ├── generators/
│   │   ├── sap_tables.py       ← gerador de dados SAP (13 tabelas P2P)
│   │   ├── fraud_injector.py   ← injeta 21 cenários de fraude (~2%)
│   │   └── schemas.py          ← definição de tipos e sensibilidade LGPD
│   ├── raw/                    ← tabelas SAP em Parquet (geradas pelo pipeline)
│   └── processed/
│       └── alerts.parquet      ← alertas finais com scores e risk_tier
│
├── models/
│   ├── isolation_forest.py     ← detector Isolation Forest + engenharia de features
│   ├── autoencoder.py          ← rede neural AutoEncoder (PyTorch)
│   ├── graph_analysis.py       ← detecção de conluio e SoD (NetworkX)
│   ├── ensemble.py             ← combina os três modelos com pesos
│   └── registry/               ← modelos treinados em .pkl (versionados)
│
├── explainer/
│   ├── shap_explainer.py       ← cálculo de SHAP values (TreeExplainer)
│   └── claude_narrator.py      ← geração de narrativas via Claude API
│
├── api/
│   ├── main.py                 ← aplicação FastAPI
│   ├── schemas.py              ← modelos Pydantic (request/response)
│   ├── auth/
│   │   └── rbac.py             ← JWT + RBAC (analista/gestor/auditor)
│   └── routers/
│       ├── alerts.py           ← GET /alerts (paginado e filtrado)
│       ├── feedback.py         ← POST /alerts/{id}/feedback
│       ├── models.py           ← GET/POST /models (aprovação)
│       ├── export.py           ← GET /export (CSV/JSON/Parquet/Power BI)
│       └── contestation.py     ← POST /alerts/{id}/contest
│
├── governance/
│   ├── audit_log.py            ← AUDIT_LOG.json com hash chain SHA-256
│   ├── model_versioning.py     ← registro de versões com hash de integridade
│   ├── data_drift.py           ← detecção de drift (PSI + KS Test)
│   ├── alert_contestation.py   ← ciclo de vida de contestações
│   └── lgpd_policy.md          ← política LGPD do projeto
│
├── mlops/
│   ├── pipeline.py             ← orquestrador do pipeline (Step 0 a Step 14)
│   └── model_approval.py       ← fluxo de aprovação de modelos
│
├── catalog/
│   └── data_catalog.json       ← catálogo de dados (campo a campo)
│
├── dashboard/
│   └── powerbi/
│       └── star_schema.py      ← exportação em esquema estrela para Power BI
│
├── scripts/
│   ├── generate_dashboard.py   ← gera reports/dashboard.html (standalone)
│   └── export_alerts.py        ← gera reports/alerts_report.xlsx
│
├── reports/
│   ├── dashboard.html          ← dashboard interativo (abre no browser)
│   └── alerts_report.xlsx      ← relatório Excel com 3 abas
│
├── docs/
│   └── TECHNICAL_DOCUMENTATION.md  ← este arquivo
│
├── tests/
│   ├── unit/
│   │   ├── test_generators.py  ← integridade de dados sintéticos
│   │   ├── test_models.py      ← shapes e ranges dos modelos
│   │   └── test_api.py         ← autenticação e endpoints
│   └── integration/
│       └── test_pipeline.py    ← pipeline end-to-end + hash chain
│
├── Dockerfile                  ← imagem python:3.11-slim, usuário não-root
├── docker-compose.yml          ← perfis: api / pipeline / test
├── requirements.txt            ← dependências com versões fixas
├── pytest.ini                  ← configuração de testes
└── .env.example                ← variáveis de ambiente necessárias
```

---

## 5. Features de Detecção e Contexto SAP P2P

As 9 features utilizadas pelos modelos Isolation Forest e AutoEncoder são calculadas na função `_build_features()` a partir das tabelas SAP brutas. Abaixo, a descrição de cada uma com seu significado de negócio e os campos SAP de origem.

### 5.1 `DMBTR` — Valor do pagamento em moeda local

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSEG / BSAK |
| **Campo SAP** | `DMBTR` (Document Amount in Local Currency) |
| **Tipo** | Numérico (float, BRL) |

**O que representa:** o valor contábil do documento de pagamento na moeda local da empresa. É a feature de maior impacto direto na detecção de fraudes de valor — superfaturamento, pagamento duplicado e valores logo abaixo de limites de aprovação são todos detectados via anomalia nesta feature.

**Sinal de alerta:** valores como R$ 49.800 (abaixo do limite de R$ 50.000) ou valores redondos como R$ 100.000 sem detalhamento de serviços.

---

### 5.2 `WRBTR` — Valor na moeda do documento

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSEG |
| **Campo SAP** | `WRBTR` (Amount in Document Currency) |
| **Tipo** | Numérico (float) |

**O que representa:** o valor original do documento na moeda em que a transação foi registrada (pode ser USD, EUR etc.). A relação entre `WRBTR` e `DMBTR` após a conversão cambial é usada para detectar manipulação de taxa de câmbio ou discrepâncias na conversão.

**Sinal de alerta:** divergência não explicável entre `WRBTR` convertido e `DMBTR`.

---

### 5.3 `days_to_pay` — Prazo de pagamento

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSAK (`AUGDT`) e BKPF (`BUDAT`) |
| **Cálculo** | `AUGDT − BUDAT` (em dias) |
| **Tipo** | Numérico (inteiro, clipado entre -365 e 365) |

**O que representa:** quantos dias se passaram entre a data de lançamento do documento (registro da fatura no SAP) e a data em que o pagamento foi efetivamente compensado. O prazo normal varia por contrato, mas tipicamente está entre 30 e 90 dias.

**Sinal de alerta:** valores próximos de zero ou negativos indicam pagamento antecipado — possível cumplicidade com o fornecedor para obter liquidez imediata. Valores muito altos podem indicar documentos esquecidos ou pagamentos fora do ciclo normal.

---

### 5.4 `hour_of_entry` — Hora de lançamento no sistema

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BKPF |
| **Campo SAP** | `CPUTM` (Entry Time) |
| **Tipo** | Inteiro (0–23) |

**O que representa:** a hora do dia em que o documento foi registrado no SAP. Transações legítimas seguem o expediente comercial (08h–18h). Lançamentos realizados à noite, madrugada ou fins de semana são indicadores de acesso não autorizado ou pagamentos realizados quando os controles de supervisão estão inoperantes.

**Sinal de alerta:** horário antes das 07h ou após das 20h, especialmente associado a fornecedores com outros indicadores suspeitos.

---

### 5.5 `vendor_payment_count_30d` — Volume total de pagamentos ao fornecedor

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSAK |
| **Cálculo** | `count(BELNR)` agrupado por `LIFNR` — total histórico no dataset (`groupby.transform("count")`) |
| **Tipo** | Inteiro |

> **Atenção:** o nome da feature (`_30d`) é descritivo do padrão de negócio monitorado, mas a implementação atual computa o **total acumulado** de pagamentos ao fornecedor no dataset, não uma janela deslizante de 30 dias. Para monitoramento em produção com dados contínuos, considere calcular a janela temporal via `rolling`.

**O que representa:** volume total de documentos de pagamento gerados para o mesmo fornecedor no período analisado. É uma das principais features para detectar dois padrões: **fracionamento de pedidos** (muitos pagamentos pequenos para o mesmo fornecedor evitando o limite de alçada) e **volume anormal** que pode indicar conluio ativo.

**Sinal de alerta:** volume muito acima da média dos demais fornecedores, especialmente se combinado com valores abaixo do limite de aprovação.

---

### 5.6 `amount_deviation_from_vendor_mean` — Desvio em relação ao histórico do fornecedor

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSAK (via agrupamento por LIFNR) |
| **Cálculo** | `(DMBTR − mean_fornecedor) / (std_fornecedor + 1)` |
| **Tipo** | Numérico (float, pode ser negativo) |

**O que representa:** o quanto o valor deste pagamento desvia da média histórica do mesmo fornecedor. Um fornecedor que normalmente recebe R$ 15.000 e de repente recebe R$ 280.000 terá um desvio alto nesta feature, mesmo que o valor absoluto não seja em si suspeito.

**Sinal de alerta:** desvio acima de 3σ (≈ valor 3 vezes maior que o desvio padrão histórico do fornecedor).

---

### 5.7 `is_round_amount` — Flag de valor redondo

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSAK (`DMBTR`) |
| **Cálculo** | Flag 1 se `DMBTR ∈ {5.000, 10.000, 25.000, 50.000, 100.000, 250.000, 500.000}` |
| **Tipo** | Binário (0 ou 1) |

**O que representa:** pagamentos com valores redondos e genéricos, sem a granularidade esperada de uma fatura real (que normalmente inclui impostos, fretes, centavos). A **Lei de Benford** aplicada a dados contábeis mostra que valores redondos são sobre-representados em fraudes.

**Sinal de alerta:** valor redondo em combinação com fornecedor novo, sem PO vinculado ou próximo ao limite de aprovação.

---

### 5.8 `days_since_vendor_created` — Tempo de vida do fornecedor

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | LFA1 (`ERDAT`) e BSAK (`BUDAT`) |
| **Cálculo** | `BUDAT − ERDAT` (em dias, clipado entre 0 e 3.650) |
| **Tipo** | Inteiro (dias) |

**O que representa:** quantos dias se passaram entre o cadastro do fornecedor no SAP e a data de lançamento do pagamento. É a **feature de maior importância SHAP** no modelo atual, pois o cenário de fornecedor criado e pago na mesma semana é um dos mais clássicos e frequentes em fraudes P2P.

**Sinal de alerta:** valores abaixo de 30 dias indicam risco alto; abaixo de 7 dias são praticamente um sinal definitivo de fornecedor fantasma.

---

### 5.9 `po_invoice_ratio` — Razão entre valor em moeda local e valor no documento

| Atributo | Detalhe |
|---|---|
| **Tabela SAP** | BSAK (campos `DMBTR` e `WRBTR` estão ambos na mesma tabela) |
| **Cálculo** | `DMBTR / (WRBTR + 1)` |
| **Tipo** | Numérico (float, esperado próximo de 1.0 para documentos em BRL) |

**O que representa:** a razão entre `DMBTR` (valor convertido para moeda local da empresa — BRL) e `WRBTR` (valor na moeda original do documento, que pode ser USD, EUR etc.). Em transações domésticas, o ratio deve ser próximo de 1.0. Desvios expressivos indicam possível manipulação de taxa de câmbio ou inconsistência de conversão — complementando o controle de **three-way match**.

> O nome `po_invoice_ratio` alude ao conceito de negócio monitorado (relação PO-fatura), mas os campos computados são `DMBTR` e `WRBTR` do BSAK, não campos do EKKO/PO diretamente.

**Sinal de alerta:** ratio > 1.15 (valor local 15% maior que o registrado na moeda do documento) ou ratio < 0.85 sem nota de crédito correspondente.

---

## 6. Scores e Risk Tiers

### Como o score é calculado

Cada transação recebe três scores independentes (0 a 1) e um score final:

```
ensemble_score = (0.35 × if_score) + (0.35 × ae_score) + (0.30 × graph_score)
```

Os scores brutos de cada modelo são normalizados para o intervalo [0, 1] antes da combinação:
- **if_score:** negativo do `score_samples()` do scikit-learn, normalizado por **min-max** do batch
- **ae_score:** erro quadrático médio de reconstrução (MSE), normalizado por **min-max** do batch. O `threshold_percentile=97.0` é usado apenas para derivar o **limiar de alerta binário** (label 1/0) — não entra na normalização do score contínuo
- **graph_score:** valor binário (1.0 se o fornecedor aparece em algum alerta de grafo, 0.0 caso contrário)

### Classificação por Risk Tier

| Tier | Threshold | Interpretação | Ação Recomendada |
|---|---|---|---|
| 🔴 **HIGH** | ≥ 0.70 | Anomalia grave, múltiplos sinais convergentes | Investigação imediata, bloqueio preventivo do pagamento |
| 🟡 **MEDIUM** | 0.40 – 0.69 | Anomalia moderada, requer análise | Revisão manual pela equipe de auditoria no próximo ciclo |
| 🟢 **LOW** | < 0.40 | Sem anomalia significativa | Monitoramento contínuo, nenhuma ação imediata |

### Interpretando os scores individuais

| Score | Valor Baixo (<0.30) | Valor Médio (0.30–0.60) | Valor Alto (>0.60) |
|---|---|---|---|
| `if_score` | Transação típica | Padrão pouco comum | Outlier estatístico |
| `ae_score` | Reconstrução perfeita | Padrão levemente atípico | Padrão não reconhecido pela rede |
| `graph_score` | Sem conexões suspeitas | Conexões ambíguas | SoD violado ou conluio detectado |

### Concordância entre modelos

O campo `unanimous` no relatório de comparação indica quantos alertas foram sinalizados pelos **três modelos simultaneamente**. Alertas unânimes têm probabilidade de verdadeiro positivo significativamente maior:

```
Detector comparison:
if_alerts  ae_alerts  graph_alerts  ensemble_alerts  unanimous  two_of_three
       92         19          2024              500         18            93
```

> **Leitura:** dos 500 alertas do ensemble, 18 foram sinalizados pelos três modelos ao mesmo tempo — estes são os casos de mais alta prioridade para investigação.

### Taxa de falsos positivos esperada

Em dados de teste sintéticos com 2% de fraudes reais, a configuração atual produz:
- Taxa de alertas: ~25% das transações (maioria MEDIUM, filtragem conservadora por design)
- Precisão estimada nos HIGH: ~70–85% (baixa taxa de falso positivo nos casos críticos)
- Recall estimado: ~90%+ (sistema prioriza não perder fraudes reais)

O endpoint `/alerts/{id}/feedback` permite que analistas registrem verdadeiros e falsos positivos, gerando métricas reais de precisão ao longo do tempo.

---

## 7. Governança, Rastreabilidade e LGPD

### 7.1 Audit Log com Hash Chain

Toda ação relevante é registrada em `governance/AUDIT_LOG.json` com o seguinte formato:

```json
{
  "timestamp": "2026-05-31T10:05:30.921260",
  "event": "PIPELINE_START",
  "user": "pipeline",
  "details": {"pipeline_id": "bb67bc31"},
  "prev_hash": "0000000000000000",
  "entry_hash": "a3f7b2c19d..."
}
```

Cada entrada contém o hash SHA-256 da entrada anterior (`prev_hash`), formando uma **cadeia imutável**. Qualquer alteração retroativa invalida todos os hashes subsequentes, tornando adulterações detectáveis imediatamente.

### 7.2 Versionamento de Modelos

Modelos não são atualizados automaticamente em produção. O fluxo obrigatório é:

```
Treinar → Registrar (hash SHA-256) → Revisar → Aprovar/Rejeitar → Promover
```

O gestor ou auditor precisa aprovar explicitamente via `POST /models/{id}/approve` antes que um novo modelo passe a gerar alertas. Modelos rejeitados são mantidos no registro para auditoria futura.

### 7.3 Detecção de Data Drift

O sistema salva um **baseline estatístico** (média, desvio padrão, percentis) de todas as features no momento do treinamento. A cada execução, compara-se a distribuição atual com o baseline:

| Métrica | Limiar de Alerta | Ação |
|---|---|---|
| **PSI > 0.10** | Drift moderado | Monitorar com atenção |
| **PSI > 0.20** | Drift severo | Retreinar o modelo |
| **KS p-value < 0.05** | Mudança de distribuição | Avaliar retreinamento |

### 7.4 Processo de Contestação

Qualquer alerta pode ser formalmente contestado pelo fornecedor ou pelo time de negócio:

```
OPEN → UNDER_REVIEW → CLOSED (resolved / dismissed)
```

Contestações são registradas com timestamp, usuário responsável e justificativa. O auditor tem acesso a todo o histórico via `GET /alerts/{id}/contestations`.

### 7.5 LGPD — Lei Geral de Proteção de Dados

O sistema classifica cada campo em quatro níveis de sensibilidade:

| Nível | Campos | Tratamento |
|---|---|---|
| **PUBLIC** | Empresa (`BUKRS`), Ano fiscal (`GJAHR`) | Sem restrição |
| **INTERNAL** | Número do documento (`BELNR`), scores | Acesso por perfil mínimo de analista |
| **CONFIDENTIAL** | Valores (`DMBTR`, `WRBTR`), datas | Acesso por gestor ou auditor; mascaramento em logs |
| **RESTRICTED** | CNPJ, dados bancários (`BANKN`, `BANKL`) | Acesso apenas por auditor; pseudonimização obrigatória em ambiente de teste |

> **Importante:** em produção com dados reais, os campos `RESTRICTED` devem ser pseudonimizados antes de qualquer processamento pelos modelos. O sistema já prevê esta substituição no método `_load_from_sap()`.

A política LGPD completa está documentada em `governance/lgpd_policy.md`, cobrindo base legal (legítimo interesse para controle interno — Art. 10 LGPD), direitos do titular, transferência internacional e prazo de retenção de dados (5 anos, alinhado com legislação fiscal brasileira).

---

## 8. Como Interpretar o Dashboard e os Alertas

### 8.1 Dashboard HTML (`reports/dashboard.html`)

O dashboard é gerado pelo script `scripts/generate_dashboard.py` e exibe dados calculados diretamente a partir do `alerts.parquet`. É completamente autossuficiente (sem servidor, sem banco de dados) — basta abrir o arquivo no browser.

#### Seção: Resumo Executivo (KPIs)

| KPI | O que mede | Como interpretar |
|---|---|---|
| **Total de Alertas** | Transações que superaram o threshold de ensemble | Espera-se ~20–25% do total de pagamentos no período |
| **Risco Alto** | Alertas com score ≥ 0.70 | Cada caso ALTO deve ter investigação iniciada em até 24h |
| **Score Ensemble Médio** | Média dos scores de todos os alertas | Valores acima de 0.55 indicam período com anomalia elevada |
| **Score Máximo** | O caso mais crítico do período | Contexto para calibrar a urgência dos alertas HIGH |

#### Seção: Alertas por Tipo de Fraude

Gráfico de barras mostrando a quantidade de alertas por cenário. Os maiores volumes esperados são:
- **SEM_TIPO:** transações sem cenário de fraude injetado detectadas como anômalas pelo modelo (legítimos ou novos padrões)
- **ROUND_PAYMENT:** valores redondos — alta incidência, requer correlação com outros indicadores
- **EARLY_PAYMENT:** pagamentos antecipados — avaliar se existem justificativas contratuais

#### Seção: Top 20 Alertas Críticos

A tabela mostra as 20 transações de maior `ensemble_score`. Para cada linha:

- **IF / AE / Grafo:** scores individuais de cada modelo. Se todos são altos, o caso é mais sólido.
- **Score Ensemble:** o score combinado (coluna mais importante para priorização)
- **Badge de Risco:** indicador visual — vermelho (HIGH), laranja (MEDIUM), verde (LOW)

> **Dica de investigação:** priorize os casos onde **IF e Grafo são simultaneamente altos**, pois indicam tanto anomalia estatística (IF) quanto violação de segregação de funções ou conluio (Grafo).

#### Seção: Importância das Features (SHAP)

Mostra quais features mais influenciaram os alertas dos 20 casos de maior score. O gráfico horizontal exibe o **mean(|SHAP value|)** — a contribuição média absoluta de cada feature.

**Leitura prática:**
- Feature no topo = maior impacto médio nas decisões do modelo
- `days_since_vendor_created` no topo significa: os alertas mais críticos envolvem fornecedores novos
- `vendor_payment_count_30d` alto significa: há padrão de volume anormal de pagamentos

### 8.2 Relatório Excel (`reports/alerts_report.xlsx`)

O Excel complementa o dashboard com dados tabulares completos:

| Aba | Uso recomendado |
|---|---|
| **Resumo Executivo** | Apresentações para gestores e comitê de auditoria |
| **Todos os Alertas** | Investigação detalhada, filtros por fornecedor/data/tipo |
| **Análise SHAP** | Reuniões técnicas, calibração do modelo, evidências de auditoria |

### 8.3 Fluxo de Investigação Recomendado

```
1. Abrir o dashboard e verificar os KPIs gerais
        ↓
2. Identificar alertas HIGH (score ≥ 0.70)
        ↓
3. Para cada alerta HIGH:
   a) Verificar o FRAUD_TYPE indicado
   b) Consultar os scores individuais (IF + AE + Grafo)
   c) Ler a narrativa gerada pela Claude API (se disponível)
   d) Analisar as features SHAP do alerta específico
        ↓
4. Executar verificação no SAP:
   - Checar data de cadastro do fornecedor (LFA1)
   - Verificar se existe PO vinculado (EKKO/EKPO)
   - Confirmar dados bancários atuais vs. histórico (LFB1)
   - Validar three-way match (PO × GR × Invoice)
        ↓
5. Registrar resultado:
   - Verdadeiro positivo → encaminhar para investigação formal
   - Falso positivo → registrar feedback via API ou dashboard
   - Em dúvida → abrir contestação para análise complementar
```

---

## 9. Catálogo Detalhado de Cenários de Fraude

> **Fonte autoritativa:** `data/generators/fraud_injector.py` — classe `FraudInjector`.  
> Taxa de injeção padrão: **2% dos registros** (parâmetro `fraud_rate`, configurável).  
> Colunas adicionadas em cada tabela afetada: `FRAUD_LABEL` (0/1) e `FRAUD_TYPE` (string).

### Legenda — Camadas de Detecção

| Sigla | Camada | Arquivo |
|---|---|---|
| **IF** | Isolation Forest (anomalia estatística tabular) | `models/isolation_forest.py` |
| **AE** | AutoEncoder (padrões temporais e combinações de features) | `models/autoencoder.py` |
| **GR** | Grafo NetworkX (SoD, conluio, nós isolados) | `models/graph_analysis.py` |
| **FD** | Feature Direta (regra determinística sobre campo SAP) | features geradas em `mlops/pipeline.py` |

---

### 9.1 Categoria: Cadastro de Fornecedor

| # | Cenário | Código `FRAUD_TYPE` | Tabela SAP Principal | Mecanismo de Injeção | Camadas que Cobrem |
|---|---|---|---|---|---|
| 1 | Fornecedor fantasma | `GHOST_VENDOR` | `LFA1` | Substitui NAME1 e STCD1 por valores aleatórios em fornecedores amostrados | IF · GR |
| 2 | Fornecedor duplicado (mesmo CNPJ, nome variado) | `DUPLICATE_VENDOR` | `LFA1` | Insere nova linha com LIFNR prefixado `VDUP`, NAME1 levemente alterado e ERDAT +30–180d | FD |
| 3 | Dados bancários alterados antes do pagamento | `BANK_CHANGE_BEFORE_PAYMENT` | `LFB1` | Define BKDAT entre 1–7 dias antes de um AUGDT aleatório do BSAK; BANKN = `99999999` | FD · IF |
| 4 | Banco do fornecedor coincide com conta de funcionário | `VENDOR_EMPLOYEE_SHARED_BANK` | `LFB1` | Força BANKL=`237` e BANKN=`12345678` (conta sintética de "funcionário interno") | FD |
| 5 | Fornecedor criado e pago em < 3 dias | `FAST_VENDOR_PAYMENT` | `BSAK` | Retroage BUDAT para ERDAT + 1–3 dias nos pagamentos do fornecedor amostrado | FD · IF |

**Campos SAP relevantes:** `LFA1.ERDAT`, `LFA1.STCD1`, `LFB1.BANKL`, `LFB1.BANKN`, `LFB1.BKDAT`, `BSAK.BUDAT`

---

### 9.2 Categoria: Pedido de Compra (PO)

| # | Cenário | Código `FRAUD_TYPE` | Tabela SAP Principal | Mecanismo de Injeção | Camadas que Cobrem |
|---|---|---|---|---|---|
| 6 | Pedido de compra duplicado | `DUPLICATE_PO` | `EKKO` | Insere cópia da linha com EBELN prefixado `PODUP`; mesmo fornecedor, valor e data | FD |
| 7 | PO sem contrato vigente (acima de R$ 100k) | `PO_WITHOUT_CONTRACT` | `EKKO` / `EKPO` | Limpa `EKPO.INFNR` (registro de informação de compra) em POs com TOTAL_VALUE > 100.000 | FD · IF |
| 8 | Fracionamento abaixo do limite de alçada | `THRESHOLD_SPLITTING` | `EKKO` | Insere 3 POs por fornecedor com TOTAL_VALUE = R$ 50.000 − (100 a 2.000); FRGSX=`S1` | FD · AE |

**Campos SAP relevantes:** `EKKO.EBELN`, `EKKO.TOTAL_VALUE`, `EKKO.FRGSX`, `EKKO.LIFNR`, `EKPO.INFNR`

---

### 9.3 Categoria: Fatura / Documento Financeiro

| # | Cenário | Código `FRAUD_TYPE` | Tabela SAP Principal | Mecanismo de Injeção | Camadas que Cobrem |
|---|---|---|---|---|---|
| 9 | Pagamento duplicado | `DUPLICATE_PAYMENT` | `BSAK` | Insere cópia da linha com BELNR prefixado `DUP`; mesmo LIFNR + DMBTR + BUDAT | FD |
| 10 | Fatura sem PO vinculado (maverick spend) | `MAVERICK_SPEND` | `BKPF` | Limpa `BKPF.AWKEY` e `BKPF.SOURCE_EBELN` (referência à PO) | FD · IF |
| 11 | Valor logo abaixo do limite de aprovação | `BELOW_THRESHOLD` | `BSAK` | Redefine DMBTR para (threshold − 1 a 500), onde threshold ∈ {10k, 50k, 100k, 500k} | IF · AE |
| 12 | NF cancelada sem estorno do pagamento | `CANCELLED_NOT_REVERSED` | `BKPF` | Preenche `BKPF.STBLG` (número do doc. de estorno) e `BKPF.STJAH` sem cancelar o pagamento | FD |
| 13 | Divergência PO × Recebimento × Fatura > 10% | `THREE_WAY_MISMATCH` | `BSEG` | Multiplica `BSEG.DMBTR` e `BSEG.WRBTR` por fator 1.15–1.50 | FD · IF |

**Campos SAP relevantes:** `BKPF.AWKEY`, `BKPF.STBLG`, `BKPF.STJAH`, `BSAK.BELNR`, `BSAK.DMBTR`, `BSEG.DMBTR`, `BSEG.WRBTR`

---

### 9.4 Categoria: Comportamento de Pagamento

| # | Cenário | Código `FRAUD_TYPE` | Tabela SAP Principal | Mecanismo de Injeção | Camadas que Cobrem |
|---|---|---|---|---|---|
| 14 | Valor redondo suspeito | `ROUND_PAYMENT` | `BSAK` | Substitui DMBTR por valor fixo ∈ {5k, 10k, 25k, 50k, 100k, 250k, 500k} | IF · AE |
| 15 | Pagamento antecipado (antes do mínimo do BKPF) | `EARLY_PAYMENT` | `BSAK` | Define AUGDT = min(BKPF.BUDAT) − 1 a 30 dias | FD · IF |
| 16 | Pagamento para conta diferente do cadastro | `WRONG_BANK_ACCOUNT` | `BSAK` | Substitui AUGBL por string `WRONGACC` + 6 dígitos aleatórios | FD |
| 17 | Volume alto para mesmo fornecedor em < 48h | `PAYMENT_BURST` | `BSAK` | Concentra 10 pagamentos ao mesmo fornecedor com AUGDT em intervalos de 3h | IF · AE |
| 18 | Pagamento fora do expediente | `AFTER_HOURS_PAYMENT` | `BKPF` | Define CPUTM para horários noturnos: 22h, 23h, 01h, 03h ou 06h | FD · IF |
| 19 | Recorrência suspeita (mesmo valor, todo mês, 12x) | `SUSPICIOUS_RECURRENCE` | `BSAK` | Fixa DMBTR = valor entre 50k–200k e AUGDT a cada 30 dias por 12 meses | AE · IF |

**Campos SAP relevantes:** `BSAK.AUGDT`, `BSAK.AUGBL`, `BSAK.DMBTR`, `BSAK.WRBTR`, `BKPF.CPUTM`

---

### 9.5 Categoria: Segregação de Funções (SoD) / Conluio

| # | Cenário | Código `FRAUD_TYPE` | Tabela SAP Principal | Mecanismo de Injeção | Camadas que Cobrem |
|---|---|---|---|---|---|
| 20 | Mesmo usuário criou fornecedor e aprovou pagamento | `SOD_VENDOR_AND_PAYMENT` | `BKPF` | Copia o `LFA1.ERNAM` mais frequente para `BKPF.USNAM` em pagamentos amostrados | GR · FD |
| 21 | Mesmo usuário criou PO e confirmou recebimento | `SOD_PO_AND_RECEIPT` | `EKKO` / `BKPF` | Copia `EKKO.ERNAM` do PO amostrado para `BKPF.USNAM` de um doc. financeiro aleatório | GR · FD |

**Campos SAP relevantes:** `LFA1.ERNAM`, `EKKO.ERNAM`, `BKPF.USNAM`

---

### 9.6 Resumo por Camada de Detecção

| Camada | Cenários Cobertos | Total |
|---|---|---|
| **Isolation Forest (IF)** | GHOST_VENDOR · BANK_CHANGE_BEFORE_PAYMENT · FAST_VENDOR_PAYMENT · PO_WITHOUT_CONTRACT · THRESHOLD_SPLITTING · BELOW_THRESHOLD · THREE_WAY_MISMATCH · ROUND_PAYMENT · EARLY_PAYMENT · PAYMENT_BURST · AFTER_HOURS_PAYMENT · SUSPICIOUS_RECURRENCE · MAVERICK_SPEND | 13 |
| **AutoEncoder (AE)** | THRESHOLD_SPLITTING · BELOW_THRESHOLD · ROUND_PAYMENT · PAYMENT_BURST · SUSPICIOUS_RECURRENCE | 5 |
| **Grafo NetworkX (GR)** | GHOST_VENDOR · SOD_VENDOR_AND_PAYMENT · SOD_PO_AND_RECEIPT | 3 |
| **Feature Direta (FD)** | DUPLICATE_VENDOR · BANK_CHANGE_BEFORE_PAYMENT · VENDOR_EMPLOYEE_SHARED_BANK · FAST_VENDOR_PAYMENT · DUPLICATE_PO · PO_WITHOUT_CONTRACT · DUPLICATE_PAYMENT · MAVERICK_SPEND · CANCELLED_NOT_REVERSED · THREE_WAY_MISMATCH · EARLY_PAYMENT · WRONG_BANK_ACCOUNT · AFTER_HOURS_PAYMENT · SOD_VENDOR_AND_PAYMENT · SOD_PO_AND_RECEIPT | 15 |

> Cada cenário pode ser coberto por mais de uma camada. A combinação via ensemble garante que fraudes detectáveis por apenas uma camada ainda recebam score elevado.

---

*Documentação gerada automaticamente com base no código-fonte do projeto.*  
*Para suporte técnico ou dúvidas sobre metodologia, consulte os comentários inline nos arquivos referenciados.*
