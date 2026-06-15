"""
generate_dashboard.py
Lê data/processed/alerts.parquet, computa valores SHAP reais a partir do
modelo Isolation Forest salvo, e gera reports/dashboard.html 100% standalone.

Uso:
    cd fraud_detection
    python scripts/generate_dashboard.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ALERTS_PATH  = ROOT / "data" / "processed" / "alerts.parquet"
MODEL_REGISTRY = ROOT / "models" / "registry"
OUT_PATH     = ROOT / "reports" / "dashboard.html"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── SHAP feature descriptions (SAP P2P context) ───────────────────────────
FEATURE_DESC = {
    "days_since_vendor_created": (
        "Fornecedor criado recentemente",
        "Dias entre o cadastro do fornecedor (LFA1.ERDAT) e o pagamento. "
        "Valores baixos indicam fornecedores cadastrados e pagos em janela curta — "
        "padrao classico de fornecedor fantasma ou cadastro fraudulento."
    ),
    "vendor_payment_count_30d": (
        "Volume de pagamentos em 30 dias",
        "Quantidade de documentos de pagamento (BSAK) para o mesmo fornecedor "
        "nos ultimos 30 dias. Picos suspeitos podem indicar fracionamento de pedido "
        "para fugir de alca de aprovacao ou conluio comprador-fornecedor."
    ),
    "DMBTR": (
        "Valor do pagamento (BRL)",
        "Valor contabil do documento de pagamento (BSEG.DMBTR em moeda local). "
        "Valores logo abaixo de limites de aprovacao (ex: R$49.999) sinalizam "
        'quebra de alca intencional. Valores redondos ativam o padrao "round amount".'
    ),
    "amount_deviation_from_vendor_mean": (
        "Desvio do valor em relacao ao historico do fornecedor",
        "Distancia padronizada entre o valor do pagamento e a media historica "
        "do mesmo fornecedor (z-score simplificado). Desvios altos indicam "
        "fatura atipica que pode representar superfaturamento ou pagamento duplicado."
    ),
    "WRBTR": (
        "Valor na moeda do documento",
        "Valor original do documento na moeda da transacao (BSEG.WRBTR). "
        "Divergencias entre WRBTR e DMBTR apos conversao podem indicar "
        "manipulacao de taxa de cambio ou fatura alterada."
    ),
    "hour_of_entry": (
        "Hora de lancamento no sistema",
        "Hora em que o documento foi registrado no SAP (BKPF.CPUTM). "
        "Lancamentos fora do horario comercial (antes das 8h ou apos 18h, "
        "fins de semana) sao indicadores de acesso nao autorizado ou pagamento "
        "realizado sem supervisao."
    ),
    "po_invoice_ratio": (
        "Relacao fatura vs. pedido de compra",
        "Razao entre o valor da fatura (DMBTR) e o valor do pedido de compra "
        "(WRBTR). Valores muito diferentes de 1.0 sinalizam falha no three-way match "
        "(PO x Recebimento x Fatura), podendo indicar superfaturamento ou "
        "maverick spend (compra sem PO vinculado)."
    ),
    "days_to_pay": (
        "Prazo de pagamento",
        "Dias entre a data de lancamento (BKPF.BUDAT) e a data de compensacao "
        "(BSAK.AUGDT). Valores negativos ou proximos de zero indicam pagamento "
        "antecipado sem justificativa — risco de cumplicidade com fornecedor."
    ),
    "is_round_amount": (
        "Valor redondo (flag)",
        "Flag binario (0/1) indicando se o valor corresponde a um montante "
        "redondo tipico (ex: R$ 5.000, R$ 50.000, R$ 100.000). Pagamentos "
        "redondos sem detalhamento de servicos sao anomalias classicas "
        "apontadas pela Lei de Benford e auditorias forenses."
    ),
}

# ── load alerts ────────────────────────────────────────────────────────────
print(f"Lendo {ALERTS_PATH} ...")
if not ALERTS_PATH.exists():
    sys.exit(f"ERRO: {ALERTS_PATH} nao encontrado. Rode o pipeline primeiro.")

df = pd.read_parquet(ALERTS_PATH)
df["risk_tier"]  = df["risk_tier"].astype(str)
df["FRAUD_TYPE"] = df["FRAUD_TYPE"].fillna("").astype(str)
for col in ["BLDAT", "BUDAT", "AUGDT"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

# ── compute real SHAP values ───────────────────────────────────────────────
print("Computando valores SHAP (Isolation Forest)...")
shap_features = []
try:
    import shap as shap_lib
    from data.generators import SAPDataGenerator
    from models.isolation_forest import (NUMERIC_FEATURES,
                                          IsolationForestDetector,
                                          _build_features)

    tables = SAPDataGenerator.load_all()
    bsak, bkpf, lfa1 = tables["BSAK"], tables["BKPF"], tables["LFA1"]
    feat_df = _build_features(bsak, bkpf, lfa1)
    X = feat_df[NUMERIC_FEATURES].fillna(0).values

    if_pkls = sorted(MODEL_REGISTRY.glob("isolation_forest*.pkl"))
    if not if_pkls:
        raise FileNotFoundError("Nenhum modelo isolation_forest*.pkl encontrado.")
    det = IsolationForestDetector.load(if_pkls[-1].stem)

    X_scaled = det.scaler.transform(X)
    n_shap = min(20, len(X_scaled))
    explainer = shap_lib.TreeExplainer(det.model)
    sv = explainer.shap_values(X_scaled[:n_shap])
    mean_abs = np.abs(sv).mean(axis=0)

    for i, feat in enumerate(NUMERIC_FEATURES):
        meta = FEATURE_DESC.get(feat, (feat, ""))
        shap_features.append({
            "feature":     feat,
            "label":       meta[0],
            "description": meta[1],
            "importance":  round(float(mean_abs[i]), 5),
        })
    shap_features.sort(key=lambda x: x["importance"], reverse=True)
    print(f"  SHAP calculado para {n_shap} registros, {len(shap_features)} features.")

except Exception as e:
    print(f"  Aviso: SHAP nao disponivel ({e}). Usando proxy de variancia.")
    for feat, (label, desc) in FEATURE_DESC.items():
        if feat in df.columns:
            vals = df[feat].astype(float)
            imp = round(float(vals.std()) / (abs(float(vals.mean())) + 1e-9), 5)
            shap_features.append({"feature": feat, "label": label,
                                   "description": desc, "importance": imp})
    shap_features.sort(key=lambda x: x["importance"], reverse=True)

# Keep top 10
shap_features = shap_features[:10]

# ── summary stats ──────────────────────────────────────────────────────────
total       = int(len(df))
tier_counts = {str(k): int(v) for k, v in df["risk_tier"].value_counts().items()}
score_stats = {
    "mean":       round(float(df["ensemble_score"].mean()), 4),
    "max":        round(float(df["ensemble_score"].max()), 4),
    "min":        round(float(df["ensemble_score"].min()), 4),
    "if_mean":    round(float(df["if_score"].mean()), 4),
    "ae_mean":    round(float(df["ae_score"].astype(float).mean()), 4),
    "graph_mean": round(float(df["graph_score"].mean()), 4),
}

# Separate classified alerts from graph anomalies without a fraud label.
# Empty FRAUD_TYPE comes from ISOLATED_VENDOR graph alerts (structural: fires for
# vendors with a single user, regardless of injection). These are real graph signals
# but not mapped to a named fraud scenario — show them in a dedicated KPI card
# rather than mixing them into the fraud-type breakdown chart.
_classified = df[df["FRAUD_TYPE"].str.strip() != ""]
unclassified_count = int((df["FRAUD_TYPE"].str.strip() == "").sum())
ft_series = _classified["FRAUD_TYPE"].value_counts()
ft_labels = ft_series.index.tolist()
ft_values = [int(v) for v in ft_series.values]

counts, edges = np.histogram(df["ensemble_score"].astype(float), bins=20)
hist_labels = [f"{edges[i]:.3f}" for i in range(len(edges) - 1)]
hist_values = [int(v) for v in counts]

top20 = (
    df.nlargest(20, "ensemble_score")[
        ["alert_id", "LIFNR", "BUKRS", "BELNR", "DMBTR", "AUGDT",
         "FRAUD_TYPE", "if_score", "ae_score", "graph_score",
         "ensemble_score", "risk_tier"]
    ].copy()
)
top20["DMBTR"]          = top20["DMBTR"].apply(lambda x: f"R$ {x:,.2f}")
top20["ensemble_score"] = top20["ensemble_score"].round(4)
top20["if_score"]       = top20["if_score"].round(4)
top20["ae_score"]       = top20["ae_score"].astype(float).round(4)
top20["graph_score"]    = top20["graph_score"].round(4)
top20_records = top20.to_dict("records")

generated_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

payload = {
    "total":              total,
    "tier_counts":        tier_counts,
    "score_stats":        score_stats,
    "ft_labels":          ft_labels,
    "ft_values":          ft_values,
    "unclassified_count": unclassified_count,
    "hist_labels":        hist_labels,
    "hist_values":        hist_values,
    "top20":              top20_records,
    "shap_features":      shap_features,
    "generated_at":       generated_at,
}

data_json = json.dumps(payload, ensure_ascii=True, default=str)
print(f"  Payload JSON: {len(data_json):,} bytes")

# ── HTML ───────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SAP P2P &mdash; Fraud Detection Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#0f1117;color:#e0e0e0;min-height:100vh}
header{background:linear-gradient(135deg,#1a1f2e 0%,#16213e 100%);
  padding:24px 32px;border-bottom:2px solid #e63946}
header h1{font-size:1.55rem;color:#fff;letter-spacing:.4px}
header p{font-size:.85rem;color:#8899aa;margin-top:5px}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;
  font-size:.72rem;font-weight:700;margin-left:10px;vertical-align:middle}
.badge-live{background:#e63946;color:#fff}
main{padding:28px 32px;max-width:1400px;margin:0 auto}
section{margin-bottom:34px}
h2.section-title{font-size:.82rem;color:#8899aa;text-transform:uppercase;
  letter-spacing:1.2px;margin-bottom:16px;padding-bottom:6px;
  border-bottom:1px solid #1e2535}
/* KPI */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:14px}
.kpi{background:#1a1f2e;border:1px solid #1e2535;border-radius:10px;
  padding:20px 16px;text-align:center;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;
  height:3px;background:var(--ac,#e63946)}
.kpi-val{font-size:1.9rem;font-weight:700;color:#fff;line-height:1.1}
.kpi-lbl{font-size:.73rem;color:#8899aa;margin-top:6px;
  text-transform:uppercase;letter-spacing:.5px}
.kpi-sub{font-size:.7rem;color:#445;margin-top:3px}
/* Charts */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.chart-box{background:#1a1f2e;border:1px solid #1e2535;border-radius:10px;padding:20px}
.chart-box h3{font-size:.8rem;color:#8899aa;text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:14px}
canvas{display:block;max-width:100%}
/* Table */
.table-wrap{background:#1a1f2e;border:1px solid #1e2535;
  border-radius:10px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.79rem}
thead th{background:#0f1117;color:#8899aa;text-transform:uppercase;
  font-size:.7rem;letter-spacing:.5px;padding:10px 12px;text-align:left;
  white-space:nowrap;position:sticky;top:0;z-index:2;
  border-bottom:1px solid #1e2535}
tbody td{padding:9px 12px;border-bottom:1px solid #141920;
  white-space:nowrap;color:#ccc}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:#1e2535}
.tier-HIGH{display:inline-block;padding:2px 9px;border-radius:10px;
  font-size:.72rem;font-weight:700;
  background:#e6394622;color:#e63946;border:1px solid #e6394655}
.tier-MEDIUM{display:inline-block;padding:2px 9px;border-radius:10px;
  font-size:.72rem;font-weight:700;
  background:#f4a26122;color:#f4a261;border:1px solid #f4a26155}
.tier-LOW{display:inline-block;padding:2px 9px;border-radius:10px;
  font-size:.72rem;font-weight:700;
  background:#2ec4b622;color:#2ec4b6;border:1px solid #2ec4b655}
.rank{color:#445;font-variant-numeric:tabular-nums}
.vendor-id{color:#a8dadc;font-weight:600}
.amount{color:#f4a261;font-weight:600}
.score-hi{color:#e63946;font-weight:700}
.score-mid{color:#f4a261}
.mono{font-family:'Cascadia Code','Consolas',monospace;font-size:.72rem}
/* SHAP section */
.shap-panel{background:#1a1f2e;border:1px solid #1e2535;
  border-radius:10px;padding:0;overflow:hidden}
.shap-chart-area{padding:24px 28px 8px}
.shap-legend{padding:0 28px 24px}
.shap-legend-title{font-size:.75rem;color:#8899aa;text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:14px;padding-top:20px;
  border-top:1px solid #1e2535}
.shap-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.shap-card{background:#0f1117;border:1px solid #1e2535;border-radius:8px;
  padding:14px 16px}
.shap-card-rank{font-size:.68rem;color:#445;font-weight:700;
  text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.shap-card-label{font-size:.88rem;color:#e0e0e0;font-weight:600;
  margin-bottom:6px}
.shap-card-badge{display:inline-block;padding:1px 8px;border-radius:8px;
  font-size:.7rem;font-weight:700;background:#e6394622;
  color:#e63946;border:1px solid #e6394644;margin-bottom:8px}
.shap-card-desc{font-size:.77rem;color:#8899aa;line-height:1.5}
.shap-card-sap{font-size:.7rem;color:#445;margin-top:6px;
  font-style:italic}
footer{text-align:center;padding:18px;color:#334;font-size:.73rem;
  border-top:1px solid #1e2535;margin-top:8px}
@media(max-width:768px){.charts-row{grid-template-columns:1fr}}
</style>
</head>
<body>

<header>
  <h1>&#x1F6E1; SAP P2P &mdash; Fraud Detection Dashboard
    <span class="badge badge-live">LIVE</span>
  </h1>
  <p id="gen-ts"></p>
</header>

<main>

<!-- KPIs -->
<section>
  <h2 class="section-title">Resumo Executivo</h2>
  <div class="kpi-row">
    <div class="kpi" style="--ac:#e63946">
      <div class="kpi-val" id="k-total"></div>
      <div class="kpi-lbl">Total de Alertas</div>
    </div>
    <div class="kpi" style="--ac:#e63946">
      <div class="kpi-val" id="k-high"></div>
      <div class="kpi-lbl">Risco Alto</div>
      <div class="kpi-sub">Acao imediata</div>
    </div>
    <div class="kpi" style="--ac:#f4a261">
      <div class="kpi-val" id="k-medium"></div>
      <div class="kpi-lbl">Risco Medio</div>
    </div>
    <div class="kpi" style="--ac:#2ec4b6">
      <div class="kpi-val" id="k-low"></div>
      <div class="kpi-lbl">Risco Baixo</div>
    </div>
    <div class="kpi" style="--ac:#4ecdc4">
      <div class="kpi-val" id="k-ens-mean"></div>
      <div class="kpi-lbl">Score Ensemble Medio</div>
    </div>
    <div class="kpi" style="--ac:#e63946">
      <div class="kpi-val" id="k-ens-max"></div>
      <div class="kpi-lbl">Score Maximo</div>
    </div>
    <div class="kpi" style="--ac:#457b9d">
      <div class="kpi-val" id="k-if-mean"></div>
      <div class="kpi-lbl">Score IF Medio</div>
    </div>
    <div class="kpi" style="--ac:#6a4c93">
      <div class="kpi-val" id="k-ae-mean"></div>
      <div class="kpi-lbl">Score AE Medio</div>
    </div>
  </div>
</section>

<!-- Charts -->
<section>
  <h2 class="section-title">Distribuicao de Alertas</h2>
  <div class="charts-row">
    <div class="chart-box">
      <h3>Alertas por Tipo de Fraude</h3>
      <canvas id="cFraud"></canvas>
      <div id="unclassified-note" style="margin-top:12px;padding:10px 14px;background:#fff8e1;border-left:4px solid #f9a825;border-radius:4px;font-size:.82rem;color:#555;display:none">
        <strong style="color:#e65100" id="unclassified-count"></strong>
        anomalia(s) sem tipo — alertas do analisador de grafo (ISOLATED_VENDOR) que
        detectam padr&atilde;o suspeito mas n&atilde;o correspondem a um cen&aacute;rio
        de fraude injetado. Exibidos separadamente para n&atilde;o distorcer o gr&aacute;fico.
      </div>
    </div>
    <div class="chart-box">
      <h3>Distribuicao do Score Ensemble</h3>
      <canvas id="cHist"></canvas>
    </div>
  </div>
</section>

<!-- Table -->
<section>
  <h2 class="section-title">Top 20 Alertas Criticos</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Fornecedor</th><th>Empresa</th><th>Documento</th>
          <th>Valor</th><th>Data Pagto</th><th>Tipo de Fraude</th>
          <th>IF</th><th>AE</th><th>Grafo</th><th>Ensemble</th><th>Risco</th>
        </tr>
      </thead>
      <tbody id="alert-tbody"></tbody>
    </table>
  </div>
</section>

<!-- SHAP -->
<section>
  <h2 class="section-title">
    Importancia das Features (SHAP) &mdash; Isolation Forest &bull;
    <span style="font-weight:400;text-transform:none;letter-spacing:0;
      color:#556;font-size:.78rem">
      |SHAP mean(|valor|)| nos 20 alertas de maior score
    </span>
  </h2>
  <div class="shap-panel">
    <div class="shap-chart-area">
      <canvas id="cShap"></canvas>
    </div>
    <div class="shap-legend">
      <div class="shap-legend-title">
        O que cada feature significa no contexto SAP P2P
      </div>
      <div class="shap-cards" id="shap-cards"></div>
    </div>
  </div>
</section>

</main>
<footer>
  SAP P2P Fraud Detection &mdash; Dados Sinteticos &mdash;
  SHAP via Isolation Forest &mdash; <span id="footer-ts"></span>
</footer>

<script>
/* ==============================================================
   DATA — embutido inline pelo generate_dashboard.py
   ============================================================== */
const DATA = /*INJECT_JSON*/;

/* ==============================================================
   KPIs
   ============================================================== */
document.getElementById('gen-ts').textContent = 'Gerado em: ' + DATA.generated_at;
document.getElementById('footer-ts').textContent = DATA.generated_at;
document.getElementById('k-total').textContent    = DATA.total.toLocaleString('pt-BR');
document.getElementById('k-high').textContent     = (DATA.tier_counts['HIGH']   || 0).toLocaleString('pt-BR');
document.getElementById('k-medium').textContent   = (DATA.tier_counts['MEDIUM'] || 0).toLocaleString('pt-BR');
document.getElementById('k-low').textContent      = (DATA.tier_counts['LOW']    || 0).toLocaleString('pt-BR');
document.getElementById('k-ens-mean').textContent = DATA.score_stats.mean.toFixed(4);
document.getElementById('k-ens-max').textContent  = DATA.score_stats.max.toFixed(4);
document.getElementById('k-if-mean').textContent  = DATA.score_stats.if_mean.toFixed(4);
document.getElementById('k-ae-mean').textContent  = DATA.score_stats.ae_mean.toFixed(4);

/* ==============================================================
   Canvas helpers
   ============================================================== */
function initCanvas(id, heightPx) {
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.parentElement.clientWidth - 40;
  const h = heightPx;
  canvas.width  = w * ratio;
  canvas.height = h * ratio;
  canvas.style.width  = w + 'px';
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);
  return { ctx, w, h };
}

/* vertical bar chart */
function drawBars(canvasId, labels, values, color) {
  const c = initCanvas(canvasId, 270); if (!c) return;
  const { ctx, w, h } = c;
  const pad = { t:24, r:12, b:90, l:44 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const max = Math.max(...values, 1) * 1.12;
  ctx.clearRect(0, 0, w, h);
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + ih - (i/4)*ih;
    ctx.strokeStyle='#1e2535'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(pad.l+iw,y); ctx.stroke();
    ctx.fillStyle='#556'; ctx.font='11px Segoe UI'; ctx.textAlign='right';
    ctx.fillText(Math.round((i/4)*max), pad.l-5, y+4);
  }
  const slot = iw/labels.length, bw = Math.max(6, slot*0.62);
  labels.forEach((lbl,i) => {
    const x = pad.l+i*slot+(slot-bw)/2, bh=(values[i]/max)*ih, y=pad.t+ih-bh;
    const g = ctx.createLinearGradient(0,y,0,y+bh);
    g.addColorStop(0,color); g.addColorStop(1,color+'55');
    ctx.fillStyle=g;
    ctx.beginPath();
    if(ctx.roundRect) ctx.roundRect(x,y,bw,bh,4); else ctx.rect(x,y,bw,bh);
    ctx.fill();
    ctx.fillStyle='#ccc'; ctx.font='bold 11px Segoe UI'; ctx.textAlign='center';
    ctx.fillText(values[i], x+bw/2, y-5);
    ctx.save(); ctx.translate(x+bw/2, pad.t+ih+8); ctx.rotate(-Math.PI/4);
    ctx.fillStyle='#8899aa'; ctx.font='10px Segoe UI'; ctx.textAlign='right';
    ctx.fillText(lbl.length>20?lbl.slice(0,19)+'…':lbl, 0, 0);
    ctx.restore();
  });
  ctx.strokeStyle='#2a3040'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(pad.l,pad.t); ctx.lineTo(pad.l,pad.t+ih); ctx.stroke();
}

/* histogram */
function drawHist(canvasId, labels, values) {
  const c = initCanvas(canvasId, 270); if (!c) return;
  const { ctx, w, h } = c;
  const pad = { t:24, r:12, b:38, l:44 };
  const iw = w-pad.l-pad.r, ih = h-pad.t-pad.b;
  const max = Math.max(...values,1)*1.12;
  ctx.clearRect(0,0,w,h);
  for(let i=0;i<=4;i++){
    const y=pad.t+ih-(i/4)*ih;
    ctx.strokeStyle='#1e2535'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(pad.l+iw,y); ctx.stroke();
    ctx.fillStyle='#556'; ctx.font='11px Segoe UI'; ctx.textAlign='right';
    ctx.fillText(Math.round((i/4)*max),pad.l-5,y+4);
  }
  const bw=iw/values.length;
  values.forEach((v,i)=>{
    const x=pad.l+i*bw, bh=(v/max)*ih, y=pad.t+ih-bh;
    const g=ctx.createLinearGradient(0,y,0,y+bh);
    g.addColorStop(0,'#4ecdc4'); g.addColorStop(1,'#4ecdc433');
    ctx.fillStyle=g; ctx.fillRect(x+.5,y,bw-1,bh);
  });
  [0,Math.floor(labels.length/2),labels.length-1].forEach(i=>{
    ctx.fillStyle='#8899aa'; ctx.font='10px Segoe UI'; ctx.textAlign='center';
    ctx.fillText(labels[i], pad.l+i*bw+bw/2, pad.t+ih+16);
  });
  ctx.strokeStyle='#2a3040'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(pad.l,pad.t+ih); ctx.lineTo(pad.l+iw,pad.t+ih); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(pad.l,pad.t); ctx.lineTo(pad.l,pad.t+ih); ctx.stroke();
}

/* SHAP horizontal bar chart */
function drawShapBars(canvasId, features) {
  const ROW_H  = 38;
  const height = features.length * ROW_H + 32;
  const c = initCanvas(canvasId, height); if (!c) return;
  const { ctx, w, h } = c;
  const pad = { t:16, r:16, b:16, l:220 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const max = Math.max(...features.map(f=>f.importance), 0.0001);
  ctx.clearRect(0, 0, w, h);

  features.forEach((f, i) => {
    const y    = pad.t + i * ROW_H;
    const barH = ROW_H * 0.52;
    const barY = y + (ROW_H - barH) / 2;
    const barW = (f.importance / max) * iw;

    // row background (alternating)
    if (i % 2 === 0) {
      ctx.fillStyle = '#ffffff08';
      ctx.fillRect(0, y, w, ROW_H);
    }

    // rank badge
    ctx.fillStyle = '#445';
    ctx.font = 'bold 10px Segoe UI';
    ctx.textAlign = 'right';
    ctx.fillText(`#${i+1}`, 22, barY + barH * 0.72);

    // feature label
    ctx.fillStyle = '#d0d0d0';
    ctx.font = '12px Segoe UI';
    ctx.textAlign = 'left';
    const labelText = f.label || f.feature;
    ctx.fillText(labelText.length > 30 ? labelText.slice(0,29)+'…' : labelText,
                 28, barY + barH * 0.72);

    // gradient bar
    const g = ctx.createLinearGradient(pad.l, 0, pad.l + barW, 0);
    g.addColorStop(0, '#e63946');
    g.addColorStop(1, '#ff8a80');
    ctx.fillStyle = g;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(pad.l, barY, barW, barH, 3);
    else ctx.rect(pad.l, barY, barW, barH);
    ctx.fill();

    // value label
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 11px Segoe UI';
    ctx.textAlign = 'left';
    ctx.fillText(f.importance.toFixed(5), pad.l + barW + 8, barY + barH * 0.72);
  });

  // vertical divider
  ctx.strokeStyle = '#2a3040'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad.l, pad.t - 8); ctx.lineTo(pad.l, h - pad.b + 8); ctx.stroke();
}

/* ==============================================================
   Alert table
   ============================================================== */
function scoreClass(v) { return v>=0.7?'score-hi':v>=0.5?'score-mid':''; }

function renderTable() {
  document.getElementById('alert-tbody').innerHTML = DATA.top20.map((r, i) => {
    const ens = parseFloat(r.ensemble_score), tier = r.risk_tier;
    return `<tr>
      <td class="rank">${i+1}</td>
      <td class="vendor-id">${r.LIFNR}</td>
      <td>${r.BUKRS}</td>
      <td class="mono">${r.BELNR}</td>
      <td class="amount">${r.DMBTR}</td>
      <td>${r.AUGDT||'&mdash;'}</td>
      <td>${r.FRAUD_TYPE||'&mdash;'}</td>
      <td class="${scoreClass(parseFloat(r.if_score))}">${parseFloat(r.if_score).toFixed(4)}</td>
      <td>${parseFloat(r.ae_score).toFixed(4)}</td>
      <td>${parseFloat(r.graph_score).toFixed(2)}</td>
      <td class="${scoreClass(ens)}">${ens.toFixed(4)}</td>
      <td><span class="tier-${tier}">${tier}</span></td>
    </tr>`;
  }).join('');
}

/* ==============================================================
   SHAP cards (explanations)
   ============================================================== */
function renderShapCards() {
  document.getElementById('shap-cards').innerHTML = DATA.shap_features.map((f, i) => `
    <div class="shap-card">
      <div class="shap-card-rank">#${i+1} Feature</div>
      <div class="shap-card-label">${f.label || f.feature}</div>
      <div class="shap-card-badge">SHAP ${f.importance.toFixed(5)}</div>
      <div class="shap-card-desc">${f.description || ''}</div>
      <div class="shap-card-sap">Campo SAP: ${f.feature}</div>
    </div>`).join('');
}

/* ==============================================================
   Boot
   ============================================================== */
function renderUnclassifiedNote() {
  const n = DATA.unclassified_count || 0;
  if (n > 0) {
    const el = document.getElementById('unclassified-note');
    document.getElementById('unclassified-count').textContent = n;
    el.style.display = 'block';
  }
}

function render() {
  drawBars('cFraud', DATA.ft_labels, DATA.ft_values, '#e63946');
  drawHist('cHist',  DATA.hist_labels, DATA.hist_values);
  drawShapBars('cShap', DATA.shap_features);
  renderTable();
  renderShapCards();
  renderUnclassifiedNote();
}

render();
window.addEventListener('resize', render);
</script>
</body>
</html>
"""

html_final = HTML.replace("/*INJECT_JSON*/", data_json)
OUT_PATH.write_text(html_final, encoding="utf-8")

size_kb = OUT_PATH.stat().st_size / 1024
print(f"\nDashboard salvo: {OUT_PATH}")
print(f"Tamanho: {size_kb:.1f} KB")
print(f"\nSessao SHAP adicionada:")
for i, f in enumerate(shap_features, 1):
    print(f"  #{i:2d}  {f['importance']:.5f}  {f['label']}")
print(f"\nAbra com:  start {OUT_PATH}")
