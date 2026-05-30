"""
Synthetic SAP P2P data generator.
Replace _load_from_sap() with a real RFC/HANA connection to go production.
"""

import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

COMPANY_CODES = ["1000", "2000", "3000"]
PLANTS = ["1001", "1002", "2001", "3001"]
CURRENCIES = ["BRL", "USD", "EUR"]
PAY_TERMS = ["Z001", "Z030", "Z060", "NET30", "NET60"]
DOC_TYPES = ["KR", "RE", "KZ", "ZP"]
MATERIAL_GROUPS = ["001", "002", "003", "004", "005"]
PURCHASE_TYPES = ["NB", "FO", "MK", "LP"]
USERS = [f"USR{i:04d}" for i in range(1, 51)]          # 50 internal users
APPROVERS = [f"APR{i:03d}" for i in range(1, 11)]       # 10 approvers


def _rand_cnpj() -> str:
    d = [random.randint(0, 9) for _ in range(14)]
    return f"{d[0]:02d}.{d[2]:03d}.{d[5]:03d}/{d[8]:04d}-{d[12]:02d}"


def _rand_doc(prefix: str = "", length: int = 10) -> str:
    suffix = "".join(random.choices(string.digits, k=length))
    return f"{prefix}{suffix}"


def _rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def _rand_amount(lo: float = 100, hi: float = 500_000) -> float:
    return round(random.uniform(lo, hi), 2)


def _rand_bank() -> tuple[str, str]:
    banks = ["001", "033", "237", "341", "104", "756", "077", "655"]
    bank = random.choice(banks)
    account = "".join(random.choices(string.digits, k=8))
    return bank, account


class SAPDataGenerator:
    """Generates a coherent set of SAP P2P tables."""

    def __init__(
        self,
        n_vendors: int = 300,
        n_materials: int = 200,
        n_pos: int = 2000,
        n_invoices: int = 2500,
        seed: int = 42,
        start_date: datetime = datetime(2023, 1, 1),
        end_date: datetime = datetime(2024, 12, 31),
    ):
        random.seed(seed)
        np.random.seed(seed)
        self.n_vendors = n_vendors
        self.n_materials = n_materials
        self.n_pos = n_pos
        self.n_invoices = n_invoices
        self.start = start_date
        self.end = end_date
        self._tables: Dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_all(self, save: bool = True) -> Dict[str, pd.DataFrame]:
        self._tables["T001"]  = self._gen_t001()
        self._tables["T001W"] = self._gen_t001w()
        self._tables["MARA"]  = self._gen_mara()
        self._tables["MARC"]  = self._gen_marc()
        self._tables["LFA1"]  = self._gen_lfa1()
        self._tables["LFB1"]  = self._gen_lfb1()
        self._tables["EKKO"]  = self._gen_ekko()
        self._tables["EKPO"]  = self._gen_ekpo()
        self._tables["EKKN"]  = self._gen_ekkn()
        self._tables["BKPF"]  = self._gen_bkpf()
        self._tables["BSEG"]  = self._gen_bseg()
        self._tables["BSAK"]  = self._gen_bsak()
        self._tables["BSID"]  = self._gen_bsid()

        if save:
            self._save_all()
        return self._tables

    def get_table(self, name: str) -> pd.DataFrame:
        if name not in self._tables:
            raise KeyError(f"Table {name} not generated yet — call generate_all() first.")
        return self._tables[name]

    # ------------------------------------------------------------------
    # Table generators
    # ------------------------------------------------------------------

    def _gen_t001(self) -> pd.DataFrame:
        rows = []
        for bukrs in COMPANY_CODES:
            rows.append({
                "MANDT": "100",
                "BUKRS": bukrs,
                "BUTXT": f"Empresa {bukrs}",
                "ORT01": random.choice(["São Paulo", "Rio de Janeiro", "Curitiba"]),
                "LAND1": "BR",
                "WAERS": "BRL",
            })
        return pd.DataFrame(rows)

    def _gen_t001w(self) -> pd.DataFrame:
        rows = []
        for werks in PLANTS:
            rows.append({
                "MANDT": "100",
                "WERKS": werks,
                "NAME1": f"Planta {werks}",
                "BUKRS": COMPANY_CODES[int(werks[0]) - 1],
                "ORT01": random.choice(["São Paulo", "Campinas", "Porto Alegre"]),
            })
        return pd.DataFrame(rows)

    def _gen_mara(self) -> pd.DataFrame:
        rows = []
        for i in range(self.n_materials):
            rows.append({
                "MANDT": "100",
                "MATNR": f"MAT{i:06d}",
                "MBRSH": "M",
                "MTART": random.choice(["ROH", "HALB", "FERT", "DIEN"]),
                "MATKL": random.choice(MATERIAL_GROUPS),
                "MEINS": random.choice(["UN", "KG", "LT", "PC"]),
                "MSTAE": "",
                "ERDAT": _rand_date(self.start - timedelta(days=365), self.start),
                "ERNAM": random.choice(USERS),
            })
        return pd.DataFrame(rows)

    def _gen_marc(self) -> pd.DataFrame:
        mara = self._tables["MARA"]
        rows = []
        for _, mat in mara.iterrows():
            for werks in random.sample(PLANTS, k=random.randint(1, 3)):
                rows.append({
                    "MANDT": "100",
                    "MATNR": mat["MATNR"],
                    "WERKS": werks,
                    "PSTAT": "V",
                    "MMSTA": "",
                    "EKGRP": f"E{random.randint(1,9):02d}",
                    "DISMM": random.choice(["PD", "VB", "ND"]),
                    "MINBE": round(random.uniform(0, 100), 2),
                })
        return pd.DataFrame(rows)

    def _gen_lfa1(self) -> pd.DataFrame:
        rows = []
        for i in range(self.n_vendors):
            bank, acct = _rand_bank()
            rows.append({
                "MANDT":    "100",
                "LIFNR":    f"V{i:06d}",
                "NAME1":    f"Fornecedor {i:04d} Ltda",
                "NAME2":    "",
                "ORT01":    random.choice(["São Paulo", "Belo Horizonte", "Brasília", "Recife"]),
                "LAND1":    "BR",
                "STCD1":    _rand_cnpj(),
                "STCD2":    "",
                "ERDAT":    _rand_date(self.start - timedelta(days=730), self.start),
                "ERNAM":    random.choice(USERS),
                "SMTP_ADDR":f"contato{i}@fornecedor{i}.com.br",
                "TELF1":    f"11{random.randint(90000000, 99999999)}",
                "STRAS":    f"Rua das Acácias, {random.randint(1, 999)}",
                "LOEVM":    "",
                "SPERR":    "",
                "BANKS":    "BR",
                "BANKL":    bank,
                "BANKN":    acct,
            })
        return pd.DataFrame(rows)

    def _gen_lfb1(self) -> pd.DataFrame:
        lfa1 = self._tables["LFA1"]
        rows = []
        for _, v in lfa1.iterrows():
            for bukrs in random.sample(COMPANY_CODES, k=random.randint(1, 2)):
                rows.append({
                    "MANDT": "100",
                    "LIFNR": v["LIFNR"],
                    "BUKRS": bukrs,
                    "ERDAT": v["ERDAT"],
                    "ERNAM": v["ERNAM"],
                    "ZTERM": random.choice(PAY_TERMS),
                    "AKONT": "160000",
                    "FDGRV": "A1",
                    "ZWELS": "T",
                    "BANKS": "BR",
                    "BANKL": v["BANKL"],
                    "BANKN": v["BANKN"],
                    "BVTYP": "01",
                    "BKDAT": v["ERDAT"],
                    "BKNAM": v["ERNAM"],
                })
        return pd.DataFrame(rows)

    def _gen_ekko(self) -> pd.DataFrame:
        lfa1 = self._tables["LFA1"]
        vendor_ids = lfa1["LIFNR"].tolist()
        rows = []
        for i in range(self.n_pos):
            creator = random.choice(USERS)
            approver = random.choice(APPROVERS)
            created = _rand_date(self.start, self.end - timedelta(days=30))
            total_value = _rand_amount(1_000, 2_000_000)
            rows.append({
                "MANDT":  "100",
                "EBELN":  f"PO{i:08d}",
                "BUKRS":  random.choice(COMPANY_CODES),
                "BSTYP":  "F",
                "BSART":  random.choice(PURCHASE_TYPES),
                "LIFNR":  random.choice(vendor_ids),
                "ERNAM":  creator,
                "ERDAT":  created,
                "AEDAT":  created + timedelta(days=random.randint(0, 10)),
                "WAERS":  "BRL",
                "WKURS":  1.0,
                "KDATB":  created,
                "KDATE":  created + timedelta(days=365),
                "KNUMV":  _rand_doc("COND"),
                "ZTERM":  random.choice(PAY_TERMS),
                "VERKF":  "",
                "IHRAN":  "",
                "FRGGR":  "01",
                "FRGSX":  "S1" if total_value < 50_000 else "S2" if total_value < 500_000 else "S3",
                "FRGKE":  "4",
                "FRGZU":  "X",
                "FRGRL":  approver,
                "TOTAL_VALUE": total_value,
            })
        return pd.DataFrame(rows)

    def _gen_ekpo(self) -> pd.DataFrame:
        ekko = self._tables["EKKO"]
        mara = self._tables["MARA"]
        mat_ids = mara["MATNR"].tolist()
        rows = []
        for _, po in ekko.iterrows():
            n_items = random.randint(1, 5)
            remaining = po["TOTAL_VALUE"]
            for j in range(1, n_items + 1):
                is_last = j == n_items
                val = remaining if is_last else round(remaining * random.uniform(0.1, 0.7), 2)
                remaining -= val
                qty = round(random.uniform(1, 100), 2)
                rows.append({
                    "MANDT": "100",
                    "EBELN": po["EBELN"],
                    "EBELP": j * 10,
                    "MATNR": random.choice(mat_ids),
                    "WERKS": random.choice(PLANTS),
                    "MENGE": qty,
                    "MEINS": "UN",
                    "NETPR": round(val / qty, 2) if qty else 0,
                    "NETWR": round(val, 2),
                    "BRTWR": round(val * 1.12, 2),
                    "MWSKZ": "V1",
                    "LOEKZ": "",
                    "EINDT": po["ERDAT"] + timedelta(days=random.randint(5, 60)),
                    "INFNR": _rand_doc("INFO"),
                    "KNTTP": random.choice(["", "K", "P"]),
                })
        return pd.DataFrame(rows)

    def _gen_ekkn(self) -> pd.DataFrame:
        ekpo = self._tables["EKPO"]
        cost_centers = [f"CC{i:04d}" for i in range(1, 21)]
        rows = []
        for _, item in ekpo.iterrows():
            rows.append({
                "MANDT": "100",
                "EBELN": item["EBELN"],
                "EBELP": item["EBELP"],
                "ZEKKN": 1,
                "KOSTL": random.choice(cost_centers),
                "SAKTO": f"{random.randint(600000, 699999)}",
                "PRCTR": f"PC{random.randint(1,10):03d}",
                "NETWR": item["NETWR"],
            })
        return pd.DataFrame(rows)

    def _gen_bkpf(self) -> pd.DataFrame:
        ekko = self._tables["EKKO"]
        rows = []
        for _, po in ekko.iterrows():
            post_date = po["ERDAT"] + timedelta(days=random.randint(1, 45))
            if post_date > self.end:
                continue
            entry_time = f"{random.randint(7,18):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
            rows.append({
                "MANDT":  "100",
                "BUKRS":  po["BUKRS"],
                "BELNR":  _rand_doc("FI"),
                "GJAHR":  post_date.year,
                "BLART":  random.choice(DOC_TYPES),
                "BLDAT":  post_date - timedelta(days=random.randint(0, 5)),
                "BUDAT":  post_date,
                "USNAM":  po["ERNAM"],
                "TCODE":  random.choice(["FB60", "MIRO", "FB70", "F110"]),
                "WAERS":  "BRL",
                "KURSF":  1.0,
                "CPUDT":  post_date,
                "CPUTM":  entry_time,
                "AWTYP":  "RMRP",
                "AWKEY":  po["EBELN"],
                "STBLG":  "",
                "STJAH":  0,
                "BSTAT":  "A",
                "SOURCE_EBELN": po["EBELN"],
            })
        return pd.DataFrame(rows)

    def _gen_bseg(self) -> pd.DataFrame:
        bkpf = self._tables["BKPF"]
        ekko = self._tables["EKKO"]
        po_map = ekko.set_index("EBELN")["TOTAL_VALUE"].to_dict()
        lfa1  = self._tables["LFA1"]
        po_vendor = ekko.set_index("EBELN")["LIFNR"].to_dict()
        rows = []
        for _, doc in bkpf.iterrows():
            ebeln = doc["SOURCE_EBELN"]
            amount = po_map.get(ebeln, _rand_amount())
            lifnr  = po_vendor.get(ebeln, lfa1["LIFNR"].iloc[0])
            rows.append({
                "MANDT":  "100",
                "BUKRS":  doc["BUKRS"],
                "BELNR":  doc["BELNR"],
                "GJAHR":  doc["GJAHR"],
                "BUZEI":  1,
                "KOART":  "K",
                "LIFNR":  lifnr,
                "DMBTR":  amount,
                "WRBTR":  amount,
                "MWSKZ":  "V1",
                "ZTERM":  random.choice(PAY_TERMS),
                "ZBD1T":  30.0,
                "AUGDT":  doc["BUDAT"] + timedelta(days=random.randint(15, 90)),
                "AUGBL":  _rand_doc("PAY"),
                "EBELN":  ebeln,
                "EBELP":  10,
            })
        return pd.DataFrame(rows)

    def _gen_bsak(self) -> pd.DataFrame:
        bseg = self._tables["BSEG"]
        bkpf = self._tables["BKPF"]
        doc_dates = bkpf.set_index("BELNR")[["BLDAT", "BUDAT"]].to_dict("index")
        rows = []
        for _, seg in bseg.iterrows():
            dates = doc_dates.get(seg["BELNR"], {})
            rows.append({
                "MANDT":  "100",
                "BUKRS":  seg["BUKRS"],
                "LIFNR":  seg["LIFNR"],
                "GJAHR":  seg["GJAHR"],
                "BELNR":  seg["BELNR"],
                "BLDAT":  dates.get("BLDAT", seg["AUGDT"]),
                "BUDAT":  dates.get("BUDAT", seg["AUGDT"]),
                "DMBTR":  seg["DMBTR"],
                "WRBTR":  seg["WRBTR"],
                "AUGDT":  seg["AUGDT"],
                "AUGBL":  seg["AUGBL"],
                "ZLSPR":  "",
            })
        return pd.DataFrame(rows)

    def _gen_bsid(self) -> pd.DataFrame:
        n = max(50, self.n_invoices // 20)
        rows = []
        for i in range(n):
            post_date = _rand_date(self.start, self.end)
            rows.append({
                "MANDT":  "100",
                "BUKRS":  random.choice(COMPANY_CODES),
                "KUNNR":  f"C{random.randint(1000,9999):04d}",
                "GJAHR":  post_date.year,
                "BELNR":  _rand_doc("AR"),
                "BLDAT":  post_date - timedelta(days=random.randint(0, 5)),
                "BUDAT":  post_date,
                "DMBTR":  _rand_amount(1_000, 200_000),
                "WRBTR":  _rand_amount(1_000, 200_000),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_all(self):
        for name, df in self._tables.items():
            path = RAW_DIR / f"{name}.parquet"
            df.to_parquet(path, index=False)
            print(f"  Saved {name}: {len(df):,} rows → {path}")

    @classmethod
    def load_all(cls) -> Dict[str, pd.DataFrame]:
        """Load previously saved tables from disk."""
        tables = {}
        for p in RAW_DIR.glob("*.parquet"):
            tables[p.stem] = pd.read_parquet(p)
        return tables

    # ------------------------------------------------------------------
    # Production hook — swap this for real SAP connection
    # ------------------------------------------------------------------

    @staticmethod
    def _load_from_sap(table_name: str, fields: list, where: str = "") -> pd.DataFrame:
        """
        PRODUCTION STUB — replace body with real RFC call, e.g.:
            from pyrfc import Connection
            conn = Connection(**SAP_CREDS)
            result = conn.call('RFC_READ_TABLE', QUERY_TABLE=table_name, ...)
            return pd.DataFrame(result['DATA'])
        """
        raise NotImplementedError("Connect to real SAP system here.")
