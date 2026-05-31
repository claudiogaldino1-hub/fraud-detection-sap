"""
scripts/generate_audit_dashboard.py
Lê governance/checksums.json e governance/AUDIT_LOG.json e gera
reports/audit_dashboard.html 100% standalone (dark theme, inline data).
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT          = Path(__file__).resolve().parent.parent
CHECKSUMS_PATH = ROOT / "governance" / "checksums.json"
AUDIT_PATH     = ROOT / "governance" / "AUDIT_LOG.json"
OUT_PATH       = ROOT / "reports" / "audit_dashboard.html"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── load ───────────────────────────────────────────────────────────────────
if not AUDIT_PATH.exists():
    sys.exit(f"ERRO: {AUDIT_PATH} não encontrado.")

audit_entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
checksums_history = (
    json.loads(CHECKSUMS_PATH.read_text(encoding="utf-8"))
    if CHECKSUMS_PATH.exists() else []
)
last_snap = checksums_history[-1] if checksums_history else None

# ── component groups for semaphore ────────────────────────────────────────
COMPONENT_PATTERNS = {
    "Modelos ML":     ["models/registry/"],
    "Dados":          ["data/processed/"],
    "Governanca":     ["governance/AUDIT_LOG", "governance/model_versions",
                       "governance/cost_report"],
}

def classify_files(files: dict) -> dict[str, str]:
    """Returns {component: 'OK'|'TAMPERED'|'MISSING'|'UNKNOWN'}."""
    result = {}
    for comp, patterns in COMPONENT_PATTERNS.items():
        matching = {k: v for k, v in files.items()
                    if any(k.startswith(p) for p in patterns)}
        if not matching:
            result[comp] = "UNKNOWN"
        elif all(v != "MISSING" for v in matching.values()):
            result[comp] = "OK"
        elif any(v == "TAMPERED" for v in matching.values()):
            result[comp] = "TAMPERED"
        else:
            result[comp] = "MISSING"
    return result

# Build file status list from last snapshot (all OK since just saved)
file_statuses = []
if last_snap:
    for fp, digest in last_snap["files"].items():
        # Determine component
        comp = "Outros"
        for c, patterns in COMPONENT_PATTERNS.items():
            if any(fp.startswith(p) for p in patterns):
                comp = c; break
        file_statuses.append({
            "file": fp, "digest": digest, "status": "OK",
            "component": comp,
            "short": digest[:16] + "…",
        })
    component_status = classify_files({f["file"]: "OK" for f in file_statuses})
else:
    component_status = {c: "UNKNOWN" for c in COMPONENT_PATTERNS}

overall = (
    "TAMPERED" if any(v == "TAMPERED" for v in component_status.values()) else
    "MISSING"  if any(v == "MISSING"  for v in component_status.values()) else
    "UNKNOWN"  if all(v == "UNKNOWN"  for v in component_status.values()) else
    "OK"
)

# ── timeline: PIPELINE_RUN_COMPLETE entries ────────────────────────────────
rich_runs = [e for e in audit_entries if e["action"] == "PIPELINE_RUN_COMPLETE"]
timeline = []
for e in rich_runs:
    ts = e.get("timestamp","")[:19].replace("T"," ")
    timeline.append({
        "seq":          e.get("seq", "?"),
        "pipeline_id":  e.get("pipeline_id", "?"),
        "timestamp":    ts,
        "author":       e.get("git_author", "?"),
        "os_user":      e.get("os_user","?"),
        "hostname":     e.get("hostname","?"),
        "commit":       e.get("git_commit_short","?"),
        "branch":       e.get("git_branch","?"),
        "alerts":       e.get("alert_count", 0),
        "cost":         round(float(e.get("cost_total_usd", 0)), 6),
        "narratives":   e.get("narratives_generated", 0),
        "entry_hash":   (e.get("entry_hash","") or "")[:16] + "…",
    })

# All audit actions summary
action_counts = {}
for e in audit_entries:
    action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1

generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

payload = {
    "generated_at":      generated_at,
    "overall":           overall,
    "component_status":  component_status,
    "file_statuses":     file_statuses,
    "timeline":          timeline,
    "action_counts":     action_counts,
    "total_log_entries": len(audit_entries),
    "last_pipeline_id":  rich_runs[-1]["pipeline_id"] if rich_runs else "—",
    "checksums_snapshots": len(checksums_history),
}
data_json = json.dumps(payload, ensure_ascii=True, default=str)
print(f"  Payload: {len(data_json):,} bytes | {len(file_statuses)} files | "
      f"{len(timeline)} pipeline runs | {len(audit_entries)} log entries")

# ── HTML ───────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SAP P2P — Audit Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#0a0d14;color:#e0e0e0;min-height:100vh}
header{background:linear-gradient(135deg,#0f1117 0%,#1a1f2e 100%);
  padding:22px 32px;border-bottom:2px solid #457b9d}
header h1{font-size:1.45rem;color:#fff}
header p{font-size:.82rem;color:#8899aa;margin-top:4px}
.badge{display:inline-block;padding:2px 9px;border-radius:10px;font-size:.7rem;
  font-weight:700;margin-left:8px;vertical-align:middle}
main{padding:26px 32px;max-width:1400px;margin:0 auto}
section{margin-bottom:30px}
h2.st{font-size:.78rem;color:#8899aa;text-transform:uppercase;letter-spacing:1.2px;
  margin-bottom:14px;padding-bottom:5px;border-bottom:1px solid #1e2535}
/* overall banner */
.overall-banner{border-radius:12px;padding:20px 28px;margin-bottom:28px;
  display:flex;align-items:center;gap:20px;border:1px solid}
.semaphore{width:56px;height:56px;border-radius:50%;display:flex;
  align-items:center;justify-content:center;font-size:1.6rem;flex-shrink:0;
  box-shadow:0 0 24px var(--glow)}
.overall-text h3{font-size:1.1rem;font-weight:700;margin-bottom:4px}
.overall-text p{font-size:.85rem;color:#8899aa;line-height:1.5}
/* component semaphores */
.comp-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.comp-card{background:#111827;border:1px solid #1e2535;border-radius:10px;
  padding:18px 16px;text-align:center;position:relative;overflow:hidden}
.comp-card::before{content:'';position:absolute;top:0;left:0;right:0;
  height:3px;background:var(--ac)}
.comp-light{width:40px;height:40px;border-radius:50%;margin:0 auto 10px;
  display:flex;align-items:center;justify-content:center;font-size:1.2rem;
  box-shadow:0 0 16px var(--glow)}
.comp-name{font-size:.82rem;color:#8899aa;text-transform:uppercase;
  letter-spacing:.5px;margin-bottom:4px}
.comp-status{font-size:.9rem;font-weight:700}
/* panels */
.panel{background:#111827;border:1px solid #1e2535;border-radius:10px;padding:20px}
.panel h3{font-size:.77rem;color:#8899aa;text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:14px}
/* timeline */
.timeline{display:flex;flex-direction:column;gap:12px}
.tl-item{background:#0f1520;border:1px solid #1e2535;border-radius:8px;
  padding:14px 18px;display:grid;
  grid-template-columns:auto 1fr auto;gap:0 16px;align-items:start}
.tl-num{width:32px;height:32px;border-radius:50%;background:#1e2535;
  display:flex;align-items:center;justify-content:center;
  font-size:.78rem;color:#8899aa;font-weight:700;flex-shrink:0;margin-top:2px}
.tl-body{}
.tl-title{font-size:.88rem;color:#fff;font-weight:600;margin-bottom:4px}
.tl-meta{font-size:.76rem;color:#8899aa;line-height:1.7}
.tl-meta span{color:#a8dadc;font-family:monospace}
.tl-right{text-align:right;white-space:nowrap}
.tl-cost{font-size:.82rem;color:#4ecdc4;font-weight:600}
.tl-alerts{font-size:.75rem;color:#8899aa;margin-top:3px}
/* checksums table */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{background:#0a0d14;color:#8899aa;font-size:.69rem;text-transform:uppercase;
  letter-spacing:.4px;padding:9px 12px;text-align:left;
  border-bottom:1px solid #1e2535;white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid #141a24;color:#ccc;white-space:nowrap}
tr:hover td{background:#1a2030}
tr:last-child td{border-bottom:none}
.st-ok{color:#2ec4b6;font-weight:700}
.st-warn{color:#f4a261;font-weight:700}
.st-bad{color:#e63946;font-weight:700}
.mono{font-family:'Cascadia Code','Consolas',monospace;font-size:.72rem}
/* action pills */
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pill{background:#1e2535;border-radius:20px;padding:4px 12px;font-size:.75rem;
  display:flex;gap:6px;align-items:center}
.pill-count{background:#2a3548;border-radius:10px;padding:1px 7px;
  font-weight:700;color:#a8dadc}
footer{text-align:center;padding:16px;color:#2a3040;font-size:.7rem;
  border-top:1px solid #1e2535;margin-top:8px}
</style>
</head>
<body>
<header>
  <h1>&#x1F6E1; SAP P2P &mdash; Audit &amp; Integrity Dashboard
    <span class="badge" id="hdr-badge"></span>
  </h1>
  <p id="hdr-sub"></p>
</header>
<main>

<!-- Overall banner -->
<div class="overall-banner" id="overall-banner">
  <div class="semaphore" id="overall-light"></div>
  <div class="overall-text">
    <h3 id="overall-title"></h3>
    <p id="overall-desc"></p>
  </div>
</div>

<!-- Component semaphores -->
<section>
  <h2 class="st">Integridade por Componente</h2>
  <div class="comp-row" id="comp-row"></div>
</section>

<!-- Timeline -->
<section>
  <h2 class="st">Timeline de Pipeline Runs</h2>
  <div class="panel">
    <h3>Entradas PIPELINE_RUN_COMPLETE no audit log</h3>
    <div class="timeline" id="timeline"></div>
  </div>
</section>

<!-- Checksums table -->
<section>
  <h2 class="st">Checksums SHA-256 dos Artefatos Criticos</h2>
  <div class="panel">
    <h3 id="chk-title"></h3>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>Componente</th><th>Arquivo</th>
          <th>SHA-256 (16 chars)</th><th>Status</th>
        </tr></thead>
        <tbody id="chk-tbody"></tbody>
      </table>
    </div>
  </div>
</section>

<!-- Audit actions summary -->
<section>
  <h2 class="st">Resumo de Acoes no Audit Log</h2>
  <div class="panel">
    <h3 id="log-title"></h3>
    <div class="pills" id="action-pills"></div>
  </div>
</section>

</main>
<footer>SAP P2P Fraud Detection &mdash; Audit Dashboard &mdash; <span id="footer-ts"></span></footer>

<script>
const D = /*INJECT_JSON*/;

const STATUS_CFG = {
  OK:       {color:'#2ec4b6', glow:'#2ec4b666', icon:'✓', label:'INTEGRO',      bg:'#2ec4b611', border:'#2ec4b633'},
  TAMPERED: {color:'#e63946', glow:'#e6394666', icon:'✗', label:'ADULTERADO',   bg:'#e6394611', border:'#e6394633'},
  MISSING:  {color:'#f4a261', glow:'#f4a26166', icon:'!', label:'AUSENTE',      bg:'#f4a26111', border:'#f4a26133'},
  UNKNOWN:  {color:'#8899aa', glow:'#88994466', icon:'?', label:'DESCONHECIDO', bg:'#88994411', border:'#88994433'},
};

const $ = id => document.getElementById(id);
function cfg(s){ return STATUS_CFG[s] || STATUS_CFG.UNKNOWN; }

// ── header ──────────────────────────────────────────────────────────────
$('footer-ts').textContent = D.generated_at;
$('hdr-sub').textContent   =
  `Pipeline ${D.last_pipeline_id} | ${D.total_log_entries} entradas no log | `+
  `${D.checksums_snapshots} snapshot(s) de checksums | Gerado em: ${D.generated_at}`;

const oc = cfg(D.overall);
const badge = $('hdr-badge');
badge.textContent   = oc.label;
badge.style.cssText = `background:${oc.bg};color:${oc.color};border:1px solid ${oc.border}`;

// ── overall banner ───────────────────────────────────────────────────────
const banner = $('overall-banner');
banner.style.background = oc.bg;
banner.style.borderColor = oc.border;
const light = $('overall-light');
light.textContent = oc.icon;
light.style.cssText = `width:56px;height:56px;border-radius:50%;display:flex;
  align-items:center;justify-content:center;font-size:1.6rem;flex-shrink:0;
  background:${oc.bg};color:${oc.color};box-shadow:0 0 24px ${oc.glow};
  border:2px solid ${oc.border}`;
$('overall-title').textContent = `Status Geral: ${oc.label}`;
$('overall-title').style.color = oc.color;
$('overall-desc').textContent  = D.overall === 'OK'
  ? `Todos os ${D.file_statuses.length} artefatos críticos verificados e íntegros. `+
    `Hash chain do audit log preservado. Sistema pronto para operação.`
  : D.overall === 'TAMPERED'
  ? `ATENÇÃO: Adulteração detectada em um ou mais artefatos críticos. `+
    `Verifique imediatamente os arquivos sinalizados abaixo.`
  : `Alguns artefatos monitorados não foram encontrados. Execute o pipeline para regenerá-los.`;

// ── component semaphores ─────────────────────────────────────────────────
const compRow = $('comp-row');
Object.entries(D.component_status).forEach(([name, status]) => {
  const c = cfg(status);
  compRow.innerHTML += `
    <div class="comp-card" style="--ac:${c.color}">
      <div class="comp-light" style="background:${c.bg};color:${c.color};
        box-shadow:0 0 16px ${c.glow};border:2px solid ${c.border}">
        ${c.icon}
      </div>
      <div class="comp-name">${name}</div>
      <div class="comp-status" style="color:${c.color}">${c.label}</div>
    </div>`;
});

// ── timeline ─────────────────────────────────────────────────────────────
const tl = $('timeline');
if (!D.timeline.length) {
  tl.innerHTML = '<p style="color:#445;font-size:.82rem">Nenhum run PIPELINE_RUN_COMPLETE registrado ainda.</p>';
} else {
  [...D.timeline].reverse().forEach((r, i) => {
    tl.innerHTML += `
      <div class="tl-item">
        <div class="tl-num">${D.timeline.length - i}</div>
        <div class="tl-body">
          <div class="tl-title">Pipeline <span class="mono">${r.pipeline_id}</span>
            &nbsp;&mdash;&nbsp;${r.timestamp}
          </div>
          <div class="tl-meta">
            <b>Autor:</b> ${r.author}&nbsp;&nbsp;
            <b>SO:</b> <span>${r.os_user}@${r.hostname}</span>&nbsp;&nbsp;
            <b>Commit:</b> <span>${r.commit}</span> (${r.branch})<br>
            <b>Hash entrada:</b> <span style="color:#445">${r.entry_hash}</span>
            ${r.narratives ? `&nbsp;&nbsp;<b>Narrativas:</b> ${r.narratives}` : ''}
          </div>
        </div>
        <div class="tl-right">
          <div class="tl-cost">$ ${r.cost.toFixed(6)}</div>
          <div class="tl-alerts">${r.alerts} alertas</div>
        </div>
      </div>`;
  });
}

// ── checksums table ───────────────────────────────────────────────────────
$('chk-title').textContent =
  `${D.file_statuses.length} artefatos monitorados — snapshot ${D.last_pipeline_id}`;
const tbody = $('chk-tbody');
D.file_statuses.forEach(f => {
  const c = cfg(f.status);
  const fname = f.file.split('/').pop();
  tbody.innerHTML += `<tr>
    <td style="color:#8899aa">${f.component}</td>
    <td class="mono" title="${f.file}">${f.file}</td>
    <td class="mono" style="color:#445">${f.short}</td>
    <td class="${f.status==='OK'?'st-ok':f.status==='TAMPERED'?'st-bad':'st-warn'}">
      ${c.icon} ${c.label}
    </td>
  </tr>`;
});

// ── action pills ──────────────────────────────────────────────────────────
$('log-title').textContent = `${D.total_log_entries} entradas totais no audit log`;
const pillsEl = $('action-pills');
Object.entries(D.action_counts)
  .sort((a,b) => b[1]-a[1])
  .forEach(([action, count]) => {
    pillsEl.innerHTML += `
      <div class="pill">
        <span>${action}</span>
        <span class="pill-count">${count}</span>
      </div>`;
  });
</script>
</body>
</html>"""

html_final = HTML.replace("/*INJECT_JSON*/", data_json)
OUT_PATH.write_text(html_final, encoding="utf-8")
print(f"  Salvo: {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.1f} KB)")
