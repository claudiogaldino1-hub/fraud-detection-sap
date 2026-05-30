"""Unit tests for detection models."""

import numpy as np
import pandas as pd
import pytest

from data.generators.sap_tables import SAPDataGenerator
from data.generators.fraud_injector import FraudInjector
from models.isolation_forest import IsolationForestDetector
from models.autoencoder import AutoEncoderDetector
from models.graph_analysis import GraphAnalyzer
from models.ensemble import EnsembleDetector


@pytest.fixture(scope="module")
def small_tables():
    gen = SAPDataGenerator(n_vendors=40, n_pos=100, n_invoices=120, seed=7)
    tables = gen.generate_all(save=False)
    injector = FraudInjector(tables, fraud_rate=0.05, seed=77)
    return injector.inject_all()


class TestIsolationForest:
    def test_fit_and_predict(self, small_tables):
        det = IsolationForestDetector(n_estimators=50)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        labels, scores = det.predict(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        assert len(labels) == len(small_tables["BSAK"])
        assert len(scores) == len(small_tables["BSAK"])
        assert set(labels).issubset({-1, 1})

    def test_proba_in_range(self, small_tables):
        det = IsolationForestDetector(n_estimators=50)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        proba = det.predict_proba(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        assert (proba >= 0).all() and (proba <= 1).all()

    def test_save_and_load(self, tmp_path, monkeypatch, small_tables):
        import models.isolation_forest as m
        monkeypatch.setattr(m, "MODEL_DIR", tmp_path)

        det = IsolationForestDetector(n_estimators=20)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        path = det.save("test_if")

        loaded = IsolationForestDetector.load("test_if")
        labels_orig, _ = det.predict(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        labels_load, _ = loaded.predict(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        np.testing.assert_array_equal(labels_orig, labels_load)

    def test_anomaly_rate_reasonable(self, small_tables):
        det = IsolationForestDetector(contamination=0.02, n_estimators=50)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        labels, _ = det.predict(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        anomaly_rate = (labels == -1).mean()
        assert 0.005 <= anomaly_rate <= 0.15, f"Anomaly rate out of range: {anomaly_rate:.3f}"


class TestAutoEncoder:
    def test_fit_and_predict(self, small_tables):
        det = AutoEncoderDetector(epochs=5, batch_size=32)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        labels, errors = det.predict(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        assert len(labels) == len(small_tables["BSAK"])
        assert (errors >= 0).all()

    def test_latent_representation(self, small_tables):
        det = AutoEncoderDetector(epochs=3, latent_dim=3)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        latent = det.get_latent(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        assert latent.shape == (len(small_tables["BSAK"]), 3)

    def test_reconstruction_errors_positive(self, small_tables):
        det = AutoEncoderDetector(epochs=3)
        det.fit(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        _, errors = det.predict(small_tables["BSAK"], small_tables["BKPF"], small_tables["LFA1"])
        assert (errors >= 0).all()


class TestGraphAnalyzer:
    def test_build_creates_nodes_and_edges(self, small_tables):
        analyzer = GraphAnalyzer()
        analyzer.build(
            lfa1=small_tables["LFA1"],
            ekko=small_tables["EKKO"],
            bkpf=small_tables["BKPF"],
            bsak=small_tables["BSAK"],
        )
        assert analyzer.G.number_of_nodes() > 0
        assert analyzer.G.number_of_edges() > 0

    def test_detect_returns_alerts_list(self, small_tables):
        analyzer = GraphAnalyzer()
        analyzer.build(
            lfa1=small_tables["LFA1"],
            ekko=small_tables["EKKO"],
            bkpf=small_tables["BKPF"],
            bsak=small_tables["BSAK"],
        )
        alerts = analyzer.detect_all()
        assert isinstance(alerts, list)

    def test_alert_dataframe_schema(self, small_tables):
        analyzer = GraphAnalyzer()
        analyzer.build(
            lfa1=small_tables["LFA1"],
            ekko=small_tables["EKKO"],
            bkpf=small_tables["BKPF"],
            bsak=small_tables["BSAK"],
        )
        analyzer.detect_all()
        df = analyzer.to_alert_dataframe()
        assert set(df.columns) == {"alert_type", "severity", "entities", "description"}

    def test_edge_export(self, small_tables):
        analyzer = GraphAnalyzer()
        analyzer.build(
            lfa1=small_tables["LFA1"],
            ekko=small_tables["EKKO"],
            bkpf=small_tables["BKPF"],
            bsak=small_tables["BSAK"],
        )
        edges_df = analyzer.export_edges()
        assert {"source", "target", "rel"}.issubset(edges_df.columns)
        assert len(edges_df) > 0


class TestEnsembleDetector:
    def test_fit_and_predict_returns_dataframe(self, small_tables):
        ensemble = EnsembleDetector()
        ensemble.fit(small_tables, ae_epochs=3)
        results = ensemble.predict(small_tables)
        assert isinstance(results, pd.DataFrame)
        assert "ensemble_score" in results.columns
        assert "risk_tier" in results.columns
        assert "is_alert" in results.columns

    def test_scores_in_valid_range(self, small_tables):
        ensemble = EnsembleDetector()
        ensemble.fit(small_tables, ae_epochs=3)
        results = ensemble.predict(small_tables)
        assert (results["ensemble_score"] >= 0).all()
        assert (results["ensemble_score"] <= 1).all()

    def test_compare_detectors_returns_summary(self, small_tables):
        ensemble = EnsembleDetector()
        ensemble.fit(small_tables, ae_epochs=3)
        results = ensemble.predict(small_tables)
        summary = ensemble.compare_detectors(results)
        assert "total_records" in summary.columns
        assert "unanimous" in summary.columns
        assert int(summary["total_records"].iloc[0]) == len(small_tables["BSAK"])

    def test_risk_tiers_are_valid(self, small_tables):
        ensemble = EnsembleDetector()
        ensemble.fit(small_tables, ae_epochs=3)
        results = ensemble.predict(small_tables)
        valid_tiers = {"HIGH", "MEDIUM", "LOW"}
        assert set(results["risk_tier"].unique()).issubset(valid_tiers)
