"""
End-to-end MLOps pipeline:
1. Generate / load data
2. Inject fraud
3. Train ensemble
4. Compute SHAP
5. Generate narratives
6. Register model version
7. Save drift baseline
8. Populate alert store
"""

import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from data.generators import FraudInjector, SAPDataGenerator
from explainer import SHAPExplainer, generate_batch_narratives
from governance.audit_log import AuditLogger
from governance.data_drift import DataDriftDetector
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
    audit = AuditLogger()
    registry = ModelVersionRegistry()
    pipeline_id = str(uuid.uuid4())[:8]

    audit.log("PIPELINE_START", user=run_by, details={"pipeline_id": pipeline_id})
    print(f"\n{'='*60}")
    print(f"Pipeline {pipeline_id} started at {datetime.utcnow().isoformat()}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # Step 1: Data
    # ------------------------------------------------------------------
    print("Step 1: Loading/generating SAP data...")
    raw_dir = Path("data/raw")

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
    injector = FraudInjector(tables, fraud_rate=0.02)
    tables = injector.inject_all()
    fraud_log = injector.fraud_log
    print(f"  Injected {len(fraud_log)} fraud records across {fraud_log['table'].nunique()} tables.")

    # ------------------------------------------------------------------
    # Step 3: Train ensemble
    # ------------------------------------------------------------------
    print("Step 3: Training ensemble detector...")
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
    results = ensemble.predict(tables)
    alerts_df = results[results["is_alert"] == True].copy()
    print(f"  {len(alerts_df)} alerts generated ({len(results)} records total).")

    # ------------------------------------------------------------------
    # Step 5: SHAP
    # ------------------------------------------------------------------
    print("Step 5: Computing SHAP values...")
    shap_explainer = SHAPExplainer(ensemble.if_detector)
    bsak = tables["BSAK"]
    bkpf = tables["BKPF"]
    lfa1 = tables["LFA1"]
    shap_explainer.fit(bsak, bkpf, lfa1)

    alert_bsak_indices = alerts_df.index.tolist()[:narrative_limit]
    alert_records = bsak.loc[bsak.index.isin(alert_bsak_indices)]
    shap_explanations = shap_explainer.explain(alert_records, bkpf, lfa1, top_n=5)
    print(f"  SHAP computed for {len(shap_explanations)} alerts.")

    # ------------------------------------------------------------------
    # Step 6: Claude narratives
    # ------------------------------------------------------------------
    if generate_narratives and len(shap_explanations) > 0:
        print(f"Step 6: Generating {len(shap_explanations)} narratives via Claude API...")
        alert_dicts = []
        for i, (_, row) in enumerate(alerts_df.head(narrative_limit).iterrows()):
            alert_dicts.append({
                "record_idx": int(row.get("record_idx", i)),
                "fraud_type": str(row.get("FRAUD_TYPE", "UNKNOWN")),
                "ensemble_score": float(row.get("ensemble_score", 0)),
                "risk_tier": str(row.get("risk_tier", "MEDIUM")),
                "if_score": float(row.get("if_score", 0)),
                "ae_score": float(row.get("ae_score", 0)),
                "graph_score": float(row.get("graph_score", 0)),
                "vendor_id": str(row.get("LIFNR", "")),
                "amount": float(row.get("DMBTR", 0)),
                "date": str(row.get("AUGDT", "")),
                "company_code": str(row.get("BUKRS", "")),
                "doc_number": str(row.get("BELNR", "")),
            })
        try:
            narrated = generate_batch_narratives(alert_dicts, shap_explanations)
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
    from models.isolation_forest import _build_features
    features_df = _build_features(bsak, bkpf, lfa1)
    drift_detector = DataDriftDetector()
    drift_detector.save_baseline(features_df)
    print("  Baseline saved.")

    # ------------------------------------------------------------------
    # Step 8: Persist alerts
    # ------------------------------------------------------------------
    processed_dir = Path("data/processed")
    processed_dir.mkdir(exist_ok=True)

    alerts_df["alert_id"] = [str(uuid.uuid4()) for _ in range(len(alerts_df))]
    alerts_df["is_alert"] = True
    alerts_df.to_parquet(processed_dir / "alerts.parquet", index=False)

    comparison = ensemble.compare_detectors(results)
    print("\nDetector comparison:")
    print(comparison.to_string(index=False))

    audit.log("PIPELINE_COMPLETE", user=run_by, details={
        "pipeline_id": pipeline_id,
        "total_records": len(results),
        "total_alerts": len(alerts_df),
    })

    print(f"\nPipeline {pipeline_id} complete — {len(alerts_df)} alerts ready.\n")
    return alerts_df


if __name__ == "__main__":
    run_pipeline(regenerate_data=True, ae_epochs=30, generate_narratives=False)
