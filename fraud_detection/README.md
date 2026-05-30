# SAP P2P Fraud Detection System

Sistema enterprise de detecção de fraude e anomalia financeira no fluxo **Procure to Pay (P2P)**, construído sobre dados sintéticos que simulam tabelas reais do SAP. Pronto para substituição por dados SAP reais em produção.

---

## Arquitetura

```
fraud_detection/
├── data/
│   ├── generators/         # Geração de dados SAP sintéticos + injeção de fraude
│   │   ├── schemas.py      # Definições de campos de todas as 13 tabelas SAP
│   │   ├── sap_tables.py   # Gerador coerente de dados SAP (plug & play para produção)
│   │   └── fraud_injector.py  # 21 cenários de fraude com taxa configurável (1–3%)
│   ├── raw/                # Tabelas SAP em Parquet (geradas)
│   └── processed/          # Alertas, feedback, contestações
├── models/
│   ├── isolation_forest.py # Isolation Forest (scikit-learn)
│   ├── autoencoder.py      # AutoEncoder (PyTorch)
│   ├── graph_analysis.py   # Análise de grafo (NetworkX) — SoD + conluio
│   ├── ensemble.py         # Ensemble ponderado dos 3 detectores
│   └── registry/           # Artefatos de modelo (.pkl) + hashes
├── api/
│   ├── main.py             # FastAPI — entry point
│   ├── auth/rbac.py        # JWT + RBAC (analista, gestor, auditor)
│   └── routers/            # alerts, feedback, models, export, contestation
├── explainer/
│   ├── shap_explainer.py   # SHAP values para Isolation Forest
│   └── claude_narrator.py  # Claude API → narrativas PT-BR por alerta
├── dashboard/
│   └── powerbi/star_schema.py  # Esquema estrela (fact + dims) para Power BI
├── governance/
│   ├── audit_log.py        # AUDIT_LOG.json com cadeia de hashes SHA-256
│   ├── model_versioning.py # Registro de versões com fluxo approve/reject
│   ├── data_drift.py       # PSI + KS test para detecção de drift
│   ├── alert_contestation.py  # Processo de contestação de alertas
│   └── lgpd_policy.md      # Política de privacidade LGPD
├── catalog/
│   └── data_catalog.json   # Catálogo completo: tipo, origem, sensibilidade
├── mlops/
│   └── pipeline.py         # Pipeline end-to-end orquestrando todas as etapas
├── tests/
│   ├── unit/               # Testes unitários: geradores, modelos, API
│   └── integration/        # Testes de integração: pipeline completo
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Tabelas SAP Simuladas

| Tabela | Módulo | Descrição |
|--------|--------|-----------|
| BKPF | FI | Cabeçalho do Documento Contábil |
| BSEG | FI | Segmento do Documento Contábil |
| BSAK | FI | Índice Sec. Fornecedores — Itens Compensados |
| BSID | FI | Índice Sec. Clientes — Itens em Aberto |
| LFA1 | MM | Mestre de Fornecedores (Geral) |
| LFB1 | MM | Mestre de Fornecedores (Dados da Empresa) |
| T001 | Org | Empresas |
| T001W | Org | Centros / Plantas |
| EKKO | MM | Cabeçalho do Pedido de Compra |
| EKPO | MM | Item do Pedido de Compra |
| EKKN | MM | Imputação Contábil do Pedido |
| MARA | MM | Mestre de Materiais (Geral) |
| MARC | MM | Mestre de Materiais (Centro) |

---

## Cenários de Fraude (21 tipos)

### Cadastro de Fornecedor
- `GHOST_VENDOR` — Fornecedor fantasma
- `DUPLICATE_VENDOR` — CNPJ duplicado com nome levemente diferente
- `BANK_CHANGE_BEFORE_PAYMENT` — Dados bancários alterados < 7 dias antes do pagamento
- `VENDOR_EMPLOYEE_SHARED_BANK` — Banco/conta compartilhado com funcionário
- `FAST_VENDOR_PAYMENT` — Cadastrado e pago em < 3 dias

### Pedido de Compra
- `DUPLICATE_PO` — PO duplicado (mesmo fornecedor/valor/data)
- `PO_WITHOUT_CONTRACT` — Compra sem info record / contrato
- `THRESHOLD_SPLITTING` — Fracionamento para fugir do limite de alçada

### Fatura
- `DUPLICATE_PAYMENT` — Mesmo documento pago duas vezes
- `MAVERICK_SPEND` — Fatura sem PO vinculado
- `BELOW_THRESHOLD` — Valor logo abaixo do limite (Lei de Benford)
- `CANCELLED_NOT_REVERSED` — NF cancelada sem estorno do pagamento
- `THREE_WAY_MISMATCH` — Divergência > 10% entre PO, recebimento e fatura

### Pagamento
- `ROUND_PAYMENT` — Valor redondo sem justificativa
- `EARLY_PAYMENT` — Pagamento antecipado
- `WRONG_BANK_ACCOUNT` — Pagamento para conta diferente do cadastro
- `PAYMENT_BURST` — Volume alto de pagamentos em 48h
- `AFTER_HOURS_PAYMENT` — Pagamento fora do horário comercial
- `SUSPICIOUS_RECURRENCE` — Mesmo valor mensal ao mesmo fornecedor

### SoD / Conluio
- `SOD_VENDOR_AND_PAYMENT` — Mesmo usuário criou fornecedor e aprovou pagamento
- `SOD_PO_AND_RECEIPT` — Mesmo usuário criou PO e aprovou recebimento

---

## Quick Start

### 1. Pré-requisitos

```bash
python 3.11+
docker & docker-compose (opcional)
```

### 2. Instalação local

```bash
cd fraud_detection
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configuração

```bash
cp .env.example .env
# Edite .env e insira ANTHROPIC_API_KEY e JWT_SECRET_KEY
```

### 4. Rodar o pipeline

```bash
python mlops/pipeline.py
```

Isso vai:
1. Gerar dados SAP sintéticos (300 fornecedores, 2000 POs, 2500 faturas)
2. Injetar 21 tipos de fraude (~2% dos registros)
3. Treinar Isolation Forest + AutoEncoder + grafo NetworkX
4. Calcular SHAP values
5. Gerar narrativas via Claude API (opcional — requer `ANTHROPIC_API_KEY`)
6. Salvar alertas em `data/processed/alerts.parquet`
7. Exportar esquema estrela para Power BI

### 5. Rodar a API

```bash
uvicorn api.main:app --reload --port 8000
# Docs: http://localhost:8000/docs
```

### 6. Docker

```bash
# API only
docker-compose up api

# Rodar pipeline dentro do Docker
docker-compose --profile pipeline up pipeline

# Rodar testes
docker-compose --profile test up tests
```

### 7. Testes

```bash
pytest tests/ -v
```

---

## API — Endpoints Principais

| Método | Endpoint | Permissão | Descrição |
|--------|----------|-----------|-----------|
| POST | `/auth/token` | — | Login, retorna JWT |
| GET | `/alerts` | analista | Lista alertas com paginação e filtros |
| GET | `/alerts/{id}` | analista | Detalhe de um alerta |
| POST | `/feedback` | analista | Marcar alerta como TP/FP |
| GET | `/feedback/stats` | analista | Taxa de precisão estimada |
| GET | `/models` | gestor | Listar versões de modelo |
| POST | `/models/approve` | gestor | Aprovar/rejeitar versão |
| GET | `/models/drift/report` | gestor | Relatório de data drift |
| POST | `/export/alerts` | gestor | Exportar alertas (CSV/JSON/Parquet) |
| GET | `/export/powerbi/star-schema` | gestor | Gerar esquema estrela para Power BI |
| GET | `/export/audit-log` | auditor | Log de auditoria completo |
| POST | `/contestations` | analista | Contestar um alerta |
| PATCH | `/contestations/{id}/resolve` | auditor | Resolver contestação |

---

## RBAC — Perfis de Acesso

| Permissão | analista | gestor | auditor |
|-----------|:---:|:---:|:---:|
| Ler alertas | ✓ | ✓ | ✓ |
| Submeter feedback | ✓ | ✓ | ✓ |
| Ver versões de modelo | — | ✓ | ✓ |
| Aprovar modelo | — | ✓ | ✓ |
| Exportar dados | — | ✓ | ✓ |
| Ler log de auditoria | — | — | ✓ |
| Resolver contestações | — | — | ✓ |

---

## Power BI — Esquema Estrela

```
fact_alerts ──── dim_vendor      (vendor_key)
            ──── dim_time        (date_key)
            ──── dim_fraud_type  (fraud_type_key)
            ──── dim_model       (model_key)
```

Os arquivos Parquet são gerados em `data/processed/exports/pbi_*.parquet`.  
No Power BI Desktop: **Obter Dados → Pasta → selecionar a pasta exports**.

---

## Migração para SAP Real

1. Abra `data/generators/sap_tables.py`
2. Implemente `SAPDataGenerator._load_from_sap()` usando `pyrfc` (SAP RFC) ou `hdbcli` (SAP HANA)
3. Substitua `generate_all()` para chamar `_load_from_sap()` para cada tabela
4. Revise a política LGPD em `governance/lgpd_policy.md`
5. Configure `ANTHROPIC_API_KEY` em produção

**Nenhum outro arquivo precisa ser alterado.**

---

## Governança e Compliance

- **AUDIT_LOG.json** — cadeia de hashes SHA-256 (imutável, verificável)
- **model_versions.json** — fluxo de aprovação pending → approved/rejected
- **drift_reports/** — PSI + KS test por feature, relatório cronológico
- **contestations.jsonl** — processo de contestação com resolução rastreada
- **lgpd_policy.md** — política de privacidade para dados fictícios e produção

---

## Licença

MIT — uso livre para fins comerciais e educacionais.  
Dados gerados são completamente fictícios — qualquer semelhança com dados reais é coincidência.
