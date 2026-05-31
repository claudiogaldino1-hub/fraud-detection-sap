# CHANGELOG — SAP P2P Fraud Detection System

> Gerado automaticamente pelo pipeline. Cada entrada registra autoria, custo, alertas e checksums do run.

---


## 📖 [DOC v1.0] Documentacao atualizada — `dd52d10`

| Campo | Valor |
|---|---|
| **Versao** | `1.0` |
| **Data** | `2026-05-31 14:44 UTC` |
| **Autor** | Claudio Galdino <claudio.galdino1@gmail.com> |
| **Pipeline** | `a5189a1b` |
| **Arquivo** | `TECHNICAL_DOCUMENTATION_v1.0.md` |

Os seguintes componentes foram alterados desde a versão anterior:

- **models/**
- **mlops/**
- **governance/**
- **scripts/**
- **explainer/**
- **api/**

---

## 🚀 [2026-05-31] PIPELINE_RUN — pipeline `a5189a1b`

| Campo            | Valor |
|------------------|-------|
| **Data/hora**    | `2026-05-31 14:44:16 UTC` |
| **Autor**        | Claudio Galdino &lt;claudio.galdino1@gmail.com&gt; |
| **Usuário SO**   | `claud` @ `Claudio` |
| **Commit**       | `dd52d10` — feat: implement full audit trail and data integrity system |
| **Branch**       | `master` |
| **Hash completo**| `dd52d10d5f46318aff787392eaabae8ab9193dfd` |
| **Alertas**      | 420 |
| **Custo total**  | `$0.000357` USD |
| **Compute**      | `$0.000083` (AWS EC2) |
| **Armazenamento**| `$0.000274` (S3/mês) |
| **Claude API**   | `$0.000000` |

### Arquivos críticos alterados neste run

- 🛡️ `governance/checksums.json` — adicionado (governanca)
- 🛡️ `governance/integrity.py` — adicionado (governanca)
- ⚙️ `mlops/pipeline.py` — modificado (pipeline)

### Checksums SHA-256 dos artefatos críticos

| Arquivo | SHA-256 (primeiros 32 chars) |
|---------|------------------------------|
| `models/registry/autoencoder_104db464.pkl` | `9bea78e19a4067cb0cbcae98491f689b…` |
| `models/registry/autoencoder_3ce6f16b.pkl` | `7b904c669c04ff311605c1e4a28dfb4c…` |
| `models/registry/autoencoder_77e3e96f.pkl` | `a8f56bee3383bfe30a38d8b06837b6a4…` |
| `models/registry/autoencoder_a5189a1b.pkl` | `1c250fa9f6e0ad128148f02c3781a22b…` |
| `models/registry/autoencoder_bb67bc31.pkl` | `d7de87a3149aec9d155f7aec4d3a73fe…` |
| `models/registry/isolation_forest_104db464.pkl` | `9a4aa587170a1516a9757386e3942836…` |
| `models/registry/isolation_forest_3ce6f16b.pkl` | `06168d528cfbc70dba8744cdc5b70464…` |
| `models/registry/isolation_forest_77e3e96f.pkl` | `9a4aa587170a1516a9757386e3942836…` |
| `models/registry/isolation_forest_a5189a1b.pkl` | `9a4aa587170a1516a9757386e3942836…` |
| `models/registry/isolation_forest_bb67bc31.pkl` | `01c7f57579123e12f8709b20232c19ac…` |
| `data/processed/alerts.parquet` | `4487fad62f11996cde19ea891cbac664…` |
| `governance/AUDIT_LOG.json` | `08ca7d2b94f02b2fa024deca27a0b479…` |
| `governance/model_versions.json` | `60bf25acd62f582ce8a5da898d02a15a…` |
| `governance/cost_report.json` | `95cb5d0575ccc8d92f7699d36233da25…` |

---
## 🚀 [2026-05-31] PIPELINE_RUN — pipeline `77e3e96f`

| Campo            | Valor |
|------------------|-------|
| **Data/hora**    | `2026-05-31 14:31:57 UTC` |
| **Autor**        | Claudio Galdino &lt;claudio.galdino1@gmail.com&gt; |
| **Usuário SO**   | `claud` @ `Claudio` |
| **Commit**       | `7454dcf` — feat: add generated reports (dashboards + Excel) |
| **Branch**       | `master` |
| **Hash completo**| `7454dcf77d2f9658c4826022df9ec405936bc6bc` |
| **Alertas**      | 404 |
| **Custo total**  | `$0.000307` USD |
| **Compute**      | `$0.000081` (AWS EC2) |
| **Armazenamento**| `$0.000226` (S3/mês) |
| **Claude API**   | `$0.000000` |

### Checksums SHA-256 dos artefatos críticos

| Arquivo | SHA-256 (primeiros 32 chars) |
|---------|------------------------------|
| `models/registry/autoencoder_104db464.pkl` | `9bea78e19a4067cb0cbcae98491f689b…` |
| `models/registry/autoencoder_3ce6f16b.pkl` | `7b904c669c04ff311605c1e4a28dfb4c…` |
| `models/registry/autoencoder_77e3e96f.pkl` | `a8f56bee3383bfe30a38d8b06837b6a4…` |
| `models/registry/autoencoder_bb67bc31.pkl` | `d7de87a3149aec9d155f7aec4d3a73fe…` |
| `models/registry/isolation_forest_104db464.pkl` | `9a4aa587170a1516a9757386e3942836…` |
| `models/registry/isolation_forest_3ce6f16b.pkl` | `06168d528cfbc70dba8744cdc5b70464…` |
| `models/registry/isolation_forest_77e3e96f.pkl` | `9a4aa587170a1516a9757386e3942836…` |
| `models/registry/isolation_forest_bb67bc31.pkl` | `01c7f57579123e12f8709b20232c19ac…` |
| `data/processed/alerts.parquet` | `b21b9437086c2e316799d607c4cc5603…` |
| `governance/AUDIT_LOG.json` | `187b385c5e16a2731655d9e09692894d…` |
| `governance/model_versions.json` | `68ca25af9d61a97b21401e18e95e5aeb…` |
| `governance/cost_report.json` | `d557dbe8e0b4dbb836701bd7beebdf16…` |

---
