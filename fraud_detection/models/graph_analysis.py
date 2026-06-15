"""
Graph-based collusion and SoD analysis using NetworkX.

Nodes: users, vendors
Edges:
  - user --[created]--> vendor
  - user --[approved_payment]--> vendor
  - user --[created_po]--> vendor
  - user --[approved_po]--> vendor

Collusion score = shared edges between buyer and vendor across different relationship types.
SoD violations = same node appears in two mutually exclusive roles.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import pandas as pd


@dataclass
class GraphAlert:
    alert_type: str
    severity: str                   # HIGH | MEDIUM | LOW
    entities: List[str]
    description: str
    evidence: dict = field(default_factory=dict)


class GraphAnalyzer:
    """
    Builds a multi-edge directed graph from P2P tables and detects:
    - SoD violations (same user in conflicting roles)
    - Collusion clusters (buyer-vendor-approver triangle)
    - Community anomalies (isolated suspicious cliques)
    """

    def __init__(self):
        self.G = nx.MultiDiGraph()
        self.alerts: List[GraphAlert] = []

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build(
        self,
        lfa1: pd.DataFrame,
        ekko: pd.DataFrame,
        bkpf: pd.DataFrame,
        bsak: pd.DataFrame,
    ) -> "GraphAnalyzer":
        self.G.clear()
        self.alerts.clear()

        # Vendor creation edges
        for _, row in lfa1.iterrows():
            user = str(row["ERNAM"])
            vendor = str(row["LIFNR"])
            if user and vendor:
                self.G.add_edge(user, vendor, rel="created_vendor", table="LFA1")
                self.G.nodes[user]["type"] = "user"
                self.G.nodes[vendor]["type"] = "vendor"

        # PO creation and approval edges
        for _, row in ekko.iterrows():
            creator = str(row["ERNAM"])
            approver = str(row.get("FRGRL", ""))
            vendor = str(row["LIFNR"])
            po = str(row["EBELN"])
            if creator and vendor:
                self.G.add_edge(creator, vendor, rel="created_po", po=po, table="EKKO")
                self.G.nodes[creator]["type"] = "user"
            if approver and vendor:
                self.G.add_edge(approver, vendor, rel="approved_po", po=po, table="EKKO")
                self.G.nodes[approver]["type"] = "approver"

        # Payment approval edges (USNAM in BKPF)
        vendor_from_bsak = bsak.set_index("BELNR")["LIFNR"].to_dict()
        for _, row in bkpf.iterrows():
            user = str(row["USNAM"])
            belnr = str(row["BELNR"])
            vendor = vendor_from_bsak.get(belnr, "")
            if user and vendor:
                self.G.add_edge(
                    user, vendor,
                    rel="approved_payment",
                    doc=belnr,
                    table="BKPF",
                )

        return self

    # ------------------------------------------------------------------
    # Detection rules
    # ------------------------------------------------------------------

    def detect_all(self) -> List[GraphAlert]:
        self._detect_sod_vendor_and_payment()
        self._detect_sod_po_and_payment()
        self._detect_collusion_triangles()
        self._detect_isolated_vendors()
        self._detect_high_degree_users()
        return self.alerts

    def _detect_sod_vendor_and_payment(self):
        """User who created a vendor AND approved a payment to the same vendor."""
        for u, v, data in self.G.edges(data=True):
            if data.get("rel") == "created_vendor":
                vendor = v
                # Check if same user has approved_payment to same vendor
                if self.G.has_edge(u, vendor):
                    for _, _, d2 in self.G.edges(u, data=True):
                        if d2.get("rel") == "approved_payment":
                            self.alerts.append(GraphAlert(
                                alert_type="SOD_VENDOR_PAYMENT",
                                severity="HIGH",
                                entities=[u, vendor],
                                description=(
                                    f"Usuário {u} cadastrou o fornecedor {vendor} "
                                    f"e também aprovou pagamento para o mesmo fornecedor."
                                ),
                                evidence={"user": u, "vendor": vendor},
                            ))
                            break

    def _detect_sod_po_and_payment(self):
        """User who created a PO AND approved a payment for the same vendor."""
        created_po: Dict[str, Set[str]] = {}    # user -> vendors
        approved_pay: Dict[str, Set[str]] = {}

        for u, v, data in self.G.edges(data=True):
            if data.get("rel") == "created_po":
                created_po.setdefault(u, set()).add(v)
            if data.get("rel") == "approved_payment":
                approved_pay.setdefault(u, set()).add(v)

        for user in set(created_po) & set(approved_pay):
            shared = created_po[user] & approved_pay[user]
            for vendor in shared:
                self.alerts.append(GraphAlert(
                    alert_type="SOD_PO_PAYMENT",
                    severity="HIGH",
                    entities=[user, vendor],
                    description=(
                        f"Usuário {user} criou pedido de compra E aprovou pagamento "
                        f"para o mesmo fornecedor {vendor} — violação de segregação de funções."
                    ),
                    evidence={"user": user, "vendor": vendor},
                ))

    def _detect_collusion_triangles(self):
        """
        Detects buyer-vendor-approver triangles:
        buyer --created_po--> vendor
        approver --approved_po--> vendor
        buyer --approved_payment--> vendor (or vice versa)
        using simple undirected triangle enumeration.
        """
        undirected = self.G.to_undirected()
        for triangle in _enumerate_triangles(undirected):
            nodes = list(triangle)
            types = [self.G.nodes.get(n, {}).get("type", "") for n in nodes]
            if "vendor" in types and "user" in types:
                vendor_nodes = [n for n in nodes if self.G.nodes.get(n, {}).get("type") == "vendor"]
                user_nodes = [n for n in nodes if n not in vendor_nodes]
                if vendor_nodes and len(user_nodes) >= 2:
                    self.alerts.append(GraphAlert(
                        alert_type="COLLUSION_TRIANGLE",
                        severity="MEDIUM",
                        entities=nodes,
                        description=(
                            f"Triângulo de conluio detectado: {', '.join(user_nodes)} "
                            f"→ fornecedor {vendor_nodes[0]}. "
                            f"Múltiplos usuários com relacionamento cruzado no mesmo fornecedor."
                        ),
                        evidence={"triangle": nodes},
                    ))

    def _detect_isolated_vendors(self, min_interactions: int = 3):
        """Vendors where a single user handles ALL interactions — ghost vendor / SoD signal.

        Requires at least `min_interactions` user→vendor edges before flagging.
        Without this guard, low-activity vendors (created but rarely used) are
        trivially isolated and flood the graph_score with 1.0 for nearly all vendors,
        inflating the ensemble score of legitimate transactions.
        """
        for node in self.G.nodes:
            if self.G.nodes[node].get("type") == "vendor":
                user_edges = [
                    u for u, v, d in self.G.in_edges(node, data=True)
                    if self.G.nodes.get(u, {}).get("type") == "user"
                ]
                if len(user_edges) < min_interactions:
                    continue
                in_users = set(user_edges)
                if len(in_users) == 1:
                    user = list(in_users)[0]
                    self.alerts.append(GraphAlert(
                        alert_type="ISOLATED_VENDOR",
                        severity="LOW",
                        entities=[user, node],
                        description=(
                            f"Fornecedor {node} possui {len(user_edges)} interações "
                            f"registradas, todas originadas do mesmo usuário ({user}). "
                            f"Padrão consistente com fornecedor fantasma ou conluio."
                        ),
                        evidence={"vendor": node, "sole_user": user,
                                  "interaction_count": len(user_edges)},
                    ))

    def _detect_high_degree_users(self):
        """Users with abnormally high number of vendor relationships."""
        degree_series = pd.Series(
            {n: self.G.degree(n) for n in self.G.nodes
             if self.G.nodes[n].get("type") == "user"}
        )
        if degree_series.empty:
            return
        mean = degree_series.mean()
        std = degree_series.std()
        threshold = mean + 3 * std
        for user, deg in degree_series.items():
            if deg > threshold:
                self.alerts.append(GraphAlert(
                    alert_type="HIGH_DEGREE_USER",
                    severity="MEDIUM",
                    entities=[user],
                    description=(
                        f"Usuário {user} possui {deg} relacionamentos com fornecedores "
                        f"(média: {mean:.1f}, +3σ: {threshold:.1f}). "
                        f"Possível ponto central de conluio."
                    ),
                    evidence={"user": user, "degree": deg, "threshold": threshold},
                ))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_subgraph(self, nodes: List[str]) -> nx.MultiDiGraph:
        return self.G.subgraph(nodes)

    def to_alert_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "alert_type": a.alert_type,
                "severity": a.severity,
                "entities": ",".join(a.entities),
                "description": a.description,
            }
            for a in self.alerts
        ])

    def export_edges(self) -> pd.DataFrame:
        rows = []
        for u, v, data in self.G.edges(data=True):
            rows.append({"source": u, "target": v, **data})
        return pd.DataFrame(rows)


def _enumerate_triangles(G: nx.Graph):
    """Yield frozensets of 3 nodes forming a triangle."""
    seen: Set[frozenset] = set()
    for u in G.nodes:
        neighbors_u = set(G.neighbors(u))
        for v in neighbors_u:
            neighbors_v = set(G.neighbors(v))
            common = neighbors_u & neighbors_v
            for w in common:
                tri = frozenset([u, v, w])
                if tri not in seen:
                    seen.add(tri)
                    yield tri
