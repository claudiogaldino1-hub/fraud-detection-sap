# SAP P2P Fraud Detection System

![Pipeline](https://img.shields.io/badge/pipeline-passing-2ec4b6?style=flat-square&logo=github-actions&logoColor=white)
![Python](https://img.shields.io/badge/python-3.12-457b9d?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-a8dadc?style=flat-square)
![SAP P2P](https://img.shields.io/badge/SAP-P2P%20Procure--to--Pay-0070f3?style=flat-square)
![Claude API](https://img.shields.io/badge/Claude%20API-claude--sonnet--4--5-6a4c93?style=flat-square)

**[▶ Abrir Dashboards ao Vivo](https://claudiogaldino1-hub.github.io/fraud-detection-sap/)** — nenhuma instalação necessária.

---

> [!WARNING]
> **Segurança — leia antes de clonar ou abrir em Claude Code**
>
> **CVE-2025-59536** (CVSS 8.8 · HIGH) — Claude Code < 1.0.111 permite injeção de código via bypass do diálogo de confiança ao abrir projetos.
> **CVE-2026-21852** (CVSS 7.5 · HIGH) — Claude Code < 2.0.65 pode exfiltrar `ANTHROPIC_API_KEY` ao carregar repositórios maliciosos antes do diálogo de confiança.
>
> ✅ **Mitigation:** mantenha Claude Code atualizado para a versão mais recente.
> Nunca armazene chaves reais em arquivos do projeto. Use `.env` (já no `.gitignore`).
> Configure sua chave apenas via variável de ambiente: `set ANTHROPIC_API_KEY=sk-ant-...`
>
> Referências: [CVE-2025-59536](https://nvd.nist.gov/vuln/detail/CVE-2025-59536) · [CVE-2026-21852](https://nvd.nist.gov/vuln/detail/CVE-2026-21852)

---

## O que é este projeto?

Sistema enterprise de **detecção de fraude e anomalia financeira** no fluxo **Procure-to-Pay (P2P)** do SAP ERP. O P2P cobre todo o ciclo de uma compra — do cadastro do fornecedor até o pagamento da fatura — e é historicamente o processo com maior exposição a fraudes corporativas: fornecedores fantasma, duplicidade de pagamento, quebra de alçada e conluio entre compradores e fornecedores.

O sistema foi projetado para rodar sobre dados reais do SAP (tabelas FI e MM) com uma única alteração de configuração, e já inclui **todos os artefatos prontos para uso**: dashboards HTML que abrem direto no browser, relatório Excel com três abas, painel de auditoria com semáforo de integridade SHA-256 e relatório executivo em uma página para gestores.

### Para quem é?

| Perfil | Como usa o sistema |
|---|---|
| **Auditor Interno** | Abre `audit_dashboard.html` para verificar integridade, revisa alertas HIGH via `alerts_report.xlsx` |
| **Gestor / Controller** | Abre `executive_report.html` para ver o resumo de um run em 30 segundos |
| **Analista de Fraude** | Trabalha no `dashboard.html` com os top 20 alertas, scores SHAP e tipos de fraude |
| **Equipe de TI / DevOps** | Roda o pipeline, verifica `cost_dashboard.html`, aprova modelos via API REST |

---

## Arquitetura

O pipeline executa **15 etapas** (Step 0 — auditoria de segurança até Step 14 — versionamento de docs), cobrindo desde a geração dos dados até a publicação dos relatórios:

```
Dados SAP (sintéticos ou reais via RFC/HANA)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  DETECÇÃO (3 camadas em paralelo)                               │
│                                                                  │
│  Isolation Forest  ──┐                                          │
│  (scikit-learn)      │                                          │
│                      ├──► Ensemble Score ──► risk_tier          │
│  AutoEncoder         │    (35% + 35% + 30%)   HIGH/MED/LOW      │
│  (PyTorch)           │                                          │
│                      │                                          │
│  Grafo NetworkX  ────┘                                          │
│  (SoD + conluio)                                                 │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  EXPLICABILIDADE & NARRATIVA                                     │
│  SHAP values  ──►  Claude API  ──►  Narrativa PT-BR por alerta  │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOVERNANÇA                                                      │
│  SHA-256 checksums · Audit log com hash chain · Data drift      │
│  Versionamento de modelos · LGPD · Cost monitor                 │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  RELATÓRIOS (gerados automaticamente)                            │
│  dashboard.html · audit_dashboard.html · executive_report.html  │
│  cost_dashboard.html · alerts_report.xlsx                        │
└─────────────────────────────────────────────────────────────────┘
```

**Tabelas SAP monitoradas (P2P):** `BKPF · BSEG · BSAK · BSID · LFA1 · LFB1 · T001 · T001W · EKKO · EKPO · EKKN · MARA · MARC`

**21 cenários de fraude** injetados a ~2% via `FraudInjector` (`data/generators/fraud_injector.py`).

---

## Cenários de Fraude Detectados

O sistema cobre **21 cenários** em 5 categorias. A tabela abaixo mapeia cada um ao código interno (`FRAUD_TYPE`), à tabela SAP afetada e à camada de detecção responsável.

**Legenda de camadas:** `IF` = Isolation Forest · `AE` = AutoEncoder · `GR` = Grafo NetworkX · `FD` = Feature Direta (regra determinística)

| # | Cenário | Código `FRAUD_TYPE` | Categoria | Tabela SAP principal | Camada |
|---|---|---|---|---|---|
| 1 | Fornecedor fantasma (criado sem histórico, pago imediatamente) | `GHOST_VENDOR` | Cadastro | `LFA1` | IF · GR |
| 2 | CNPJ duplicado com nome levemente diferente | `DUPLICATE_VENDOR` | Cadastro | `LFA1` | FD |
| 3 | Dados bancários alterados 1–7 dias antes do pagamento | `BANK_CHANGE_BEFORE_PAYMENT` | Cadastro | `LFB1` | FD · IF |
| 4 | Conta bancária do fornecedor coincide com a de funcionário interno | `VENDOR_EMPLOYEE_SHARED_BANK` | Cadastro | `LFB1` | FD |
| 5 | Fornecedor criado e pago em menos de 3 dias | `FAST_VENDOR_PAYMENT` | Cadastro | `BSAK` | FD · IF |
| 6 | PO duplicado (mesmo fornecedor, valor e data) | `DUPLICATE_PO` | Pedido de Compra | `EKKO` | FD |
| 7 | PO acima de R$ 100k sem contrato vigente (INFNR em branco) | `PO_WITHOUT_CONTRACT` | Pedido de Compra | `EKKO` / `EKPO` | FD · IF |
| 8 | Compra fracionada em múltiplos POs abaixo de R$ 50k | `THRESHOLD_SPLITTING` | Pedido de Compra | `EKKO` | FD · AE |
| 9 | Pagamento duplicado (mesmo LIFNR + DMBTR + BUDAT) | `DUPLICATE_PAYMENT` | Fatura | `BSAK` | FD |
| 10 | Fatura sem PO vinculado — AWKEY/EBELN em branco | `MAVERICK_SPEND` | Fatura | `BKPF` | FD · IF |
| 11 | Valor logo abaixo de limite de aprovação (R$ 10k / 50k / 100k / 500k) | `BELOW_THRESHOLD` | Fatura | `BSAK` | IF · AE |
| 12 | NF cancelada (STBLG preenchido) com pagamento não estornado | `CANCELLED_NOT_REVERSED` | Fatura | `BKPF` | FD |
| 13 | Divergência > 10% entre PO, recebimento e fatura (3-way match) | `THREE_WAY_MISMATCH` | Fatura | `BSEG` | FD · IF |
| 14 | Valor redondo suspeito (R$ 5k, 10k, 25k, 50k, 100k…) | `ROUND_PAYMENT` | Pagamento | `BSAK` | IF · AE |
| 15 | Pagamento com data anterior ao mínimo do BKPF | `EARLY_PAYMENT` | Pagamento | `BSAK` | FD · IF |
| 16 | Pagamento direcionado a conta diferente do cadastro (AUGBL divergente) | `WRONG_BANK_ACCOUNT` | Pagamento | `BSAK` | FD |
| 17 | 10+ pagamentos ao mesmo fornecedor em menos de 48h | `PAYMENT_BURST` | Pagamento | `BSAK` | IF · AE |
| 18 | Processamento fora do expediente (antes 08h ou após 18h — CPUTM) | `AFTER_HOURS_PAYMENT` | Pagamento | `BKPF` | FD · IF |
| 19 | Mesmo valor para o mesmo fornecedor todo mês por 12 meses | `SUSPICIOUS_RECURRENCE` | Pagamento | `BSAK` | AE · IF |
| 20 | Mesmo usuário cadastrou o fornecedor e aprovou o pagamento | `SOD_VENDOR_AND_PAYMENT` | SoD / Conluio | `BKPF` | GR · FD |
| 21 | Mesmo usuário criou o PO e aprovou o pagamento ao mesmo fornecedor | `SOD_PO_AND_RECEIPT` | SoD / Conluio | `EKKO` / `BKPF` | GR · FD |

> Mapeamento detalhado com mecanismo de injeção campo a campo: **[Capítulo 9 — Catálogo Detalhado de Cenários de Fraude](docs/TECHNICAL_DOCUMENTATION.md#9-catálogo-detalhado-de-cenários-de-fraude)**.

---

## Como rodar

> **Pré-requisito:** Python 3.11+ instalado. Todos os comandos abaixo são para **Windows CMD**.

### 1 — Navegue para a pasta do projeto

```cmd
cd C:\caminho\para\meu_portifolio\fraud_detection
```

### 2 — Configure o ambiente (apenas uma vez)

```cmd
pip install -r requirements.txt
```

### 3 — Configure as variáveis de ambiente

```cmd
set PYTHONPATH=C:\caminho\para\meu_portifolio\fraud_detection
set PYTHONUTF8=1
```

> **Opcional — narrativas em português via Claude API:**
> ```cmd
> set ANTHROPIC_API_KEY=sk-ant-...
> ```

### 4 — Execute o pipeline completo

```cmd
python mlops/pipeline.py
```

O pipeline executa 14 steps automaticamente e gera todos os relatórios:

```
Step  0  Auditoria de segurança (bloqueia se detectar credencial exposta)
Step  1  Gerar dados SAP (13 tabelas, 2.000 POs, ~2.500 faturas)
Step  2  Injetar 21 cenários de fraude (~2% dos registros)
Step  3  Treinar ensemble (Isolation Forest + AutoEncoder + NetworkX)
Step  4  Inferência — gerar scores e risk tiers
Step  5  Calcular SHAP values (explicabilidade)
Step  6  Narrativas via Claude API (skipped sem ANTHROPIC_API_KEY)
Step  7  Baseline de data drift
Step  8  Persistir alertas em data/processed/alerts.parquet
Step  9  Relatório de custos (compute + storage + Claude API)
Step 10  Checksums SHA-256 dos artefatos críticos
Step 11  Atualizar CHANGELOG.md e enriquecer audit log
Step 12  Gerar audit_dashboard.html
Step 13  Gerar executive_report.html
Step 14  Versionar documentação técnica
```

### 5 — Abra os relatórios

```cmd
start reports\dashboard.html
start reports\executive_report.html
start reports\audit_dashboard.html
start reports\cost_dashboard.html
start reports\alerts_report.xlsx
```

### 6 — Suba a API REST (opcional)

```cmd
python -m uvicorn api.main:app --reload --port 8000
```

Acesse `http://localhost:8000/docs` para a interface Swagger interativa.

**Credenciais de teste:**

| Usuário | Senha | Perfil |
|---|---|---|
| `ana.analista` | `analista123` | Analista |
| `gabriel.gestor` | `gestor123` | Gestor |
| `arthur.auditor` | `auditor123` | Auditor |

### 7 — Docker (alternativa)

```cmd
docker-compose --profile pipeline up pipeline
docker-compose --profile api up api
docker-compose --profile test up tests
```

---

## Dashboards

> **[▶ Abrir todos os dashboards](https://claudiogaldino1-hub.github.io/fraud-detection-sap/)** — página pública, nenhuma instalação necessária.

Quatro painéis HTML gerados automaticamente pelo pipeline — abra qualquer um diretamente no browser, sem servidor:

### 📊 `reports/dashboard.html` — Para analistas de fraude

Painel principal de alertas com dados do último run embutidos inline. Mostra KPIs de resumo, gráfico de barras por tipo de fraude, histograma de scores, tabela dos top 20 alertas mais críticos e o gráfico de importância SHAP com explicações em português por feature.

```cmd
start reports\dashboard.html
```

### 📋 `reports/executive_report.html` — Para gestores e diretores

Uma página só, sem tecnicismo. Semáforo grande no topo (✅ OK / ⚠️ ATENÇÃO / 🚨 CRÍTICO), frase resumo gerada automaticamente, distribuição de alertas por risco com barras de proporção e custo do run. Ideal para ser aberto antes de uma reunião de resultados.

```cmd
start reports\executive_report.html
```

### 🛡️ `reports/audit_dashboard.html` — Para auditores e compliance

Semáforo de integridade por componente (Modelos ML · Dados · Governança), timeline de todos os runs com autor/hostname/commit/custo, tabela completa de checksums SHA-256 com status ÍNTEGRO/AUSENTE/ADULTERADO e contagem de ações no audit log.

```cmd
start reports\audit_dashboard.html
```

### 💸 `reports/cost_dashboard.html` — Para equipes de FinOps e TI

Histórico de custo por run (gráfico de linha), breakdown por dimensão (compute · storage · Claude API), detalhamento por etapa do pipeline, projeção mensal para 100 runs com e sem narrativas.

```cmd
start reports\cost_dashboard.html
```

> Todos os dashboards já estão prontos no repositório e refletem o último run do pipeline. Para atualizar após um novo run, basta executar `python mlops/pipeline.py` — todos são regenerados automaticamente no Step 12/13.

---

## Estrutura do projeto

```
fraud_detection/
│
├── data/generators/          # Geração de dados SAP + injeção de fraude
│   ├── sap_tables.py         ← substitua _load_from_sap() para SAP real
│   ├── fraud_injector.py     # 21 cenários, taxa configurável (~2%)
│   └── schemas.py            # Tipos, sensibilidade LGPD por campo
│
├── models/                   # Os três detectores + ensemble
│   ├── isolation_forest.py   # scikit-learn + feature engineering
│   ├── autoencoder.py        # PyTorch, latent_dim=4, percentile 97
│   ├── graph_analysis.py     # NetworkX — SoD + conluio
│   ├── ensemble.py           # 35% IF + 35% AE + 30% Grafo
│   └── registry/             # Modelos .pkl versionados com SHA-256
│
├── explainer/
│   ├── shap_explainer.py     # SHAP TreeExplainer (português)
│   └── claude_narrator.py    # Claude API → narrativa PT-BR por alerta
│
├── api/
│   ├── main.py               # FastAPI
│   ├── auth/rbac.py          # JWT + RBAC (analista/gestor/auditor)
│   └── routers/              # alerts, feedback, models, export, contestation
│
├── governance/
│   ├── audit_log.py          # Hash chain SHA-256 (append-only)
│   ├── integrity.py          # Checksums + detecção de adulteração
│   ├── cost_monitor.py       # Compute + storage + Claude API em USD
│   ├── model_versioning.py   # Aprovação de modelos (pending→approved)
│   ├── data_drift.py         # PSI + KS test por feature
│   └── lgpd_policy.md        # Política LGPD (base legal Art. 10)
│
├── mlops/
│   └── pipeline.py           # Orquestrador 14 steps
│
├── scripts/                  # Geradores de relatórios e utilitários
│   ├── generate_dashboard.py
│   ├── generate_audit_dashboard.py
│   ├── generate_executive_report.py
│   ├── generate_cost_dashboard.py
│   ├── export_alerts.py
│   ├── update_changelog.py
│   └── version_docs.py
│
├── reports/                  # Saídas prontas para abertura no browser
│   ├── dashboard.html
│   ├── audit_dashboard.html
│   ├── executive_report.html
│   ├── cost_dashboard.html
│   └── alerts_report.xlsx
│
├── docs/
│   ├── TECHNICAL_DOCUMENTATION.md     # Documentação atual (versionada)
│   └── versions/                      # Histórico de versões da doc
│
├── tests/unit/               # 40+ testes unitários
├── tests/integration/        # Testes end-to-end + verificação hash chain
├── catalog/data_catalog.json # Catálogo: tipo, sensibilidade, origem
├── dashboard/powerbi/        # Esquema estrela para Power BI
├── CHANGELOG.md              # Gerado automaticamente pelo pipeline
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Governança e Auditoria

O sistema foi projetado para ambientes regulados, com rastreabilidade completa de cada run:

### 🔐 Integridade SHA-256

Todos os artefatos críticos (modelos `.pkl`, `alerts.parquet`, audit log, cost report) têm seu hash SHA-256 calculado e armazenado em `governance/checksums.json` a cada pipeline run. Qualquer adulteração — mesmo de um único byte — é detectada na próxima execução.

```
governance/checksums.json  →  18 arquivos monitorados
governance/AUDIT_LOG.json  →  hash chain imutável (adulteração detectável)
```

### 📋 Rastreabilidade completa por run

O `CHANGELOG.md` e o `AUDIT_LOG.json` registram automaticamente:

- **Identidade:** autor (nome + email do git config), usuário do SO, hostname da máquina
- **Código:** hash do commit, branch, mensagem do commit, arquivos críticos alterados
- **Resultado:** alertas gerados, custo breakdown (compute · storage · Claude API)
- **Integridade:** tabela de checksums SHA-256 dos artefatos do run

### 🤖 Versionamento de Modelos

Nenhum modelo entra em produção sem aprovação explícita. Fluxo:
```
Treinar → Registrar (hash) → Revisar → Aprovar/Rejeitar → Promover
```

Modelos rejeitados são mantidos no registro para auditoria futura.

### 📊 Detecção de Data Drift

A cada run, o sistema compara a distribuição das features de entrada com o baseline de treinamento usando dois testes estatísticos:
- **PSI > 0.20** → drift severo → retreinamento necessário
- **KS test p < 0.05** → mudança de distribuição detectada

### 🇧🇷 LGPD

Campos classificados em quatro níveis: `PUBLIC · INTERNAL · CONFIDENTIAL · RESTRICTED`. Documentação completa em `governance/lgpd_policy.md` (base legal: Art. 10 LGPD — legítimo interesse para controle interno).

### 📖 Documentação Versionada

A documentação técnica é versionada automaticamente sempre que há mudança em `models/`, `mlops/`, `governance/` ou `scripts/`. Versões anteriores são preservadas em `docs/versions/`.

---

## Custo Operacional

Valores medidos em runs reais com dados sintéticos (pipeline ~3–4 segundos):

| Dimensão | Custo por run | Referência |
|---|---|---|
| **Processamento** | ~$0.000083 | AWS c6i.large (2 vCPU, 4 GB) |
| **Armazenamento** | ~$0.000274 | AWS S3 Standard (por mês) |
| **Claude API** | $0.00 sem narrativas | claude-sonnet-4-5 |
| **Claude API** | ~$0.012 com 20 narrativas | $3/1M input · $15/1M output |
| **Total (sem narrativas)** | **~$0.000357/run** | |
| **Total (com narrativas)** | **~$0.012/run** | |

**Projeção para 100 runs/mês:**

| Cenário | Custo mensal estimado |
|---|---|
| Sem narrativas | ~$0.035 |
| Com 20 narrativas por run | ~$1.23 |

> Os relatórios de custo são gerados automaticamente em `reports/cost_dashboard.html` e `governance/cost_report.json` a cada pipeline run.

---

## Migração para SAP Real

Apenas **um método** precisa ser implementado:

```python
# data/generators/sap_tables.py

def _load_from_sap(self) -> Dict[str, pd.DataFrame]:
    """
    Substitua este método pela conexão ao SAP real.
    Use pyrfc para SAP RFC ou hdbcli para SAP HANA.
    Retorne um dict {nome_tabela: DataFrame} com as mesmas colunas
    definidas em data/generators/schemas.py.
    """
    raise NotImplementedError("Implemente a conexão SAP aqui.")
```

**Nenhum outro arquivo precisa ser alterado.** Toda a stack de ML, governança e relatórios funciona automaticamente sobre os dados reais.

---

## Tabelas SAP Monitoradas

| Tabela | Módulo | Descrição |
|---|---|---|
| `BKPF` | FI | Cabeçalho do Documento Contábil |
| `BSEG` | FI | Segmento do Documento Contábil |
| `BSAK` | FI | Índice Secundário — Itens Compensados |
| `BSID` | FI | Índice Secundário — Itens em Aberto |
| `LFA1` | MM | Mestre de Fornecedores (Geral) |
| `LFB1` | MM | Mestre de Fornecedores (Dados da Empresa) |
| `T001` | Org | Empresas |
| `T001W` | Org | Centros / Plantas |
| `EKKO` | MM | Cabeçalho do Pedido de Compra |
| `EKPO` | MM | Item do Pedido de Compra |
| `EKKN` | MM | Imputação Contábil do Pedido |
| `MARA` | MM | Mestre de Materiais (Geral) |
| `MARC` | MM | Mestre de Materiais (Centro) |

---

## API REST — Endpoints Principais

| Método | Endpoint | Perfil mínimo | Descrição |
|---|---|---|---|
| `POST` | `/auth/token` | — | Login, retorna JWT |
| `GET` | `/alerts` | analista | Lista paginada com filtros |
| `POST` | `/alerts/{id}/feedback` | analista | Marcar TP / FP |
| `POST` | `/alerts/{id}/contest` | analista | Abrir contestação |
| `GET` | `/models` | gestor | Versões de modelo registradas |
| `POST` | `/models/{id}/approve` | gestor | Aprovar / rejeitar modelo |
| `GET` | `/export` | gestor | CSV / JSON / Parquet |
| `GET` | `/export/powerbi` | gestor | Esquema estrela para Power BI |
| `GET` | `/audit-log` | auditor | Log de auditoria completo |

Documentação interativa disponível em `http://localhost:8000/docs` após subir a API.

---

## Rodando os Testes

```cmd
set PYTHONPATH=C:\caminho\para\meu_portifolio\fraud_detection
python -m pytest tests/ -v
```

Cobertura: 40+ testes unitários (geradores, modelos, API, RBAC) e testes de integração (pipeline completo, verificação da hash chain do audit log).

---

## Licença

MIT — uso livre para fins comerciais e educacionais.
Todos os dados gerados são completamente fictícios. Qualquer semelhança com dados reais é coincidência.

---

<p align="center">
  Desenvolvido por <strong>Claudio Galdino</strong> &nbsp;|&nbsp;
  <a href="https://github.com/claudiogaldino1-hub/fraud-detection-sap">github.com/claudiogaldino1-hub/fraud-detection-sap</a>
</p>
