"""
End-to-end MLOps pipeline:
1. Generate / load data
2. Inject fraud
3. Train ensemble
4. Inference
5. Compute SHAP
6. Generate narratives (Claude API)
7. Save drift baseline
8. Persist alerts
9. Cost report  ← new
"""

import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from data.generators import FraudInjector, SAPDataGenerator
from explainer import SHAPExplainer, generate_batch_narratives
from governance.audit_log import AuditLogger
from governance.cost_monitor import CostMonitor
from governance.data_drift import DataDriftDetector
from governance.integrity import collect_critical_files, save_checksums, verify_checksums
from governance.model_versioning import ModelVersionRegistry
from models import EnsembleDetector


def run_pipeline(
    regenerate_data: bool = False,
    ae_epochs: int = 30,
    run_by: str = "pipeline",
    generate_narratives: bool = True,
    narrative_limit: int = 20,
) -> pd.DataFrame:
    """
    Runs the full pipeline and returns the alerts DataFrame.
    Set generate_narratives=False to skip Claude API calls (useful for unit tests).
    """
    audit       = AuditLogger()
    registry    = ModelVersionRegistry()
    pipeline_id = str(uuid.uuid4())[:8]
    monitor     = CostMonitor(pipeline_id=pipeline_id)

    audit.log("PIPELINE_START", user=run_by, details={"pipeline_id": pipeline_id})
    print(f"\n{'='*60}")
    print(f"Pipeline {pipeline_id} started at {datetime.utcnow().isoformat()}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # Step 1: Data
    # ------------------------------------------------------------------
    print("Step 1: Loading/generating SAP data...")
    raw_dir = Path("data/raw")

    with monitor.track_step("Step 1 — Gerar/carregar dados SAP"):
        if regenerate_data or not any(raw_dir.glob("*.parquet")):
            generator = SAPDataGenerator(n_vendors=300, n_pos=2000, n_invoices=2500)
            tables = generator.generate_all(save=True)
            print(f"  Generated {len(tables)} SAP tables.")
        else:
            tables = SAPDataGenerator.load_all()
            print(f"  Loaded {len(tables)} tables from disk.")

    # ------------------------------------------------------------------
    # Step 2: Fraud injection
    # ------------------------------------------------------------------
    print("Step 2: Injecting fraud scenarios...")
    with monitor.track_step("Step 2 — Injecao de fraudes"):
        injector = FraudInjector(tables, fraud_rate=0.02)
        tables   = injector.inject_all()
        fraud_log = injector.fraud_log
    print(f"  Injected {len(fraud_log)} fraud records across {fraud_log['table'].nunique()} tables.")

    # ------------------------------------------------------------------
    # Step 3: Train ensemble
    # ------------------------------------------------------------------
    print("Step 3: Training ensemble detector...")
    with monitor.track_step("Step 3 — Treinamento do ensemble"):
        ensemble = EnsembleDetector()
        ensemble.fit(tables, ae_epochs=ae_epochs)
        ensemble.save_all(prefix=pipeline_id)
    print("  Ensemble trained and saved.")

    # Register model versions
    model_dir = Path("models/registry")
    for model_name in ["isolation_forest", "autoencoder"]:
        artifact_path = model_dir / f"{model_name}_{pipeline_id}.pkl"
        if artifact_path.exists():
            registry.register(
                model_name=model_name,
                artifact_path=str(artifact_path),
                created_by=run_by,
                metrics={"pipeline_id": pipeline_id},
            )

    audit.log("MODEL_TRAINED", user=run_by, details={"pipeline_id": pipeline_id})

    # ------------------------------------------------------------------
    # Step 4: Inference
    # ------------------------------------------------------------------
    print("Step 4: Running inference...")
    with monitor.track_step("Step 4 — Inferencia ensemble"):
        results   = ensemble.predict(tables)
        alerts_df = results[results["is_alert"] == True].copy()
    print(f"  {len(alerts_df)} alerts generated ({len(results)} records total).")

    # ------------------------------------------------------------------
    # Step 5: SHAP
    # ------------------------------------------------------------------
    print("Step 5: Computing SHAP values...")
    bsak = tables["BSAK"]
    bkpf = tables["BKPF"]
    lfa1 = tables["LFA1"]

    with monitor.track_step("Step 5 — SHAP (explicabilidade)"):
        shap_explainer = SHAPExplainer(ensemble.if_detector)
        shap_explainer.fit(bsak, bkpf, lfa1)
        alert_bsak_indices = alerts_df.index.tolist()[:narrative_limit]
        alert_records      = bsak.loc[bsak.index.isin(alert_bsak_indices)]
        shap_explanations  = shap_explainer.explain(alert_records, bkpf, lfa1, top_n=5)
    print(f"  SHAP computed for {len(shap_explanations)} alerts.")

    # ------------------------------------------------------------------
    # Step 6: Claude narratives
    # ------------------------------------------------------------------
    if generate_narratives and len(shap_explanations) > 0:
        print(f"Step 6: Generating {len(shap_explanations)} narratives via Claude API...")
        alert_dicts = []
        for i, (_, row) in enumerate(alerts_df.head(narrative_limit).iterrows()):
            alert_dicts.append({
                "record_idx":     int(row.get("record_idx", i)),
                "fraud_type":     str(row.get("FRAUD_TYPE", "UNKNOWN")),
                "ensemble_score": float(row.get("ensemble_score", 0)),
                "risk_tier":      str(row.get("risk_tier", "MEDIUM")),
                "if_score":       float(row.get("if_score", 0)),
                "ae_score":       float(row.get("ae_score", 0)),
                "graph_score":    float(row.get("graph_score", 0)),
                "vendor_id":      str(row.get("LIFNR", "")),
                "amount":         float(row.get("DMBTR", 0)),
                "date":           str(row.get("AUGDT", "")),
                "company_code":   str(row.get("BUKRS", "")),
                "doc_number":     str(row.get("BELNR", "")),
            })
        try:
            with monitor.track_step("Step 6 — Narrativas Claude API"):
                # Patch generate_batch_narratives to capture token usage
                narrated = _generate_with_cost_tracking(
                    alert_dicts, shap_explanations, monitor
                )
            for item in narrated:
                mask = alerts_df["LIFNR"] == item.get("vendor_id", "")
                alerts_df.loc[mask, "narrative"] = item.get("narrative", "")
        except Exception as e:
            print(f"  Warning: narrative generation failed — {e}")
    else:
        print("Step 6: Skipping narrative generation.")

    # ------------------------------------------------------------------
    # Step 7: Drift baseline
    # ------------------------------------------------------------------
    print("Step 7: Saving drift baseline...")
    with monitor.track_step("Step 7 — Baseline de data drift"):
        from models.isolation_forest import _build_features
        features_df   = _build_features(bsak, bkpf, lfa1)
        drift_detector = DataDriftDetector()
        drift_detector.save_baseline(features_df)
    print("  Baseline saved.")

    # ------------------------------------------------------------------
    # Step 8: Persist alerts
    # ------------------------------------------------------------------
    with monitor.track_step("Step 8 — Persistir alertas em Parquet"):
        processed_dir = Path("data/processed")
        processed_dir.mkdir(exist_ok=True)
        alerts_df["alert_id"] = [str(uuid.uuid4()) for _ in range(len(alerts_df))]
        alerts_df["is_alert"] = True
        alerts_df.to_parquet(processed_dir / "alerts.parquet", index=False)

    comparison = ensemble.compare_detectors(results)
    print("\nDetector comparison:")
    print(comparison.to_string(index=False))

    audit.log("PIPELINE_COMPLETE", user=run_by, details={
        "pipeline_id":  pipeline_id,
        "total_records": len(results),
        "total_alerts":  len(alerts_df),
    })

    print(f"\nPipeline {pipeline_id} complete — {len(alerts_df)} alerts ready.\n")

    # ------------------------------------------------------------------
    # Step 9: Cost report
    # ------------------------------------------------------------------
    monitor.finalize(print_summary=True)

    # ------------------------------------------------------------------
    # Step 10: Checksums SHA-256 dos artefatos críticos
    # ------------------------------------------------------------------
    print("Step 10: Computing SHA-256 checksums for critical artifacts...")
    checksums = collect_critical_files()
    save_checksums(pipeline_id=pipeline_id, checksums=checksums)
    ok, issues = verify_checksums(pipeline_id=pipeline_id)
    if ok:
        print(f"  Checksums OK — {len(checksums)} arquivo(s) registrado(s).")
    else:
        print(f"  ⚠ {len(issues)} problema(s) de integridade detectado(s):")
        for iss in issues:
            print(f"    [{iss['status']}] {iss['file']}")
    audit.log("CHECKSUMS_SAVED", user=run_by, details={
        "pipeline_id": pipeline_id,
        "file_count":  len(checksums),
        "integrity_ok": ok,
    })

    # ------------------------------------------------------------------
    # Step 11: CHANGELOG + audit log enrichment
    # ------------------------------------------------------------------
    print("Step 11: Updating CHANGELOG.md and enriching audit log...")
    try:
        from scripts.update_changelog import run as update_changelog_run
        update_changelog_run(pipeline_id=pipeline_id, run_type="pipeline_run")
    except Exception as exc:
        print(f"  Warning: changelog update failed — {exc}")

    # ------------------------------------------------------------------
    # Step 12: Audit dashboard
    # ------------------------------------------------------------------
    print("Step 12: Generating audit dashboard...")
    try:
        _run_script("scripts/generate_audit_dashboard.py")
    except Exception as exc:
        print(f"  Warning: audit dashboard failed — {exc}")

    # ------------------------------------------------------------------
    # Step 13: Executive report
    # ------------------------------------------------------------------
    print("Step 13: Generating executive report...")
    try:
        _run_script("scripts/generate_executive_report.py")
    except Exception as exc:
        print(f"  Warning: executive report failed — {exc}")

    # ------------------------------------------------------------------
    # Step 14: Documentation versioning
    # ------------------------------------------------------------------
    print("Step 14: Versioning documentation...")
    try:
        from scripts.version_docs import run as version_docs_run
        version_docs_run(pipeline_id=pipeline_id)
    except Exception as exc:
        print(f"  Warning: doc versioning failed — {exc}")

    return alerts_df


def _run_script(rel_path: str) -> None:
    """Executes a script file in the current Python interpreter via runpy."""
    import runpy
    script_path = Path(rel_path)
    if script_path.exists():
        runpy.run_path(str(script_path), run_name="__main__")


def _generate_with_cost_tracking(
    alert_dicts: list,
    shap_explanations: list,
    monitor: CostMonitor,
    model: str = "claude-sonnet-4-5",
    max_alerts: int = 50,
) -> list:
    """
    Calls the Claude API narrative by narrative, recording token usage
    in the CostMonitor after each response.
    """
    import anthropic as _anthropic
    from explainer.claude_narrator import SYSTEM_PROMPT, format_shap_for_prompt

    api_key = __import__("os").environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY nao definida.")

    client  = _anthropic.Anthropic(api_key=api_key)
    results = []

    for alert, explanation in zip(alert_dicts[:max_alerts], shap_explanations[:max_alerts]):
        shap_text    = format_shap_for_prompt(explanation)
        user_message = (
            f"Analise o seguinte alerta de risco financeiro e redija a narrativa de auditoria:\n\n"
            f"**Informacoes do Alerta:**\n"
            f"- Tipo de fraude detectada: {alert.get('fraud_type', 'Anomalia generica')}\n"
            f"- Score de risco ensemble: {alert.get('ensemble_score', 0):.4f}\n"
            f"- Nivel de risco: {alert.get('risk_tier', 'N/A')}\n"
            f"- Score Isolation Forest: {alert.get('if_score', 0):.4f}\n"
            f"- Score AutoEncoder: {alert.get('ae_score', 0):.4f}\n"
            f"- Score de grafo (conluio/SoD): {alert.get('graph_score', 0):.4f}\n"
            f"- Fornecedor (LIFNR): {alert.get('vendor_id', 'N/A')}\n"
            f"- Valor do pagamento (DMBTR): R$ {alert.get('amount', 0):,.2f}\n"
            f"- Data de compensacao (AUGDT): {alert.get('date', 'N/A')}\n"
            f"- Empresa (BUKRS): {alert.get('company_code', 'N/A')}\n\n"
            f"**Explicabilidade SHAP:**\n{shap_text}\n\n"
            f"Redija a narrativa completa de auditoria seguindo as diretrizes do sistema."
        )

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            narrative = response.content[0].text
            # Record token usage in the cost monitor
            monitor.record_token_usage(
                alert_id=str(alert.get("vendor_id", f"alert_{len(results)}")),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=model,
            )
        except Exception as e:
            narrative = f"[Erro ao gerar narrativa: {e}]"

        results.append({**alert, "narrative": narrative})

    return results


if __name__ == "__main__":
    run_pipeline(regenerate_data=True, ae_epochs=30, generate_narratives=False)
