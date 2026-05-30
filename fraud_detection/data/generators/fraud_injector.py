"""
Injects realistic fraud scenarios into the generated SAP tables.
Target fraud rate: 1–3% of transactions (configurable).
Each injected record is tagged with FRAUD_LABEL and FRAUD_TYPE for supervised eval.
"""

import random
import string
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd


def _rand_cnpj() -> str:
    d = [random.randint(0, 9) for _ in range(14)]
    return f"{d[0]:02d}.{d[2]:03d}.{d[5]:03d}/{d[8]:04d}-{d[12]:02d}"


def _slight_name_variation(name: str) -> str:
    variants = [
        name.replace("Ltda", "LTDA"),
        name.replace("Ltda", "Ltda."),
        name + " ME",
        name.replace(" ", "  "),
        name + " EPP",
    ]
    return random.choice(variants)


class FraudInjector:
    """
    Receives a dict of SAP DataFrames and injects fraud scenarios.
    All modified tables are returned with FRAUD_LABEL and FRAUD_TYPE columns.
    """

    def __init__(self, tables: Dict[str, pd.DataFrame], fraud_rate: float = 0.02, seed: int = 99):
        self.tables = {k: v.copy() for k, v in tables.items()}
        self.fraud_rate = fraud_rate
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)
        self._fraud_log: List[dict] = []

        for tbl in ["BKPF", "BSEG", "BSAK", "EKKO", "LFA1", "LFB1"]:
            if tbl in self.tables:
                if "FRAUD_LABEL" not in self.tables[tbl].columns:
                    self.tables[tbl]["FRAUD_LABEL"] = 0
                if "FRAUD_TYPE" not in self.tables[tbl].columns:
                    self.tables[tbl]["FRAUD_TYPE"] = ""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def inject_all(self) -> Dict[str, pd.DataFrame]:
        self._ghost_vendor()
        self._duplicate_vendor()
        self._bank_data_changed()
        self._vendor_same_bank_as_employee()
        self._vendor_created_and_paid_fast()
        self._duplicate_po()
        self._po_without_contract()
        self._approval_threshold_split()
        self._duplicate_payment()
        self._maverick_spend()
        self._below_threshold_invoice()
        self._cancelled_invoice_not_reversed()
        self._three_way_mismatch()
        self._round_payment()
        self._early_payment()
        self._payment_to_wrong_account()
        self._payment_burst()
        self._after_hours_payment()
        self._suspicious_recurrence()
        self._sod_same_user_vendor_and_payment()
        self._sod_same_user_po_and_receipt()
        return self.tables

    @property
    def fraud_log(self) -> pd.DataFrame:
        return pd.DataFrame(self._fraud_log)

    # ------------------------------------------------------------------
    # Vendor registration frauds
    # ------------------------------------------------------------------

    def _ghost_vendor(self):
        """Vendor with no real activity — created but immediately receives payments."""
        lfa1 = self.tables["LFA1"]
        n = max(1, int(len(lfa1) * self.fraud_rate))
        sample = lfa1.sample(n=n, random_state=self.seed)
        for idx in sample.index:
            self.tables["LFA1"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["LFA1"].at[idx, "FRAUD_TYPE"] = "GHOST_VENDOR"
            self.tables["LFA1"].at[idx, "NAME1"] = f"GHOST {idx} Comercio"
            self.tables["LFA1"].at[idx, "STCD1"] = _rand_cnpj()
            self._log("LFA1", idx, "GHOST_VENDOR")

    def _duplicate_vendor(self):
        """Same CNPJ with slightly different name — duplicate master record."""
        lfa1 = self.tables["LFA1"]
        n = max(1, int(len(lfa1) * self.fraud_rate))
        originals = lfa1.sample(n=n, random_state=self.seed + 1).copy()
        new_rows = []
        for _, row in originals.iterrows():
            dup = row.copy()
            dup["LIFNR"] = f"VDUP{row['LIFNR']}"
            dup["NAME1"] = _slight_name_variation(str(row["NAME1"]))
            dup["ERDAT"] = row["ERDAT"] + timedelta(days=random.randint(30, 180))
            dup["FRAUD_LABEL"] = 1
            dup["FRAUD_TYPE"] = "DUPLICATE_VENDOR"
            new_rows.append(dup)
            self._log("LFA1", dup["LIFNR"], "DUPLICATE_VENDOR")
        self.tables["LFA1"] = pd.concat(
            [self.tables["LFA1"], pd.DataFrame(new_rows)], ignore_index=True
        )

    def _bank_data_changed(self):
        """Bank account modified within 7 days of a payment."""
        lfb1 = self.tables["LFB1"]
        n = max(1, int(len(lfb1) * self.fraud_rate))
        sample = lfb1.sample(n=n, random_state=self.seed + 2)
        for idx in sample.index:
            pay_date = pd.Timestamp(self.tables["BSAK"]["AUGDT"].dropna().sample(1).values[0])
            self.tables["LFB1"].at[idx, "BKDAT"] = pay_date - timedelta(days=random.randint(1, 7))
            self.tables["LFB1"].at[idx, "BANKN"] = "99999999"
            self.tables["LFB1"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["LFB1"].at[idx, "FRAUD_TYPE"] = "BANK_CHANGE_BEFORE_PAYMENT"
            self._log("LFB1", idx, "BANK_CHANGE_BEFORE_PAYMENT")

    def _vendor_same_bank_as_employee(self):
        """Vendor shares bank routing + account with internal user (simulated)."""
        lfb1 = self.tables["LFB1"]
        employee_bank = ("237", "12345678")  # fake employee account
        n = max(1, int(len(lfb1) * self.fraud_rate))
        sample = lfb1.sample(n=n, random_state=self.seed + 3)
        for idx in sample.index:
            self.tables["LFB1"].at[idx, "BANKL"] = employee_bank[0]
            self.tables["LFB1"].at[idx, "BANKN"] = employee_bank[1]
            self.tables["LFB1"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["LFB1"].at[idx, "FRAUD_TYPE"] = "VENDOR_EMPLOYEE_SHARED_BANK"
            self._log("LFB1", idx, "VENDOR_EMPLOYEE_SHARED_BANK")

    def _vendor_created_and_paid_fast(self):
        """Vendor created and first payment within 3 days."""
        lfa1 = self.tables["LFA1"]
        bsak = self.tables["BSAK"]
        n = max(1, int(len(lfa1) * self.fraud_rate))
        sample = lfa1.sample(n=n, random_state=self.seed + 4)
        for _, row in sample.iterrows():
            mask = bsak["LIFNR"] == row["LIFNR"]
            if mask.any():
                idx = bsak[mask].index[0]
                self.tables["BSAK"].at[idx, "BUDAT"] = row["ERDAT"] + timedelta(days=random.randint(1, 3))
                self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
                self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "FAST_VENDOR_PAYMENT"
                self._log("BSAK", idx, "FAST_VENDOR_PAYMENT")

    # ------------------------------------------------------------------
    # Purchase Order frauds
    # ------------------------------------------------------------------

    def _duplicate_po(self):
        """Two POs for same vendor/amount/date — exact duplicate."""
        ekko = self.tables["EKKO"]
        n = max(1, int(len(ekko) * self.fraud_rate))
        sample = ekko.sample(n=n, random_state=self.seed + 5).copy()
        dups = []
        for _, row in sample.iterrows():
            dup = row.copy()
            dup["EBELN"] = f"PODUP{row['EBELN']}"
            dup["FRAUD_LABEL"] = 1
            dup["FRAUD_TYPE"] = "DUPLICATE_PO"
            dups.append(dup)
            self._log("EKKO", dup["EBELN"], "DUPLICATE_PO")
        self.tables["EKKO"] = pd.concat(
            [self.tables["EKKO"], pd.DataFrame(dups)], ignore_index=True
        )

    def _po_without_contract(self):
        """PO with no valid info record (INFNR blank) above a threshold."""
        ekko = self.tables["EKKO"]
        ekpo = self.tables["EKPO"]
        n = max(1, int(len(ekko) * self.fraud_rate))
        high_value = ekko[ekko["TOTAL_VALUE"] > 100_000].sample(
            n=min(n, len(ekko[ekko["TOTAL_VALUE"] > 100_000])), random_state=self.seed + 6
        )
        for _, row in high_value.iterrows():
            mask = ekpo["EBELN"] == row["EBELN"]
            self.tables["EKPO"].loc[mask, "INFNR"] = ""
            ekko_mask = self.tables["EKKO"]["EBELN"] == row["EBELN"]
            self.tables["EKKO"].loc[ekko_mask, "FRAUD_LABEL"] = 1
            self.tables["EKKO"].loc[ekko_mask, "FRAUD_TYPE"] = "PO_WITHOUT_CONTRACT"
            self._log("EKKO", row["EBELN"], "PO_WITHOUT_CONTRACT")

    def _approval_threshold_split(self):
        """Single purchase split into multiple POs just below approval limit."""
        ekko = self.tables["EKKO"]
        threshold = 50_000
        n = max(1, int(len(ekko) * self.fraud_rate))
        vendors = ekko["LIFNR"].value_counts().head(20).index.tolist()
        new_rows = []
        for vendor in random.sample(vendors, k=min(n, len(vendors))):
            for j in range(3):
                base = ekko[ekko["LIFNR"] == vendor].iloc[0].copy()
                base["EBELN"] = f"SPLIT{vendor}{j}"
                base["TOTAL_VALUE"] = threshold - random.uniform(100, 2000)
                base["FRGSX"] = "S1"
                base["FRAUD_LABEL"] = 1
                base["FRAUD_TYPE"] = "THRESHOLD_SPLITTING"
                new_rows.append(base)
                self._log("EKKO", base["EBELN"], "THRESHOLD_SPLITTING")
        self.tables["EKKO"] = pd.concat(
            [self.tables["EKKO"], pd.DataFrame(new_rows)], ignore_index=True
        )

    # ------------------------------------------------------------------
    # Invoice / payment frauds
    # ------------------------------------------------------------------

    def _duplicate_payment(self):
        """Two BSAK records with same LIFNR + DMBTR + BUDAT."""
        bsak = self.tables["BSAK"]
        n = max(1, int(len(bsak) * self.fraud_rate))
        sample = bsak.sample(n=n, random_state=self.seed + 7).copy()
        dups = []
        for _, row in sample.iterrows():
            dup = row.copy()
            dup["BELNR"] = f"DUP{row['BELNR']}"
            dup["FRAUD_LABEL"] = 1
            dup["FRAUD_TYPE"] = "DUPLICATE_PAYMENT"
            dups.append(dup)
            self._log("BSAK", dup["BELNR"], "DUPLICATE_PAYMENT")
        self.tables["BSAK"] = pd.concat(
            [self.tables["BSAK"], pd.DataFrame(dups)], ignore_index=True
        )

    def _maverick_spend(self):
        """BKPF entries with no EBELN (invoice without PO)."""
        bkpf = self.tables["BKPF"]
        n = max(1, int(len(bkpf) * self.fraud_rate))
        sample = bkpf.sample(n=n, random_state=self.seed + 8)
        for idx in sample.index:
            self.tables["BKPF"].at[idx, "AWKEY"] = ""
            self.tables["BKPF"].at[idx, "SOURCE_EBELN"] = ""
            self.tables["BKPF"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BKPF"].at[idx, "FRAUD_TYPE"] = "MAVERICK_SPEND"
            self._log("BKPF", idx, "MAVERICK_SPEND")

    def _below_threshold_invoice(self):
        """Invoice amount just below approval threshold — Benford-like."""
        bsak = self.tables["BSAK"]
        thresholds = [10_000, 50_000, 100_000, 500_000]
        n = max(1, int(len(bsak) * self.fraud_rate))
        sample = bsak.sample(n=n, random_state=self.seed + 9)
        for idx in sample.index:
            threshold = random.choice(thresholds)
            self.tables["BSAK"].at[idx, "DMBTR"] = threshold - random.uniform(1, 500)
            self.tables["BSAK"].at[idx, "WRBTR"] = self.tables["BSAK"].at[idx, "DMBTR"]
            self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "BELOW_THRESHOLD"
            self._log("BSAK", idx, "BELOW_THRESHOLD")

    def _cancelled_invoice_not_reversed(self):
        """Document reversed (STBLG set) but payment not cancelled."""
        bkpf = self.tables["BKPF"]
        n = max(1, int(len(bkpf) * self.fraud_rate))
        sample = bkpf.sample(n=n, random_state=self.seed + 10)
        for idx in sample.index:
            self.tables["BKPF"].at[idx, "STBLG"] = _rand_str(10)
            self.tables["BKPF"].at[idx, "STJAH"] = self.tables["BKPF"].at[idx, "GJAHR"]
            self.tables["BKPF"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BKPF"].at[idx, "FRAUD_TYPE"] = "CANCELLED_NOT_REVERSED"
            self._log("BKPF", idx, "CANCELLED_NOT_REVERSED")

    def _three_way_mismatch(self):
        """Invoice value diverges >10% from PO value — 3-way match failure."""
        bseg = self.tables["BSEG"]
        n = max(1, int(len(bseg) * self.fraud_rate))
        sample = bseg.sample(n=n, random_state=self.seed + 11)
        for idx in sample.index:
            original = self.tables["BSEG"].at[idx, "DMBTR"]
            self.tables["BSEG"].at[idx, "DMBTR"] = original * random.uniform(1.15, 1.5)
            self.tables["BSEG"].at[idx, "WRBTR"] = self.tables["BSEG"].at[idx, "DMBTR"]
            self.tables["BSEG"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSEG"].at[idx, "FRAUD_TYPE"] = "THREE_WAY_MISMATCH"
            self._log("BSEG", idx, "THREE_WAY_MISMATCH")

    # ------------------------------------------------------------------
    # Payment behaviour frauds
    # ------------------------------------------------------------------

    def _round_payment(self):
        """Suspiciously round amounts (e.g. exactly 10000, 50000)."""
        bsak = self.tables["BSAK"]
        n = max(1, int(len(bsak) * self.fraud_rate))
        sample = bsak.sample(n=n, random_state=self.seed + 12)
        round_amounts = [5000, 10000, 25000, 50000, 100000, 250000, 500000]
        for idx in sample.index:
            self.tables["BSAK"].at[idx, "DMBTR"] = float(random.choice(round_amounts))
            self.tables["BSAK"].at[idx, "WRBTR"] = self.tables["BSAK"].at[idx, "DMBTR"]
            self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "ROUND_PAYMENT"
            self._log("BSAK", idx, "ROUND_PAYMENT")

    def _early_payment(self):
        """Payment date before PO creation date."""
        bsak = self.tables["BSAK"]
        ekko = self.tables["EKKO"]
        bkpf = self.tables["BKPF"]
        n = max(1, int(len(bsak) * self.fraud_rate))
        sample = bsak.sample(n=n, random_state=self.seed + 13)
        for idx in sample.index:
            min_date = bkpf["BUDAT"].min()
            self.tables["BSAK"].at[idx, "AUGDT"] = min_date - timedelta(days=random.randint(1, 30))
            self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "EARLY_PAYMENT"
            self._log("BSAK", idx, "EARLY_PAYMENT")

    def _payment_to_wrong_account(self):
        """Payment bank account differs from vendor master."""
        lfb1 = self.tables["LFB1"]
        bsak = self.tables["BSAK"]
        n = max(1, int(len(bsak) * self.fraud_rate))
        sample = bsak.sample(n=n, random_state=self.seed + 14)
        for idx in sample.index:
            self.tables["BSAK"].at[idx, "AUGBL"] = "WRONGACC" + _rand_str(6)
            self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "WRONG_BANK_ACCOUNT"
            self._log("BSAK", idx, "WRONG_BANK_ACCOUNT")

    def _payment_burst(self):
        """Many payments to same vendor within 48h."""
        bsak = self.tables["BSAK"]
        vendors = bsak["LIFNR"].value_counts().head(10).index.tolist()
        burst_vendor = random.choice(vendors)
        mask = bsak["LIFNR"] == burst_vendor
        idxs = bsak[mask].head(10).index
        burst_date = bsak.loc[idxs[0], "AUGDT"]
        for i, idx in enumerate(idxs):
            self.tables["BSAK"].at[idx, "AUGDT"] = burst_date + timedelta(hours=i * 3)
            self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "PAYMENT_BURST"
            self._log("BSAK", idx, "PAYMENT_BURST")

    def _after_hours_payment(self):
        """Payment processed outside business hours (before 8h or after 18h)."""
        bkpf = self.tables["BKPF"]
        n = max(1, int(len(bkpf) * self.fraud_rate))
        sample = bkpf.sample(n=n, random_state=self.seed + 15)
        after_hours = ["22:14:05", "23:55:00", "01:30:00", "03:45:22", "06:00:01"]
        for idx in sample.index:
            self.tables["BKPF"].at[idx, "CPUTM"] = random.choice(after_hours)
            self.tables["BKPF"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BKPF"].at[idx, "FRAUD_TYPE"] = "AFTER_HOURS_PAYMENT"
            self._log("BKPF", idx, "AFTER_HOURS_PAYMENT")

    def _suspicious_recurrence(self):
        """Same vendor, same amount, every month — suspicious pattern."""
        bsak = self.tables["BSAK"]
        vendor = bsak["LIFNR"].value_counts().index[0]
        mask = bsak["LIFNR"] == vendor
        idxs = bsak[mask].head(12).index
        fixed_amount = round(random.uniform(50_000, 200_000), 2)
        base_date = datetime(2023, 1, 15)
        for i, idx in enumerate(idxs):
            self.tables["BSAK"].at[idx, "DMBTR"] = fixed_amount
            self.tables["BSAK"].at[idx, "WRBTR"] = fixed_amount
            self.tables["BSAK"].at[idx, "AUGDT"] = base_date + timedelta(days=30 * i)
            self.tables["BSAK"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BSAK"].at[idx, "FRAUD_TYPE"] = "SUSPICIOUS_RECURRENCE"
            self._log("BSAK", idx, "SUSPICIOUS_RECURRENCE")

    # ------------------------------------------------------------------
    # SoD / collusion frauds
    # ------------------------------------------------------------------

    def _sod_same_user_vendor_and_payment(self):
        """ERNAM in LFA1 matches USNAM in BKPF — same user created vendor and approved payment."""
        lfa1 = self.tables["LFA1"]
        bkpf = self.tables["BKPF"]
        n = max(1, int(len(bkpf) * self.fraud_rate))
        user = lfa1["ERNAM"].value_counts().index[0]
        sample = bkpf.sample(n=n, random_state=self.seed + 16)
        for idx in sample.index:
            self.tables["BKPF"].at[idx, "USNAM"] = user
            self.tables["BKPF"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["BKPF"].at[idx, "FRAUD_TYPE"] = "SOD_VENDOR_AND_PAYMENT"
            self._log("BKPF", idx, "SOD_VENDOR_AND_PAYMENT")

    def _sod_same_user_po_and_receipt(self):
        """Same user created PO and confirmed goods receipt."""
        ekko = self.tables["EKKO"]
        bkpf = self.tables["BKPF"]
        n = max(1, int(len(ekko) * self.fraud_rate))
        sample = ekko.sample(n=n, random_state=self.seed + 17)
        for idx in sample.index:
            creator = self.tables["EKKO"].at[idx, "ERNAM"]
            bkpf_idx = bkpf.sample(1, random_state=idx).index[0]
            self.tables["BKPF"].at[bkpf_idx, "USNAM"] = creator
            self.tables["EKKO"].at[idx, "FRAUD_LABEL"] = 1
            self.tables["EKKO"].at[idx, "FRAUD_TYPE"] = "SOD_PO_AND_RECEIPT"
            self._log("EKKO", idx, "SOD_PO_AND_RECEIPT")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, table: str, record_id, fraud_type: str):
        self._fraud_log.append({
            "table": table,
            "record_id": str(record_id),
            "fraud_type": fraud_type,
            "injected_at": datetime.utcnow().isoformat(),
        })


def _rand_str(n: int) -> str:
    return "".join(random.choices(string.digits, k=n))
