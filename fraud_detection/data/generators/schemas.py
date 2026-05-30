"""
SAP P2P table schemas — field definitions matching real SAP column conventions.
Swap generate_* functions in sap_tables.py to point at a real SAP connection.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class FieldDef:
    name: str
    dtype: str          # pandas dtype string
    description: str
    sensitivity: str    # public | internal | confidential | restricted


@dataclass
class TableSchema:
    name: str
    description: str
    layer: str          # source system layer: FI | MM | LO | master
    fields: List[FieldDef]


# ---------------------------------------------------------------------------
# Financial Accounting (FI)
# ---------------------------------------------------------------------------

BKPF = TableSchema(
    name="BKPF",
    description="Accounting Document Header",
    layer="FI",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("BELNR",   "str",      "Accounting Document Number",       "internal"),
        FieldDef("GJAHR",   "int32",    "Fiscal Year",                      "internal"),
        FieldDef("BLART",   "str",      "Document Type",                    "internal"),
        FieldDef("BLDAT",   "datetime", "Document Date in Document",        "internal"),
        FieldDef("BUDAT",   "datetime", "Posting Date in the Document",     "internal"),
        FieldDef("USNAM",   "str",      "User Name",                        "confidential"),
        FieldDef("TCODE",   "str",      "Transaction Code",                 "internal"),
        FieldDef("WAERS",   "str",      "Currency Key",                     "internal"),
        FieldDef("KURSF",   "float64",  "Exchange Rate",                    "internal"),
        FieldDef("CPUDT",   "datetime", "Day On Which Accounting Document Was Entered", "internal"),
        FieldDef("CPUTM",   "str",      "Time of Data Entry",               "confidential"),
        FieldDef("AWTYP",   "str",      "Reference Procedure",              "internal"),
        FieldDef("AWKEY",   "str",      "Object Key",                       "internal"),
        FieldDef("STBLG",   "str",      "Reverse Document Number",          "internal"),
        FieldDef("STJAH",   "int32",    "Reversal Fiscal Year",             "internal"),
        FieldDef("BSTAT",   "str",      "Document Status",                  "internal"),
    ],
)

BSEG = TableSchema(
    name="BSEG",
    description="Accounting Document Segment",
    layer="FI",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("BELNR",   "str",      "Accounting Document Number",       "internal"),
        FieldDef("GJAHR",   "int32",    "Fiscal Year",                      "internal"),
        FieldDef("BUZEI",   "int32",    "Number of Line Item Within Accounting Document", "internal"),
        FieldDef("KOART",   "str",      "Account Type",                     "internal"),
        FieldDef("LIFNR",   "str",      "Account Number of Vendor",         "confidential"),
        FieldDef("DMBTR",   "float64",  "Amount in Local Currency",         "confidential"),
        FieldDef("WRBTR",   "float64",  "Amount in Document Currency",      "confidential"),
        FieldDef("MWSKZ",   "str",      "Tax on Sales/Purchases Code",      "internal"),
        FieldDef("ZTERM",   "str",      "Terms of Payment Key",             "internal"),
        FieldDef("ZBD1T",   "float64",  "Cash Discount Days 1",             "internal"),
        FieldDef("AUGDT",   "datetime", "Clearing Date",                    "internal"),
        FieldDef("AUGBL",   "str",      "Document Number of Clearing Document", "internal"),
        FieldDef("EBELN",   "str",      "Purchasing Document Number",       "internal"),
        FieldDef("EBELP",   "int32",    "Item Number of Purchasing Document","internal"),
    ],
)

BSAK = TableSchema(
    name="BSAK",
    description="Accounting: Secondary Index for Vendors (Cleared Items)",
    layer="FI",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("LIFNR",   "str",      "Vendor Account Number",            "confidential"),
        FieldDef("GJAHR",   "int32",    "Fiscal Year",                      "internal"),
        FieldDef("BELNR",   "str",      "Accounting Document Number",       "internal"),
        FieldDef("BLDAT",   "datetime", "Document Date",                    "internal"),
        FieldDef("BUDAT",   "datetime", "Posting Date",                     "internal"),
        FieldDef("DMBTR",   "float64",  "Amount in Local Currency",         "confidential"),
        FieldDef("WRBTR",   "float64",  "Amount in Document Currency",      "confidential"),
        FieldDef("AUGDT",   "datetime", "Clearing Date",                    "internal"),
        FieldDef("AUGBL",   "str",      "Clearing Document",                "internal"),
        FieldDef("ZLSPR",   "str",      "Payment Block Key",                "internal"),
    ],
)

BSID = TableSchema(
    name="BSID",
    description="Accounting: Secondary Index for Customers (Open Items)",
    layer="FI",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("KUNNR",   "str",      "Customer Account Number",          "confidential"),
        FieldDef("GJAHR",   "int32",    "Fiscal Year",                      "internal"),
        FieldDef("BELNR",   "str",      "Accounting Document Number",       "internal"),
        FieldDef("BLDAT",   "datetime", "Document Date",                    "internal"),
        FieldDef("BUDAT",   "datetime", "Posting Date",                     "internal"),
        FieldDef("DMBTR",   "float64",  "Amount in Local Currency",         "confidential"),
        FieldDef("WRBTR",   "float64",  "Amount in Document Currency",      "confidential"),
    ],
)

# ---------------------------------------------------------------------------
# Vendor Master
# ---------------------------------------------------------------------------

LFA1 = TableSchema(
    name="LFA1",
    description="Vendor Master (General Section)",
    layer="master",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("LIFNR",   "str",      "Vendor Account Number",            "confidential"),
        FieldDef("NAME1",   "str",      "Name 1",                           "confidential"),
        FieldDef("NAME2",   "str",      "Name 2",                           "confidential"),
        FieldDef("ORT01",   "str",      "City",                             "confidential"),
        FieldDef("LAND1",   "str",      "Country Key",                      "internal"),
        FieldDef("STCD1",   "str",      "Tax Number 1 (CNPJ/CPF)",          "restricted"),
        FieldDef("STCD2",   "str",      "Tax Number 2",                     "restricted"),
        FieldDef("ERDAT",   "datetime", "Date on Which Record Was Created",  "internal"),
        FieldDef("ERNAM",   "str",      "Name of Person who Created Object", "confidential"),
        FieldDef("SMTP_ADDR","str",     "E-Mail Address",                   "restricted"),
        FieldDef("TELF1",   "str",      "First Telephone Number",           "restricted"),
        FieldDef("STRAS",   "str",      "Street and House Number",          "confidential"),
        FieldDef("LOEVM",   "str",      "Central Deletion Flag for Master Record", "internal"),
        FieldDef("SPERR",   "str",      "Central Posting Block",            "internal"),
    ],
)

LFB1 = TableSchema(
    name="LFB1",
    description="Vendor Master (Company Code Data)",
    layer="master",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("LIFNR",   "str",      "Vendor Account Number",            "confidential"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("ERDAT",   "datetime", "Date on Which Record Was Created",  "internal"),
        FieldDef("ERNAM",   "str",      "Created By",                       "confidential"),
        FieldDef("ZTERM",   "str",      "Terms of Payment Key",             "internal"),
        FieldDef("AKONT",   "str",      "Reconciliation Account in General Ledger", "internal"),
        FieldDef("FDGRV",   "str",      "Planning Group",                   "internal"),
        FieldDef("ZWELS",   "str",      "Payment Methods",                  "internal"),
        FieldDef("BANKS",   "str",      "Bank Country Key",                 "internal"),
        FieldDef("BANKL",   "str",      "Bank Key (Routing Number)",        "restricted"),
        FieldDef("BANKN",   "str",      "Bank Account Number",              "restricted"),
        FieldDef("BVTYP",   "str",      "Partner Bank Type",                "internal"),
        FieldDef("BKDAT",   "datetime", "Bank Data Changed Date",           "internal"),
        FieldDef("BKNAM",   "str",      "User who Changed Bank Data",       "confidential"),
    ],
)

# ---------------------------------------------------------------------------
# Organizational
# ---------------------------------------------------------------------------

T001 = TableSchema(
    name="T001",
    description="Company Codes",
    layer="master",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("BUTXT",   "str",      "Name of Company Code",             "public"),
        FieldDef("ORT01",   "str",      "City",                             "public"),
        FieldDef("LAND1",   "str",      "Country Key",                      "public"),
        FieldDef("WAERS",   "str",      "Currency Key",                     "public"),
    ],
)

T001W = TableSchema(
    name="T001W",
    description="Plants/Branches",
    layer="master",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("WERKS",   "str",      "Plant",                            "internal"),
        FieldDef("NAME1",   "str",      "Name 1",                           "public"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("ORT01",   "str",      "City",                             "public"),
    ],
)

# ---------------------------------------------------------------------------
# Purchasing (MM)
# ---------------------------------------------------------------------------

EKKO = TableSchema(
    name="EKKO",
    description="Purchasing Document Header",
    layer="MM",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("EBELN",   "str",      "Purchasing Document Number",       "internal"),
        FieldDef("BUKRS",   "str",      "Company Code",                     "internal"),
        FieldDef("BSTYP",   "str",      "Purchasing Document Category",     "internal"),
        FieldDef("BSART",   "str",      "Purchasing Document Type",         "internal"),
        FieldDef("LIFNR",   "str",      "Vendor Account Number",            "confidential"),
        FieldDef("ERNAM",   "str",      "Created By",                       "confidential"),
        FieldDef("ERDAT",   "datetime", "Creation Date",                    "internal"),
        FieldDef("AEDAT",   "datetime", "Last Change Date",                 "internal"),
        FieldDef("WAERS",   "str",      "Currency Key",                     "internal"),
        FieldDef("WKURS",   "float64",  "Exchange Rate",                    "internal"),
        FieldDef("KDATB",   "datetime", "Start of Validity Period",         "internal"),
        FieldDef("KDATE",   "datetime", "End of Validity Period",           "internal"),
        FieldDef("KNUMV",   "str",      "Number of Condition Document",     "internal"),
        FieldDef("ZTERM",   "str",      "Payment Terms",                    "internal"),
        FieldDef("VERKF",   "str",      "Vendor Salesperson",               "internal"),
        FieldDef("IHRAN",   "str",      "Quotation Deadline",               "internal"),
        FieldDef("FRGGR",   "str",      "Release Group",                    "internal"),
        FieldDef("FRGSX",   "str",      "Release Strategy",                 "internal"),
        FieldDef("FRGKE",   "str",      "Release Indicator",                "internal"),
        FieldDef("FRGZU",   "str",      "Release Status",                   "internal"),
        FieldDef("FRGRL",   "str",      "Indicator: Release Already Carried Out Once", "internal"),
    ],
)

EKPO = TableSchema(
    name="EKPO",
    description="Purchasing Document Item",
    layer="MM",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("EBELN",   "str",      "Purchasing Document Number",       "internal"),
        FieldDef("EBELP",   "int32",    "Item Number of Purchasing Document","internal"),
        FieldDef("MATNR",   "str",      "Material Number",                  "internal"),
        FieldDef("WERKS",   "str",      "Plant",                            "internal"),
        FieldDef("MENGE",   "float64",  "Purchase Order Quantity",          "internal"),
        FieldDef("MEINS",   "str",      "Purchase Order Unit of Measure",   "internal"),
        FieldDef("NETPR",   "float64",  "Net Price in Purchasing Document",  "confidential"),
        FieldDef("NETWR",   "float64",  "Net Order Value in PO Currency",   "confidential"),
        FieldDef("BRTWR",   "float64",  "Gross Order Value in PO Currency", "confidential"),
        FieldDef("MWSKZ",   "str",      "Tax on Sales/Purchases Code",      "internal"),
        FieldDef("LOEKZ",   "str",      "Deletion Indicator in Purchasing Document", "internal"),
        FieldDef("EINDT",   "datetime", "Item Delivery Date",               "internal"),
        FieldDef("INFNR",   "str",      "Number of Purchasing Info Record",  "internal"),
        FieldDef("KNTTP",   "str",      "Account Assignment Category",      "internal"),
    ],
)

EKKN = TableSchema(
    name="EKKN",
    description="Account Assignment in Purchasing Document",
    layer="MM",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("EBELN",   "str",      "Purchasing Document Number",       "internal"),
        FieldDef("EBELP",   "int32",    "Item Number",                      "internal"),
        FieldDef("ZEKKN",   "int32",    "Sequential Number of Account Assignment", "internal"),
        FieldDef("KOSTL",   "str",      "Cost Center",                      "internal"),
        FieldDef("SAKTO",   "str",      "G/L Account Number",               "internal"),
        FieldDef("PRCTR",   "str",      "Profit Center",                    "internal"),
        FieldDef("NETWR",   "float64",  "Net Value",                        "confidential"),
    ],
)

# ---------------------------------------------------------------------------
# Material Master
# ---------------------------------------------------------------------------

MARA = TableSchema(
    name="MARA",
    description="General Material Data",
    layer="MM",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("MATNR",   "str",      "Material Number",                  "internal"),
        FieldDef("MBRSH",   "str",      "Industry Sector",                  "internal"),
        FieldDef("MTART",   "str",      "Material Type",                    "internal"),
        FieldDef("MATKL",   "str",      "Material Group",                   "internal"),
        FieldDef("MEINS",   "str",      "Base Unit of Measure",             "internal"),
        FieldDef("MSTAE",   "str",      "Cross-Plant Material Status",      "internal"),
        FieldDef("ERDAT",   "datetime", "Date on Which Record Was Created",  "internal"),
        FieldDef("ERNAM",   "str",      "Name of Person Who Created Object", "confidential"),
    ],
)

MARC = TableSchema(
    name="MARC",
    description="Plant Data for Material",
    layer="MM",
    fields=[
        FieldDef("MANDT",   "str",      "Client",                           "internal"),
        FieldDef("MATNR",   "str",      "Material Number",                  "internal"),
        FieldDef("WERKS",   "str",      "Plant",                            "internal"),
        FieldDef("PSTAT",   "str",      "Maintenance Status",               "internal"),
        FieldDef("MMSTA",   "str",      "Plant-Specific Material Status",   "internal"),
        FieldDef("EKGRP",   "str",      "Purchasing Group",                 "internal"),
        FieldDef("DISMM",   "str",      "MRP Type",                         "internal"),
        FieldDef("MINBE",   "float64",  "Reorder Point",                    "internal"),
    ],
)

ALL_SCHEMAS = {
    s.name: s for s in [
        BKPF, BSEG, BSAK, BSID, LFA1, LFB1,
        T001, T001W, EKKO, EKPO, EKKN, MARA, MARC,
    ]
}
