"""
scripts/security_check.py
────────────────────────────────────────────────────────────────────────
Auditoria de segurança do projeto. Varre arquivos em busca de credenciais
expostas, verifica .gitignore e .claude/settings.json, e gera
security/security_report.json.

Usado como Step 0 do pipeline — bloqueia a execução se encontrar
credencial real exposta.

Uso standalone:
    python scripts/security_check.py            # relatório + saída 0 se OK
    python scripts/security_check.py --strict   # saída 1 se qualquer FAIL
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT         = Path(__file__).resolve().parent.parent
REPORT_DIR   = ROOT / "security"
REPORT_PATH  = REPORT_DIR / "security_report.json"
REPORT_DIR.mkdir(exist_ok=True)

# ── patterns that indicate a REAL secret (not a placeholder) ──────────────────
# A real Anthropic key looks like:  sk-ant-api03-<base64-43-chars>
# Placeholders used in this repo:   sk-ant-..., sk-ant-api03-..., sua_chave_aqui
REAL_SECRET_PATTERNS = [
    # Anthropic key: sk-ant-api03- followed by 20+ non-dot, non-space chars
    (r'sk-ant-api\d+-[A-Za-z0-9_\-]{20,}', "Anthropic API key (real)"),
    # Generic Bearer token (≥ 32 hex/b64 chars)
    (r'Bearer\s+[A-Za-z0-9+/=]{32,}',       "Bearer token"),
    # Assignments like token=<real-value>, api_key=<real-value>
    (r'(?:token|api_key|apikey)\s*=\s*["\']?[A-Za-z0-9+/=_\-]{32,}["\']?',
     "Hardcoded token/api_key assignment"),
    # AWS-style keys
    (r'AKIA[0-9A-Z]{16}',                   "AWS Access Key ID"),
    (r'(?:aws_secret|AWS_SECRET)[^=]*=\s*[A-Za-z0-9+/]{40}',
     "AWS Secret Access Key"),
    # Private key headers
    (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private key block"),
]

# Files and dirs to skip entirely
SKIP_DIRS  = {".git", "__pycache__", ".venv", "venv", "env",
              "node_modules", ".mypy_cache", ".pytest_cache"}
SKIP_EXTS  = {".pyc", ".pyo", ".pkl", ".parquet", ".xlsx",
              ".png", ".jpg", ".gif", ".ico", ".woff", ".ttf"}
SKIP_FILES = {"security_report.json"}   # avoid circular self-scan

# Files that are expected to contain placeholder-like text — lower false-positive risk
PLACEHOLDER_HINT = re.compile(
    r'\.{3}|sua_chave_aqui|change.this|your[_\-]key|example|placeholder|troque',
    re.IGNORECASE
)

# ── required .gitignore entries ───────────────────────────────────────────────
REQUIRED_GITIGNORE = [".env", ".env.*", "*.key", "*.pem", "*secret*"]

# ── checks ────────────────────────────────────────────────────────────────────

def check_secrets_in_files() -> list[dict]:
    """Scan all text files for real secret patterns."""
    findings: list[dict] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_EXTS:
            continue
        if path.name in SKIP_FILES:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pattern, label in REAL_SECRET_PATTERNS:
            for match in re.finditer(pattern, text):
                line_no = text[:match.start()].count("\n") + 1
                context = text[max(0, match.start()-40):match.end()+40].replace("\n", " ").strip()

                # Skip if the surrounding context looks like a placeholder
                if PLACEHOLDER_HINT.search(context):
                    continue

                findings.append({
                    "severity": "CRITICAL",
                    "check":    "secret_in_file",
                    "label":    label,
                    "file":     str(path.relative_to(ROOT)),
                    "line":     line_no,
                    "context":  context[:120],
                    "pattern":  pattern,
                })

    return findings


def check_gitignore() -> list[dict]:
    """Verify .gitignore contains all required secret patterns."""
    findings: list[dict] = []
    gi_path = ROOT / ".gitignore"

    if not gi_path.exists():
        return [{
            "severity": "FAIL",
            "check":    "gitignore_exists",
            "message":  ".gitignore não encontrado — segredos podem ser commitados acidentalmente.",
            "file":     ".gitignore",
        }]

    gi_text = gi_path.read_text(encoding="utf-8")
    for entry in REQUIRED_GITIGNORE:
        # Check for exact line or glob match
        escaped = re.escape(entry).replace(r"\*", r"\*")
        if not re.search(rf"^{escaped}$", gi_text, re.MULTILINE):
            findings.append({
                "severity": "WARN",
                "check":    "gitignore_entry",
                "message":  f"'{entry}' não está no .gitignore.",
                "file":     ".gitignore",
            })

    return findings


def check_env_not_tracked() -> list[dict]:
    """Check that no real .env file is tracked by git."""
    findings: list[dict] = []
    import subprocess
    try:
        tracked = subprocess.check_output(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=str(ROOT), stderr=subprocess.DEVNULL, text=True
        ).strip()
        if tracked:
            findings.append({
                "severity": "CRITICAL",
                "check":    "env_tracked",
                "message":  ".env está sendo rastreado pelo git. Execute: git rm --cached .env",
                "file":     ".env",
            })
    except subprocess.CalledProcessError:
        pass  # file not tracked — good
    return findings


def check_claude_settings() -> list[dict]:
    """Inspect .claude/settings.json for hooks that auto-execute code."""
    findings: list[dict] = []
    settings_path = ROOT.parent / ".claude" / "settings.json"

    if not settings_path.exists():
        return [{
            "severity": "INFO",
            "check":    "claude_settings",
            "message":  ".claude/settings.json não encontrado — sem hooks configurados.",
        }]

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        findings.append({
            "severity": "WARN",
            "check":    "claude_settings_parse",
            "message":  ".claude/settings.json existe mas não é JSON válido.",
            "file":     str(settings_path),
        })
        return findings

    hooks = settings.get("hooks", {})
    if hooks:
        for event, commands in hooks.items():
            for cmd in (commands if isinstance(commands, list) else [commands]):
                cmd_str = str(cmd)
                # Flag hooks that could exfiltrate data
                suspicious_patterns = ["curl ", "wget ", "http", "nc ", "ncat ",
                                       "python -c", "eval(", "exec(", "bash -c"]
                is_suspicious = any(p in cmd_str.lower() for p in suspicious_patterns)
                severity = "WARN" if is_suspicious else "INFO"
                findings.append({
                    "severity": severity,
                    "check":    "claude_hook",
                    "event":    event,
                    "command":  cmd_str[:200],
                    "message":  (
                        f"Hook '{event}' executa: {cmd_str[:80]}"
                        + (" — SUSPEITO: pode exfiltrar dados (CVE-2026-21852)" if is_suspicious else "")
                    ),
                })
    else:
        findings.append({
            "severity": "INFO",
            "check":    "claude_settings",
            "message":  ".claude/settings.json existe mas não tem hooks configurados.",
        })

    return findings


def check_claude_code_version() -> list[dict]:
    """Check installed Claude Code version against known vulnerable versions."""
    import subprocess
    findings: list[dict] = []

    try:
        output = subprocess.check_output(
            ["claude", "--version"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        # Parse version like "1.2.34" or "Claude Code 1.2.34"
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', output)
        if match:
            major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
            version_str = f"{major}.{minor}.{patch}"

            vulns = []
            # CVE-2025-59536: fixed in 1.0.111
            if (major, minor, patch) < (1, 0, 111):
                vulns.append("CVE-2025-59536 (code injection via trust dialog, CVSS 8.8) — atualize para ≥ 1.0.111")
            # CVE-2026-21852: fixed in 2.0.65
            if (major, minor, patch) < (2, 0, 65):
                vulns.append("CVE-2026-21852 (API key exfiltration via malicious repo, CVSS 7.5) — atualize para ≥ 2.0.65")

            if vulns:
                for v in vulns:
                    findings.append({
                        "severity": "CRITICAL",
                        "check":    "claude_code_version",
                        "version":  version_str,
                        "message":  f"Claude Code v{version_str} é vulnerável: {v}",
                    })
            else:
                findings.append({
                    "severity": "OK",
                    "check":    "claude_code_version",
                    "version":  version_str,
                    "message":  f"Claude Code v{version_str} — sem CVEs conhecidos críticos.",
                })
        else:
            findings.append({
                "severity": "WARN",
                "check":    "claude_code_version",
                "message":  f"Não foi possível parsear a versão do Claude Code: {output}",
            })
    except (FileNotFoundError, subprocess.CalledProcessError):
        findings.append({
            "severity": "INFO",
            "check":    "claude_code_version",
            "message":  "Claude Code não instalado ou não encontrado no PATH.",
        })

    return findings


# ── report builder ─────────────────────────────────────────────────────────────

def run_all_checks() -> tuple[list[dict], bool]:
    """Run all checks. Returns (all_findings, has_critical)."""
    all_findings: list[dict] = []

    print("  [security] Verificando credenciais expostas em arquivos...")
    all_findings += check_secrets_in_files()

    print("  [security] Verificando .gitignore...")
    all_findings += check_gitignore()

    print("  [security] Verificando .env rastreado pelo git...")
    all_findings += check_env_not_tracked()

    print("  [security] Verificando .claude/settings.json...")
    all_findings += check_claude_settings()

    print("  [security] Verificando versão do Claude Code...")
    all_findings += check_claude_code_version()

    has_critical = any(f["severity"] == "CRITICAL" for f in all_findings)
    return all_findings, has_critical


def build_report(findings: list[dict], has_critical: bool) -> dict:
    counts = {"CRITICAL": 0, "FAIL": 0, "WARN": 0, "INFO": 0, "OK": 0}
    for f in findings:
        counts[f.get("severity", "INFO")] = counts.get(f.get("severity", "INFO"), 0) + 1

    overall = (
        "CRITICAL" if counts["CRITICAL"] > 0 else
        "FAIL"     if counts["FAIL"]     > 0 else
        "WARN"     if counts["WARN"]     > 0 else
        "OK"
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall":      overall,
        "counts":       counts,
        "findings":     findings,
        "cve_reference": {
            "CVE-2025-59536": {
                "description": "Code injection via trust dialog bypass in Claude Code < 1.0.111",
                "cvss":        "8.8 HIGH",
                "fix":         "Update Claude Code to >= 1.0.111",
                "url":         "https://nvd.nist.gov/vuln/detail/CVE-2025-59536",
            },
            "CVE-2026-21852": {
                "description": "API key exfiltration via malicious repository in Claude Code < 2.0.65",
                "cvss":        "7.5 HIGH",
                "fix":         "Update Claude Code to >= 2.0.65",
                "url":         "https://nvd.nist.gov/vuln/detail/CVE-2026-21852",
            },
        },
    }


def print_summary(report: dict) -> None:
    W = 60
    overall = report["overall"]
    icon = {"OK": "✓", "WARN": "⚠", "FAIL": "✗", "CRITICAL": "✗✗"}.get(overall, "?")
    color_map = {"OK": "\033[92m", "WARN": "\033[93m",
                 "FAIL": "\033[91m", "CRITICAL": "\033[91m"}
    reset = "\033[0m"
    color = color_map.get(overall, "")

    print(f"\n{'═'*W}")
    print(f"  {color}AUDITORIA DE SEGURANÇA — {icon} {overall}{reset}")
    print(f"{'═'*W}")
    c = report["counts"]
    print(f"  CRITICAL: {c['CRITICAL']}  |  FAIL: {c['FAIL']}  |  "
          f"WARN: {c['WARN']}  |  INFO: {c['INFO']}  |  OK: {c['OK']}")
    print(f"{'─'*W}")

    for f in report["findings"]:
        sev   = f.get("severity", "INFO")
        col   = color_map.get(sev, "")
        label = f"{col}[{sev}]{reset}"
        msg   = f.get("message", f.get("label", ""))
        loc   = f" — {f['file']}:{f['line']}" if "file" in f and "line" in f else \
                f" — {f.get('file','')}" if "file" in f else ""
        print(f"  {label} {msg}{loc}")

    print(f"{'─'*W}")
    print(f"  Relatório: security/security_report.json")
    print(f"{'═'*W}\n")


# ── entry point ────────────────────────────────────────────────────────────────

def main(strict: bool = False) -> bool:
    """Returns True if safe to proceed, False if critical findings."""
    print("\n[Step 0] Auditoria de segurança...")
    findings, has_critical = run_all_checks()
    report = build_report(findings, has_critical)

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print_summary(report)

    if has_critical:
        print("  ⛔ BLOQUEADO: credencial exposta ou vulnerabilidade crítica detectada.")
        print("     Corrija os itens CRITICAL antes de continuar.\n")
        return False

    if strict and report["overall"] in ("FAIL", "WARN"):
        print("  ⚠ Modo estrito: execução bloqueada por FAIL/WARN.\n")
        return False

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="Bloqueia também em WARN/FAIL (não só CRITICAL)")
    args = parser.parse_args()
    ok = main(strict=args.strict)
    sys.exit(0 if ok else 1)
