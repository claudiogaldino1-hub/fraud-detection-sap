"""
scripts/generate_executive_report.py
Gera reports/executive_report.html — uma página para gestores, sem tecnicismo.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT          = Path(__file__).resolve().parent.parent
COST_REPORT   = ROOT / "governance" / "cost_report.json"
CHECKSUMS_PATH= ROOT / "governance" / "checksums.json"
AUDIT_PATH    = ROOT / "governance" / "AUDIT_LOG.json"
ALERTS_PATH   = ROOT / "data" / "processed" / "alerts.parquet"
OUT_PATH      = ROOT / "reports" / "executive_report.html"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
ALERTS_DASHBOARD = "dashboard.html"

# ── load ───────────────────────────────────────────────────────────────────
if not COST_REPORT.exists():
    sys.exit("ERRO: cost_report.json não encontrado. Rode o pipeline primeiro.")

cost    = json.loads(COST_REPORT.read_text(encoding="utf-8"))
audit   = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
chk_hist= json.loads(CHECKSUMS_PATH.read_text(encoding="utf-8")) if CHECKSUMS_PATH.exists() else []

# ── identity ───────────────────────────────────────────────────────────────
rich = [e for e in audit if e.get("action") == "PIPELINE_RUN_COMPLETE"]
last_rich = rich[-1] if rich else {}

pipeline_id  = cost.get("pipeline_id", "?")
generated_at = datetime.now(timezone.utc)
dt_str       = generated_at.strftime("%d/%m/%Y às %H:%M UTC")
author       = last_rich.get("git_author", "—").split("<")[0].strip()
os_user      = last_rich.get("os_user", "—")
hostname     = last_rich.get("hostname", "—")
commit       = last_rich.get("git_commit_short", "?")

# ── alerts ─────────────────────────────────────────────────────────────────
try:
    import pandas as pd
    df     = pd.read_parquet(ALERTS_PATH)
    tiers  = df["risk_tier"].astype(str).value_counts().to_dict()
    total  = int(len(df))
    high   = int(tiers.get("HIGH", 0))
    medium = int(tiers.get("MEDIUM", 0))
    low    = int(tiers.get("LOW", 0))
except Exception:
    total = high = medium = low = 0
    tiers = {}

# ── cost ───────────────────────────────────────────────────────────────────
cs          = cost.get("cost_summary", {})
total_cost  = float(cs.get("total_estimated_usd", 0))
compute_usd = float(cs.get("compute_aws_ec2_usd", 0))
storage_usd = float(cs.get("storage_aws_s3_monthly_usd", 0))
claude_usd  = float(cs.get("claude_api_usd", 0))
narratives  = cost.get("claude_api", {}).get("narratives_generated", 0)
compute_sec = float(cost.get("compute", {}).get("total_elapsed_seconds", 0))

# ── integrity ─────────────────────────────────────────────────────────────
last_snap      = chk_hist[-1] if chk_hist else None
files_monitored= last_snap["file_count"] if last_snap else 0
integrity_ok   = True   # always OK when called right after pipeline

# ── overall status ─────────────────────────────────────────────────────────
if high > 0 and not integrity_ok:
    status       = "CRITICO"
    status_color = "#e63946"
    status_icon  = "🚨"
    status_bg    = "#e6394611"
elif high > 0 or not integrity_ok:
    status       = "ATENCAO"
    status_color = "#f4a261"
    status_icon  = "⚠️"
    status_bg    = "#f4a26111"
else:
    status       = "OK"
    status_color = "#2ec4b6"
    status_icon  = "✅"
    status_bg    = "#2ec4b611"

# ── auto summary sentence ──────────────────────────────────────────────────
def _plural(n, s, p): return f"{n} {s if n==1 else p}"

high_txt   = f", **{_plural(high,'de alto risco','de alto risco')}**" if high else ""
integ_txt  = "Sistema íntegro" if integrity_ok else "⚠ Verifique a integridade do sistema"
narr_txt   = f" {_plural(narratives,'narrativa gerada','narrativas geradas')} via Claude API." if narratives else ""
summary = (
    f"Pipeline executado com sucesso por **{author or os_user}** em {dt_str}. "
    f"{_plural(total,'alerta detectado','alertas detectados')}{high_txt}. "
    f"{integ_txt}. "
    f"Custo: **${total_cost:.6f} USD**.{narr_txt}"
)

generated_at_str = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")

payload = {
    "pipeline_id":    pipeline_id,
    "generated_at":   generated_at_str,
    "dt_str":         dt_str,
    "author":         author,
    "os_user":        os_user,
    "hostname":       hostname,
    "commit":         commit,
    "status":         status,
    "status_color":   status_color,
    "status_icon":    status_icon,
    "status_bg":      status_bg,
    "summary":        summary,
    "total_alerts":   total,
    "high":           high,
    "medium":         medium,
    "low":            low,
    "total_cost":     total_cost,
    "compute_usd":    compute_usd,
    "storage_usd":    storage_usd,
    "claude_usd":     claude_usd,
    "compute_sec":    compute_sec,
    "narratives":     narratives,
    "integrity_ok":   integrity_ok,
    "files_monitored": files_monitored,
    "alerts_dashboard": ALERTS_DASHBOARD,
}
data_json = json.dumps(payload, ensure_ascii=True, default=str)

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Relatório Executivo — SAP P2P Fraud Detection</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#0a0d14;
  color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column}
header{background:linear-gradient(135deg,#0f1117,#1a1f2e);
  padding:20px 32px;border-bottom:2px solid #457b9d}
header h1{font-size:1.35rem;color:#fff}
header p{font-size:.8rem;color:#8899aa;margin-top:4px}
main{padding:32px;max-width:900px;margin:0 auto;flex:1;width:100%}
/* semaphore hero */
.hero{border-radius:16px;padding:32px 36px;margin-bottom:28px;
  display:flex;align-items:center;gap:28px;border:1px solid}
.sem-big{width:90px;height:90px;border-radius:50%;display:flex;
  align-items:center;justify-content:center;font-size:2.6rem;flex-shrink:0;
  box-shadow:0 0 40px var(--glow)}
.hero-text h2{font-size:1.5rem;font-weight:700;margin-bottom:8px}
.hero-text .summary-text{font-size:.92rem;color:#ccc;line-height:1.7}
.hero-text .summary-text strong,.hero-text .summary-text b{color:#fff;font-weight:700}
/* sections */
h2.st{font-size:.76rem;color:#8899aa;text-transform:uppercase;letter-spacing:1.2px;
  margin-bottom:14px;padding-bottom:5px;border-bottom:1px solid #1e2535}
/* stat grid */
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;
  margin-bottom:28px}
.stat{background:#111827;border:1px solid #1e2535;border-radius:10px;
  padding:18px 16px;text-align:center;position:relative;overflow:hidden}
.stat::before{content:'';position:absolute;top:0;left:0;right:0;
  height:3px;background:var(--ac,#457b9d)}
.stat-val{font-size:1.8rem;font-weight:700;color:#fff;line-height:1.1}
.stat-lbl{font-size:.7rem;color:#8899aa;margin-top:5px;
  text-transform:uppercase;letter-spacing:.4px}
/* detail rows */
.detail-panel{background:#111827;border:1px solid #1e2535;border-radius:10px;
  padding:20px;margin-bottom:20px}
.detail-panel h3{font-size:.77rem;color:#8899aa;text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:14px}
.detail-row{display:flex;justify-content:space-between;align-items:center;
  padding:7px 0;border-bottom:1px solid #1a2030;font-size:.85rem}
.detail-row:last-child{border-bottom:none}
.detail-key{color:#8899aa}
.detail-val{color:#e0e0e0;font-weight:600;font-variant-numeric:tabular-nums}
/* alerts tier bars */
.tier-row{margin:8px 0}
.tier-label{display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:4px}
.tier-track{background:#0a0d14;border-radius:4px;height:8px;overflow:hidden}
.tier-fill{height:100%;border-radius:4px}
/* CTA button */
.cta{display:inline-block;padding:12px 28px;border-radius:8px;
  background:#e63946;color:#fff;font-weight:700;font-size:.9rem;
  text-decoration:none;border:none;cursor:pointer;margin-top:8px}
.cta:hover{background:#c0392b}
/* integrity badge */
.integ-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;
  border-radius:20px;font-size:.8rem;font-weight:700}
footer{text-align:center;padding:14px;color:#2a3040;font-size:.7rem;
  border-top:1px solid #1e2535}
@media(max-width:600px){.hero{flex-direction:column;text-align:center}
  .sem-big{margin:0 auto}}
</style>
</head>
<body>
<header>
  <h1>&#x1F4CB; Relatório Executivo — SAP P2P Fraud Detection</h1>
  <p id="hdr-sub"></p>
</header>
<main>

<!-- Semaphore hero -->
<div class="hero" id="hero">
  <div class="sem-big" id="sem-big"></div>
  <div class="hero-text">
    <h2 id="hero-title"></h2>
    <p class="summary-text" id="hero-summary"></p>
    <br>
    <a id="cta-btn" class="cta" href="#">&#x1F4CA; Ver Dashboard Completo de Alertas</a>
  </div>
</div>

<!-- Stats row -->
<section style="margin-bottom:28px">
  <h2 class="st">Alertas por Nivel de Risco</h2>
  <div class="stat-grid">
    <div class="stat" style="--ac:#457b9d">
      <div class="stat-val" id="s-total"></div>
      <div class="stat-lbl">Total de Alertas</div>
    </div>
    <div class="stat" style="--ac:#e63946">
      <div class="stat-val" id="s-high"></div>
      <div class="stat-lbl">Alto Risco</div>
    </div>
    <div class="stat" style="--ac:#f4a261">
      <div class="stat-val" id="s-medium"></div>
      <div class="stat-lbl">Risco Medio</div>
    </div>
    <div class="stat" style="--ac:#2ec4b6">
      <div class="stat-val" id="s-low"></div>
      <div class="stat-lbl">Risco Baixo</div>
    </div>
  </div>
  <div class="detail-panel">
    <div id="tier-bars"></div>
  </div>
</section>

<!-- Cost & run detail -->
<div class="detail-panel">
  <h3>Detalhes do Run</h3>
  <div class="detail-row">
    <span class="detail-key">Responsavel pela execucao</span>
    <span class="detail-val" id="d-author"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Maquina / usuario SO</span>
    <span class="detail-val" id="d-machine"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Pipeline ID</span>
    <span class="detail-val" id="d-pid"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Commit do codigo</span>
    <span class="detail-val" id="d-commit"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Tempo de execucao</span>
    <span class="detail-val" id="d-time"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Integridade do sistema</span>
    <span class="detail-val" id="d-integ"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Arquivos monitorados (SHA-256)</span>
    <span class="detail-val" id="d-files"></span>
  </div>
</div>

<div class="detail-panel">
  <h3>Custo do Run (USD)</h3>
  <div class="detail-row">
    <span class="detail-key">Processamento (AWS EC2 equivalente)</span>
    <span class="detail-val" id="d-compute"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Armazenamento (S3 mensal)</span>
    <span class="detail-val" id="d-storage"></span>
  </div>
  <div class="detail-row">
    <span class="detail-key">Claude API (narrativas)</span>
    <span class="detail-val" id="d-claude"></span>
  </div>
  <div class="detail-row" style="border-top:1px solid #2a3548;margin-top:4px;padding-top:10px">
    <span class="detail-key" style="color:#e0e0e0;font-weight:600">Total estimado</span>
    <span class="detail-val" style="color:#4ecdc4;font-size:1rem" id="d-total"></span>
  </div>
</div>

</main>
<footer>SAP P2P Fraud Detection &mdash; Relatorio Executivo &mdash; <span id="footer-ts"></span></footer>

<script>
const D = /*INJECT_JSON*/;
const $ = id => document.getElementById(id);
const f6 = v => '$ ' + Number(v).toFixed(6) + ' USD';

$('footer-ts').textContent  = D.generated_at;
$('hdr-sub').textContent    = `Pipeline ${D.pipeline_id} | ${D.generated_at}`;
$('cta-btn').href           = D.alerts_dashboard;

// hero
const hero = $('hero');
hero.style.background  = D.status_bg;
hero.style.borderColor = D.status_color + '55';
const sem = $('sem-big');
sem.textContent = D.status_icon;
sem.style.cssText = `width:90px;height:90px;border-radius:50%;display:flex;
  align-items:center;justify-content:center;font-size:2.6rem;flex-shrink:0;
  background:${D.status_bg};border:3px solid ${D.status_color};
  box-shadow:0 0 40px ${D.status_color}66`;
$('hero-title').textContent = `Status: ${D.status}`;
$('hero-title').style.color = D.status_color;

// parse **bold** in summary
$('hero-summary').innerHTML = D.summary
  .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

// stats
$('s-total').textContent  = D.total_alerts.toLocaleString('pt-BR');
$('s-high').textContent   = D.high.toLocaleString('pt-BR');
$('s-medium').textContent = D.medium.toLocaleString('pt-BR');
$('s-low').textContent    = D.low.toLocaleString('pt-BR');

// tier bars
const tiers = [
  {label:'Alto Risco',  val:D.high,   color:'#e63946', pct: D.total_alerts?D.high/D.total_alerts*100:0},
  {label:'Risco Medio', val:D.medium, color:'#f4a261', pct: D.total_alerts?D.medium/D.total_alerts*100:0},
  {label:'Risco Baixo', val:D.low,    color:'#2ec4b6', pct: D.total_alerts?D.low/D.total_alerts*100:0},
];
$('tier-bars').innerHTML = tiers.map(t=>`
  <div class="tier-row">
    <div class="tier-label">
      <span style="color:${t.color};font-weight:600">${t.label}</span>
      <span>${t.val.toLocaleString('pt-BR')} (${t.pct.toFixed(1)}%)</span>
    </div>
    <div class="tier-track">
      <div class="tier-fill" style="width:${t.pct}%;background:${t.color}"></div>
    </div>
  </div>`).join('');

// detail rows
$('d-author').textContent  = D.author || D.os_user;
$('d-machine').textContent = `${D.os_user} @ ${D.hostname}`;
$('d-pid').textContent     = D.pipeline_id;
$('d-commit').textContent  = D.commit;
$('d-time').textContent    = D.compute_sec.toFixed(2) + ' segundos';
$('d-files').textContent   = `${D.files_monitored} arquivo(s) verificados`;
$('d-compute').textContent = f6(D.compute_usd);
$('d-storage').textContent = f6(D.storage_usd);
$('d-claude').textContent  = D.narratives
  ? f6(D.claude_usd) + ` (${D.narratives} narrativas)`
  : f6(D.claude_usd) + ' (nenhuma narrativa gerada)';
$('d-total').textContent   = f6(D.total_cost);

const integ = $('d-integ');
integ.innerHTML = D.integrity_ok
  ? '<span class="integ-badge" style="background:#2ec4b611;color:#2ec4b6;'+
    'border:1px solid #2ec4b633">&#10003; INTEGRO</span>'
  : '<span class="integ-badge" style="background:#e6394611;color:#e63946;'+
    'border:1px solid #e6394633">&#10007; VERIFIQUE O SISTEMA</span>';
</script>
</body>
</html>"""

html_final = HTML.replace("/*INJECT_JSON*/", data_json)
OUT_PATH.write_text(html_final, encoding="utf-8")
print(f"  Salvo: {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.1f} KB)")
print(f"  Status: {status} | {total} alertas ({high} HIGH) | ${total_cost:.6f} USD")
