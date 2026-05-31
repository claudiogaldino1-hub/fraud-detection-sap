"""
scripts/update_changelog.py
────────────────────────────────────────────────────────────────────────
Registra cada pipeline run no CHANGELOG.md e no governance/AUDIT_LOG.json
com rastreabilidade completa:

  - Usuário do SO + hostname
  - Autor e email do git config
  - Hash do commit atual do código
  - Arquivos críticos alterados desde o último run
  - Checksums SHA-256 dos artefatos críticos
  - Alertas gerados + custo do run

Uso (chamado automaticamente pelo pipeline, ou manualmente):
    python scripts/update_changelog.py --pipeline-id abc123 --run-type pipeline
    python scripts/update_changelog.py --run-type docs
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHANGELOG_PATH = ROOT / "CHANGELOG.md"
AUDIT_LOG_PATH = ROOT / "governance" / "AUDIT_LOG.json"
COST_REPORT    = ROOT / "governance" / "cost_report.json"
ALERTS_PATH    = ROOT / "data" / "processed" / "alerts.parquet"
CHECKSUMS_PATH = ROOT / "governance" / "checksums.json"

# Diretórios monitorados para mudanças de código
WATCHED_DIRS = ["models", "governance", "mlops", "explainer", "api", "data/generators"]

# Tipos de mudança e padrões de arquivo associados
CHANGE_TYPE_MAP = {
    "models/":           "modelo",
    "governance/":       "governanca",
    "mlops/":            "pipeline",
    "explainer/":        "explicabilidade",
    "api/":              "api",
    "data/generators/":  "dados",
    "scripts/":          "script",
    "docs/":             "documentacao",
    "reports/":          "relatorio",
    "tests/":            "teste",
}

CHANGE_EMOJI = {
    "modelo":          "🤖",
    "governanca":      "🛡️",
    "pipeline":        "⚙️",
    "explicabilidade": "🔍",
    "api":             "🌐",
    "dados":           "📦",
    "script":          "📜",
    "documentacao":    "📖",
    "relatorio":       "📊",
    "teste":           "🧪",
    "pipeline_run":    "🚀",
}


# ── git helpers ────────────────────────────────────────────────────────────

def _git(cmd: List[str], cwd: Path = ROOT.parent) -> str:
    try:
        return subprocess.check_output(
            ["git"] + cmd, cwd=str(cwd), stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""


def get_git_info() -> Dict[str, str]:
    repo_root = ROOT.parent  # meu_portifolio/
    return {
        "commit_hash":    _git(["rev-parse", "HEAD"],            cwd=repo_root),
        "commit_short":   _git(["rev-parse", "--short", "HEAD"], cwd=repo_root),
        "commit_message": _git(["log", "-1", "--format=%s"],     cwd=repo_root),
        "branch":         _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root),
        "author_name":    _git(["config", "user.name"],          cwd=repo_root),
        "author_email":   _git(["config", "user.email"],         cwd=repo_root),
        "repo_url":       _git(["remote", "get-url", "origin"],  cwd=repo_root),
    }


def get_changed_files_since_last_run(watchdirs: List[str], repo_root: Path = ROOT.parent) -> List[Dict]:
    """
    Returns files in watched dirs that changed in the last git commit.
    Falls back to unstaged changes if no commit found.
    """
    changed: List[Dict] = []
    # Files changed in last commit
    raw = _git(["diff-tree", "--no-commit-id", "-r", "--name-status", "HEAD"], cwd=repo_root)
    for line in raw.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, filepath = parts
        rel = filepath.replace("fraud_detection/", "", 1)
        for watched in watchdirs:
            if rel.startswith(watched):
                change_type = next(
                    (v for k, v in CHANGE_TYPE_MAP.items() if rel.startswith(k)),
                    "codigo"
                )
                changed.append({
                    "file":        rel,
                    "git_status":  status,   # A=added, M=modified, D=deleted
                    "change_type": change_type,
                })
                break
    return changed


def get_system_info() -> Dict[str, str]:
    try:
        login = os.getlogin()
    except OSError:
        login = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    return {
        "os_user":       login,
        "hostname":      socket.gethostname(),
        "platform":      platform.platform(),
        "python_version": platform.python_version(),
    }


# ── cost / alert helpers ───────────────────────────────────────────────────

def load_cost_report() -> Optional[Dict]:
    if COST_REPORT.exists():
        try:
            return json.loads(COST_REPORT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def load_alert_count() -> int:
    if ALERTS_PATH.exists():
        try:
            import pandas as pd
            return len(pd.read_parquet(ALERTS_PATH))
        except Exception:
            pass
    return 0


def load_checksums_snapshot(pipeline_id: str) -> Optional[Dict]:
    if CHECKSUMS_PATH.exists():
        try:
            history = json.loads(CHECKSUMS_PATH.read_text(encoding="utf-8"))
            matches = [s for s in history if s.get("pipeline_id") == pipeline_id]
            return matches[-1] if matches else (history[-1] if history else None)
        except Exception:
            pass
    return None


# ── CHANGELOG writer ───────────────────────────────────────────────────────

def _read_changelog() -> str:
    if CHANGELOG_PATH.exists():
        return CHANGELOG_PATH.read_text(encoding="utf-8")
    return ""


def _build_changelog_entry(
    pipeline_id: str,
    run_type: str,
    git: Dict,
    sys_info: Dict,
    changed_files: List[Dict],
    cost: Optional[Dict],
    alert_count: int,
    checksums_snap: Optional[Dict],
    timestamp: str,
) -> str:
    emoji = CHANGE_EMOJI.get(run_type, "🔧")
    lines = [
        f"## {emoji} [{timestamp[:10]}] {run_type.upper()} — pipeline `{pipeline_id}`",
        f"",
        f"| Campo            | Valor |",
        f"|------------------|-------|",
        f"| **Data/hora**    | `{timestamp}` |",
        f"| **Autor**        | {git.get('author_name', '—')} &lt;{git.get('author_email', '—')}&gt; |",
        f"| **Usuário SO**   | `{sys_info['os_user']}` @ `{sys_info['hostname']}` |",
        f"| **Commit**       | `{git.get('commit_short', '—')}` — {git.get('commit_message', '—')} |",
        f"| **Branch**       | `{git.get('branch', '—')}` |",
        f"| **Hash completo**| `{git.get('commit_hash', '—')}` |",
        f"| **Alertas**      | {alert_count} |",
    ]

    if cost:
        cs = cost.get("cost_summary", {})
        lines += [
            f"| **Custo total**  | `${cs.get('total_estimated_usd', 0):.6f}` USD |",
            f"| **Compute**      | `${cs.get('compute_aws_ec2_usd', 0):.6f}` (AWS EC2) |",
            f"| **Armazenamento**| `${cs.get('storage_aws_s3_monthly_usd', 0):.6f}` (S3/mês) |",
            f"| **Claude API**   | `${cs.get('claude_api_usd', 0):.6f}` |",
        ]
        narratives = cost.get("claude_api", {}).get("narratives_generated", 0)
        if narratives:
            lines.append(f"| **Narrativas**   | {narratives} geradas |")

    lines.append("")

    if changed_files:
        lines.append("### Arquivos críticos alterados neste run")
        lines.append("")
        for cf in changed_files:
            status_label = {"A": "adicionado", "M": "modificado", "D": "removido"}.get(
                cf["git_status"], cf["git_status"]
            )
            e = CHANGE_EMOJI.get(cf["change_type"], "📄")
            lines.append(f"- {e} `{cf['file']}` — {status_label} ({cf['change_type']})")
        lines.append("")

    if checksums_snap:
        lines.append("### Checksums SHA-256 dos artefatos críticos")
        lines.append("")
        lines.append("| Arquivo | SHA-256 (primeiros 32 chars) |")
        lines.append("|---------|------------------------------|")
        for fp, digest in checksums_snap.get("files", {}).items():
            lines.append(f"| `{fp}` | `{digest[:32]}…` |")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def update_changelog(
    pipeline_id: str,
    run_type: str = "pipeline_run",
) -> str:
    """
    Inserts a new entry at the top of CHANGELOG.md (below the header).
    Returns the entry text.
    """
    timestamp  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    git        = get_git_info()
    sys_info   = get_system_info()
    changed    = get_changed_files_since_last_run(WATCHED_DIRS)
    cost       = load_cost_report()
    alerts     = load_alert_count()
    chksums    = load_checksums_snapshot(pipeline_id)

    entry = _build_changelog_entry(
        pipeline_id, run_type, git, sys_info, changed, cost, alerts, chksums, timestamp
    )

    current = _read_changelog()

    # Build header if file is new
    if not current.strip():
        header = (
            "# CHANGELOG — SAP P2P Fraud Detection System\n\n"
            "> Gerado automaticamente pelo pipeline. "
            "Cada entrada registra autoria, custo, alertas e checksums do run.\n\n"
            "---\n\n"
        )
        content = header + entry
    else:
        # Insert after first separator line (---) or at top after first heading
        lines = current.split("\n")
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip() == "---" and i > 0:
                insert_at = i + 2   # after the --- and blank line
                break
        before = "\n".join(lines[:insert_at])
        after  = "\n".join(lines[insert_at:])
        content = before + "\n" + entry + after

    CHANGELOG_PATH.write_text(content, encoding="utf-8")
    return entry


# ── audit_log enrichment ───────────────────────────────────────────────────

def enrich_audit_log(
    pipeline_id: str,
    run_type: str,
    git: Dict,
    sys_info: Dict,
    changed_files: List[Dict],
    cost: Optional[Dict],
    alert_count: int,
    checksums_snap: Optional[Dict],
) -> None:
    """
    Appends a rich PIPELINE_RUN_COMPLETE entry to the existing audit log,
    adding OS user, hostname, git hash, changed files and checksums —
    fields not captured by the lightweight AuditLogger used during the run.
    """
    if not AUDIT_LOG_PATH.exists():
        return

    try:
        entries = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        entries = []

    import hashlib

    def _hash(e: dict) -> str:
        return hashlib.sha256(
            json.dumps(e, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    prev_hash = _hash({k: v for k, v in entries[-1].items()
                       if k != "entry_hash"}) if entries else "genesis"

    cs = (cost or {}).get("cost_summary", {})
    entry: Dict = {
        "seq":             len(entries) + 1,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "action":          "PIPELINE_RUN_COMPLETE",
        "pipeline_id":     pipeline_id,
        "run_type":        run_type,
        # identity
        "git_commit":      git.get("commit_hash", ""),
        "git_commit_short": git.get("commit_short", ""),
        "git_branch":      git.get("branch", ""),
        "git_author":      f"{git.get('author_name','')} <{git.get('author_email','')}>",
        "os_user":         sys_info["os_user"],
        "hostname":        sys_info["hostname"],
        "platform":        sys_info["platform"],
        # results
        "alert_count":     alert_count,
        "changed_files":   changed_files,
        # cost
        "cost_total_usd":      cs.get("total_estimated_usd", 0),
        "cost_compute_usd":    cs.get("compute_aws_ec2_usd", 0),
        "cost_storage_usd":    cs.get("storage_aws_s3_monthly_usd", 0),
        "cost_claude_usd":     cs.get("claude_api_usd", 0),
        "narratives_generated": (cost or {}).get("claude_api", {}).get("narratives_generated", 0),
        # checksums
        "checksums_snapshot":  checksums_snap.get("files", {}) if checksums_snap else {},
        # chain
        "prev_hash":       prev_hash,
    }
    entry["entry_hash"] = _hash(entry)
    entries.append(entry)

    AUDIT_LOG_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ── main orchestrator ──────────────────────────────────────────────────────

def run(pipeline_id: str, run_type: str = "pipeline_run") -> None:
    print(f"\n[changelog] Registrando run {pipeline_id} ({run_type})...")

    git      = get_git_info()
    sys_info = get_system_info()
    changed  = get_changed_files_since_last_run(WATCHED_DIRS)
    cost     = load_cost_report()
    alerts   = load_alert_count()
    chksums  = load_checksums_snapshot(pipeline_id)

    # Update CHANGELOG.md
    update_changelog(pipeline_id, run_type)
    print(f"  CHANGELOG.md atualizado")

    # Enrich audit log
    enrich_audit_log(pipeline_id, run_type, git, sys_info, changed, cost, alerts, chksums)
    print(f"  AUDIT_LOG.json enriquecido")

    # Summary
    print(f"  Commit : {git.get('commit_short','?')} — {git.get('commit_message','?')}")
    print(f"  Usuário: {sys_info['os_user']}@{sys_info['hostname']}")
    print(f"  Alertas: {alerts} | Custo: "
          f"${(cost or {}).get('cost_summary',{}).get('total_estimated_usd',0):.6f} USD")
    if changed:
        print(f"  Arquivos críticos alterados: {len(changed)}")
        for c in changed:
            print(f"    {c['git_status']} {c['file']}")
    if chksums:
        print(f"  Checksums registrados: {chksums['file_count']} arquivos")


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-id", default="manual",
                        help="ID do pipeline run")
    parser.add_argument("--run-type", default="pipeline_run",
                        choices=["pipeline_run","modelo","documentacao",
                                 "relatorio","teste","script","manual"],
                        help="Tipo de mudança para o CHANGELOG")
    args = parser.parse_args()
    run(args.pipeline_id, args.run_type)
