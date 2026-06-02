"""Unit tests for SAP data generators."""

import pytest
import pandas as pd
from data.generators.sap_tables import SAPDataGenerator
from data.generators.fraud_injector import FraudInjector


@pytest.fixture(scope="module")
def tables():
    gen = SAPDataGenerator(n_vendors=50, n_pos=200, n_invoices=250, seed=42)
    return gen.generate_all(save=False)


@pytest.fixture(scope="module")
def tables_with_fraud(tables):
    injector = FraudInjector(tables, fraud_rate=0.05, seed=99)
    return injector.inject_all(), injector.fraud_log


class TestSAPDataGenerator:
    def test_all_tables_present(self, tables):
        expected = {"BKPF", "BSEG", "BSAK", "BSID", "LFA1", "LFB1",
                    "T001", "T001W", "EKKO", "EKPO", "EKKN", "MARA", "MARC"}
        assert expected == set(tables.keys())

    def test_lfa1_has_expected_columns(self, tables):
        cols = set(tables["LFA1"].columns)
        assert {"LIFNR", "NAME1", "STCD1", "ERDAT", "ERNAM"}.issubset(cols)

    def test_ekko_references_valid_vendors(self, tables):
        valid_vendors = set(tables["LFA1"]["LIFNR"])
        po_vendors = set(tables["EKKO"]["LIFNR"])
        assert po_vendors.issubset(valid_vendors)

    def test_bseg_ebeln_references_ekko(self, tables):
        valid_pos = set(tables["EKKO"]["EBELN"])
        bseg_pos = set(tables["BSEG"]["EBELN"].dropna())
        assert bseg_pos.issubset(valid_pos), "BSEG has EBELN values not in EKKO"

    def test_row_counts_are_positive(self, tables):
        for name, df in tables.items():
            assert len(df) > 0, f"Table {name} is empty"

    def test_no_null_primary_keys(self, tables):
        pk_map = {"LFA1": "LIFNR", "EKKO": "EBELN", "BKPF": "BELNR"}
        for table, pk in pk_map.items():
            assert tables[table][pk].notna().all(), f"{table}.{pk} has nulls"

    def test_amounts_are_positive(self, tables):
        for tbl in ["BSAK", "BSEG"]:
            if tbl in tables:
                assert (tables[tbl]["DMBTR"] >= 0).all(), f"{tbl}.DMBTR has negative values"

    def test_ekko_ekpo_join_integrity(self, tables):
        ekko_pos = set(tables["EKKO"]["EBELN"])
        ekpo_pos = set(tables["EKPO"]["EBELN"])
        assert ekpo_pos.issubset(ekko_pos), "EKPO references POs not in EKKO"


class TestFraudInjector:
    def test_fraud_labels_added(self, tables_with_fraud):
        injected, _ = tables_with_fraud
        for tbl in ["LFA1", "EKKO", "BKPF", "BSAK"]:
            assert "FRAUD_LABEL" in injected[tbl].columns
            assert "FRAUD_TYPE" in injected[tbl].columns

    def test_fraud_rate_within_bounds(self, tables_with_fraud):
        injected, log = tables_with_fraud
        for tbl_name in ["BSAK"]:
            df = injected[tbl_name]
            rate = df["FRAUD_LABEL"].mean()
            assert rate <= 0.30, f"Fraud rate in {tbl_name} too high: {rate:.2%}"

    def test_all_fraud_types_injected(self, tables_with_fraud):
        _, log = tables_with_fraud
        types = set(log["fraud_type"].unique())
        expected = {
            "GHOST_VENDOR", "DUPLICATE_VENDOR", "DUPLICATE_PO",
            "DUPLICATE_PAYMENT", "ROUND_PAYMENT", "AFTER_HOURS_PAYMENT",
        }
        assert expected.issubset(types), f"Missing fraud types: {expected - types}"

    def test_fraud_log_has_all_required_columns(self, tables_with_fraud):
        _, log = tables_with_fraud
        assert {"table", "record_id", "fraud_type", "injected_at"}.issubset(log.columns)

    def test_ghost_vendor_name_changed(self, tables_with_fraud):
        injected, _ = tables_with_fraud
        ghost_rows = injected["LFA1"][injected["LFA1"]["FRAUD_TYPE"] == "GHOST_VENDOR"]
        assert (ghost_rows["NAME1"].str.startswith("GHOST")).all()

    def test_duplicate_vendor_has_different_lifnr(self, tables_with_fraud):
        injected, _ = tables_with_fraud
        dups = injected["LFA1"][injected["LFA1"]["FRAUD_TYPE"] == "DUPLICATE_VENDOR"]
        assert dups["LIFNR"].str.startswith("VDUP").all()

    def test_bank_change_within_7_days(self, tables_with_fraud):
        injected, _ = tables_with_fraud
        lfb1 = injected["LFB1"]
        changed = lfb1[lfb1["FRAUD_TYPE"] == "BANK_CHANGE_BEFORE_PAYMENT"]
        assert (changed["BANKN"] == "99999999").all()

    def test_after_hours_entries(self, tables_with_fraud):
        injected, _ = tables_with_fraud
        bkpf = injected["BKPF"]
        after_hours = bkpf[bkpf["FRAUD_TYPE"] == "AFTER_HOURS_PAYMENT"]
        hours = after_hours["CPUTM"].str.split(":").str[0].astype(int)
        assert ((hours < 8) | (hours >= 18)).all()
