"""
governance/integrity.py
────────────────────────────────────────────────────────────────────────
Motor de integridade SHA-256 para arquivos críticos do projeto.

Responsabilidades:
  - Calcular e persistir checksums de modelos .pkl, alertas.parquet e
    quaisquer outros artefatos críticos
  - Verificar adulteração comparando hash atual vs. hash registrado
  - Salvar governance/checksums.json (append com histórico por pipeline_id)

Uso standalone:
    python governance/integrity.py          # verifica arquivos críticos
    python governance/integrity.py --check  # verifica + sai com código 1 se adulterado
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CHECKSUMS_PATH = ROOT / "governance" / "checksums.json"

# Padrões de arquivos que devem ter integridade garantida
CRITICAL_PATTERNS: List[tuple[str, str]] = [
    ("models/registry", "*.pkl"),
    ("data/processed",  "*.parquet"),
    ("governance",      "AUDIT_LOG.json"),
    ("governance",      "model_versions.json"),
    ("governance",      "cost_report.json"),
    ("governance",      "checksums.json"),   # o próprio ficheiro (self-referência removida ao ler)
]


def sha256_file(path: Path) -> str:
    """Returns SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_critical_files(root: Path = ROOT) -> Dict[str, str]:
    """
    Walks CRITICAL_PATTERNS and returns {relative_path: sha256}.
    Skips checksums.json itself to avoid circular dependency.
    """
    result: Dict[str, str] = {}
    for subdir, pattern in CRITICAL_PATTERNS:
        target = root / subdir
        if not target.exists():
            continue
        files = sorted(target.glob(pattern)) if target.is_dir() else [target]
        for f in files:
            if not f.is_file():
                continue
            rel = f.relative_to(root).as_posix()
            if rel == "governance/checksums.json":
                continue   # skip self
            result[rel] = sha256_file(f)
    return result


def save_checksums(
    pipeline_id: str,
    checksums: Dict[str, str],
    path: Path = CHECKSUMS_PATH,
) -> None:
    """
    Append-only: adds a new snapshot entry keyed by pipeline_id + timestamp.
    Format:
      [
        { "pipeline_id": "abc123", "timestamp": "...", "files": { "path": "sha256", ... } },
        ...
      ]
    """
    history: List[dict] = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            history = []

    entry = {
        "pipeline_id": pipeline_id,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "file_count":  len(checksums),
        "files":       checksums,
    }
    history.append(entry)

    path.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def verify_checksums(
    pipeline_id: Optional[str] = None,
    path: Path = CHECKSUMS_PATH,
    root: Path = ROOT,
) -> tuple[bool, List[dict]]:
    """
    Compares current file hashes against the last recorded snapshot
    (or the snapshot of a specific pipeline_id).

    Returns (all_ok: bool, issues: list[dict])
    Issues list is empty when all_ok is True.
    """
    if not path.exists():
        return True, []

    history: List[dict] = json.loads(path.read_text(encoding="utf-8"))
    if not history:
        return True, []

    # Pick snapshot to compare against
    if pipeline_id:
        snapshots = [s for s in history if s["pipeline_id"] == pipeline_id]
        snapshot  = snapshots[-1] if snapshots else history[-1]
    else:
        snapshot = history[-1]

    recorded  = snapshot["files"]
    current   = collect_critical_files(root)
    issues: List[dict] = []

    for rel, old_hash in recorded.items():
        if rel not in current:
            issues.append({"file": rel, "status": "MISSING", "expected": old_hash, "found": None})
        elif current[rel] != old_hash:
            issues.append({
                "file":     rel,
                "status":   "TAMPERED",
                "expected": old_hash,
                "found":    current[rel],
            })

    return len(issues) == 0, issues


def print_report(checksums: Dict[str, str], issues: List[dict]) -> None:
    W = 64
    print(f"\n{'═'*W}")
    print(f"  RELATORIO DE INTEGRIDADE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*W}")
    print(f"\n  Arquivos monitorados: {len(checksums)}")
    for rel, digest in checksums.items():
        status = "✓"
        if any(i["file"] == rel for i in issues):
            issue  = next(i for i in issues if i["file"] == rel)
            status = "✗ ADULTERADO" if issue["status"] == "TAMPERED" else "✗ AUSENTE"
        print(f"  {status}  {rel}")
        print(f"        SHA-256: {digest[:32]}…")

    if issues:
        print(f"\n  ⚠ {len(issues)} PROBLEMA(S) DETECTADO(S):")
        for iss in issues:
            print(f"    [{iss['status']}] {iss['file']}")
            print(f"      esperado : {iss['expected'][:32] if iss['expected'] else 'N/A'}…")
            print(f"      encontrado: {iss['found'][:32] if iss['found'] else 'AUSENTE'}…")
    else:
        print(f"\n  ✓ Todos os arquivos íntegros.")
    print(f"{'═'*W}\n")


# ── CLI standalone ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verifica integridade SHA-256 dos artefatos críticos.")
    parser.add_argument("--check", action="store_true",
                        help="Sai com código 1 se adulteração detectada")
    parser.add_argument("--pipeline-id", default=None,
                        help="Compara com snapshot de um pipeline_id específico")
    args = parser.parse_args()

    checksums = collect_critical_files()
    ok, issues = verify_checksums(pipeline_id=args.pipeline_id)
    print_report(checksums, issues)

    if args.check and not ok:
        sys.exit(1)
