"""
scripts/version_docs.py
Verifica se houve mudanças em componentes críticos desde a última versão da
documentação. Se sim, cria docs/versions/TECHNICAL_DOCUMENTATION_vX.Y.md
e atualiza docs/TECHNICAL_DOCUMENTATION.md com o cabeçalho de versão.
"""
from __future__ import annotations
import json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent   # meu_portifolio/
DOCS_DIR  = ROOT / "docs"
VERS_DIR  = DOCS_DIR / "versions"
CURRENT   = DOCS_DIR / "TECHNICAL_DOCUMENTATION.md"
VERSION_REGISTRY = DOCS_DIR / "doc_versions.json"
CHANGELOG = ROOT / "CHANGELOG.md"

WATCHED_COMPONENTS = ["models/", "mlops/", "governance/", "scripts/", "explainer/", "api/"]

def _git(cmd: list, cwd: Path = REPO_ROOT) -> str:
    try:
        return subprocess.check_output(
            ["git"] + cmd, cwd=str(cwd), stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""

def _load_registry() -> list:
    if VERSION_REGISTRY.exists():
        try:
            return json.loads(VERSION_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_registry(versions: list) -> None:
    VERSION_REGISTRY.write_text(
        json.dumps(versions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def _next_version(versions: list) -> str:
    """Bump minor version: 1.0 → 1.1 → 1.2 …"""
    if not versions:
        return "1.0"
    last = versions[-1].get("version", "1.0")
    try:
        major, minor = last.split(".")
        return f"{major}.{int(minor)+1}"
    except Exception:
        return "1.0"

def _changed_components_since(commit_hash: str) -> list[str]:
    """Returns list of watched components that have changed since commit_hash."""
    if not commit_hash:
        return list(WATCHED_COMPONENTS)
    raw = _git(["diff", "--name-only", commit_hash, "HEAD"])
    changed = set()
    for line in raw.splitlines():
        rel = line.replace("fraud_detection/", "", 1)
        for comp in WATCHED_COMPONENTS:
            if rel.startswith(comp):
                changed.add(comp.rstrip("/"))
    return sorted(changed)

def _diff_summary_pt(changed_components: list[str]) -> str:
    """Generates a short Portuguese diff summary."""
    if not changed_components:
        return "Nenhuma alteração em componentes monitorados."
    comp_labels = {
        "models":     "Modelos de ML (Isolation Forest, AutoEncoder, Ensemble)",
        "mlops":      "Pipeline MLOps (orquestração, steps)",
        "governance": "Governança (audit log, versionamento, drift, custos, integridade)",
        "scripts":    "Scripts utilitários (dashboards, relatórios, changelog)",
        "explainer":  "Explicabilidade (SHAP, narrativas Claude API)",
        "api":        "API REST (FastAPI, RBAC, endpoints)",
    }
    items = [f"- **{comp_labels.get(c, c)}**" for c in changed_components]
    return (
        "Os seguintes componentes foram alterados desde a versão anterior:\n\n"
        + "\n".join(items)
    )

def _build_version_header(
    version: str,
    pipeline_id: str,
    git_short: str,
    git_author: str,
    changed_components: list[str],
    diff_summary: str,
    prev_version: str,
    timestamp: str,
) -> str:
    return (
        f"# Documentação Técnica v{version} — SAP P2P Fraud Detection System\n\n"
        f"> **Versão:** {version} | "
        f"**Pipeline:** `{pipeline_id}` | "
        f"**Commit:** `{git_short}`\n"
        f"> **Data:** {timestamp} | "
        f"**Autor:** {git_author}\n"
        f"> **Versão anterior:** {prev_version or 'N/A'}\n\n"
        f"---\n\n"
        f"## Resumo das Alterações nesta Versão\n\n"
        f"{diff_summary}\n\n"
        f"---\n\n"
    )

def run(pipeline_id: str = "manual") -> str | None:
    """
    Main entry point. Returns version string if new version created, else None.
    """
    VERS_DIR.mkdir(parents=True, exist_ok=True)

    if not CURRENT.exists():
        print("  [version_docs] TECHNICAL_DOCUMENTATION.md não encontrado — skipping.")
        return None

    registry = _load_registry()
    last_entry = registry[-1] if registry else None
    last_commit = last_entry.get("git_commit", "") if last_entry else ""
    prev_version = last_entry.get("version", "") if last_entry else ""

    # Check what changed since last doc version
    changed = _changed_components_since(last_commit)

    git_short  = _git(["rev-parse", "--short", "HEAD"])
    git_full   = _git(["rev-parse", "HEAD"])
    git_author = _git(["log", "-1", "--format=%an <%ae>"])
    timestamp  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not changed and last_entry:
        print(f"  [version_docs] Sem alterações em componentes monitorados. "
              f"Documentação na versão {prev_version}.")
        return None

    new_version = _next_version(registry)
    diff_summary = _diff_summary_pt(changed)
    header = _build_version_header(
        version=new_version,
        pipeline_id=pipeline_id,
        git_short=git_short,
        git_author=git_author,
        changed_components=changed,
        diff_summary=diff_summary,
        prev_version=prev_version,
        timestamp=timestamp,
    )

    # Read current doc body (strip existing version header if present)
    body = CURRENT.read_text(encoding="utf-8")
    # Remove old version header block if it exists (between first # and the next ---)
    body_clean = re.sub(
        r'^# Documentação Técnica v[\d\.]+.*?^---\n\n## Resumo.*?^---\n\n',
        '',
        body,
        flags=re.DOTALL | re.MULTILINE,
    )

    versioned_content = header + body_clean.lstrip()

    # Save versioned copy
    version_file = VERS_DIR / f"TECHNICAL_DOCUMENTATION_v{new_version}.md"
    version_file.write_text(versioned_content, encoding="utf-8")

    # Update current doc with new header
    CURRENT.write_text(versioned_content, encoding="utf-8")

    # Update registry
    registry.append({
        "version":    new_version,
        "pipeline_id": pipeline_id,
        "git_commit": git_full,
        "git_short":  git_short,
        "git_author": git_author,
        "timestamp":  timestamp,
        "changed_components": changed,
        "file":       version_file.name,
    })
    _save_registry(registry)

    # Add entry to CHANGELOG
    if CHANGELOG.exists():
        log_entry = (
            f"\n## 📖 [DOC v{new_version}] Documentacao atualizada — `{git_short}`\n\n"
            f"| Campo | Valor |\n|---|---|\n"
            f"| **Versao** | `{new_version}` |\n"
            f"| **Data** | `{timestamp}` |\n"
            f"| **Autor** | {git_author} |\n"
            f"| **Pipeline** | `{pipeline_id}` |\n"
            f"| **Arquivo** | `{version_file.name}` |\n\n"
            f"{diff_summary}\n\n---\n\n"
        )
        current_log = CHANGELOG.read_text(encoding="utf-8")
        # Insert after header separator
        lines = current_log.split("\n")
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip() == "---" and i > 0:
                insert_at = i + 2
                break
        before = "\n".join(lines[:insert_at])
        after  = "\n".join(lines[insert_at:])
        CHANGELOG.write_text(before + "\n" + log_entry + after, encoding="utf-8")

    print(f"  [version_docs] Nova versao criada: v{new_version} → {version_file.name}")
    print(f"    Componentes alterados: {', '.join(changed) or 'todos (primeiro run)'}")
    return new_version


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--pipeline-id", default="manual")
    args = p.parse_args()
    result = run(args.pipeline_id)
    if result:
        print(f"Versão criada: v{result}")
    else:
        print("Nenhuma nova versão necessária.")
