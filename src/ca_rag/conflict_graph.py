import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np

try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False

try:
    from neo4j import GraphDatabase
    _HAS_NEO4J = True
except ImportError:
    _HAS_NEO4J = False

from src.ca_rag.claim_extractor import Claim
from src.ca_rag.evidence_clusterer import EvidenceCluster
from src.ca_rag.nli_detector import NLIMatrix, NLILabel, NLIResult

logger = logging.getLogger("rag_system.ca_rag.conflict_graph")

@dataclass
class GraphMetrics:
    node_count: int
    edge_count: int
    contradiction_edge_count: int
    entailment_edge_count: int
    contradiction_density: float
    hub_claims: List[Claim]
    largest_contradiction_component: int
    cluster_separation_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "contradiction_edge_count": self.contradiction_edge_count,
            "entailment_edge_count": self.entailment_edge_count,
            "contradiction_density": self.contradiction_density,
            "hub_claims": [c.to_dict() for c in self.hub_claims],
            "largest_contradiction_component": self.largest_contradiction_component,
            "cluster_separation_score": self.cluster_separation_score
        }

@dataclass
class ConflictGraph:
    graph: Any  # nx.DiGraph or Dict fallback
    claims: List[Claim]
    clusters: List[EvidenceCluster]
    metrics: GraphMetrics
    neo4j_persisted: bool
    built_at: datetime


class ConflictGraphBuilder:
    """Constructs, queries, and persists topological NLI relationship graphs from extracted claims and clusters."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        ca_config = config.get("ca_rag", {})
        self.neo4j_uri = ca_config.get("neo4j_uri", "bolt://localhost:7687")
        self.neo4j_user = ca_config.get("neo4j_user", "neo4j")
        self.neo4j_password = ca_config.get("neo4j_password", "password")

    def _cosine_similarity(self, u: List[float], v: List[float]) -> float:
        if not u or not v:
            return 0.0
        arr_u, arr_v = np.array(u), np.array(v)
        norm_u = np.linalg.norm(arr_u)
        norm_v = np.linalg.norm(arr_v)
        if norm_u == 0 or norm_v == 0:
            return 0.0
        return float(np.dot(arr_u, arr_v) / (norm_u * norm_v))

    def build(self, claims: List[Claim], nli_matrix: NLIMatrix, clusters: List[EvidenceCluster]) -> ConflictGraph:
        """Assembles a directed relationship graph and compiles analytical network metrics."""
        
        # Mapping to resolve claim clusters
        claim_cluster_map = {}
        for cluster in clusters:
            for claim in cluster.claims:
                claim_cluster_map[claim.claim_id] = cluster.cluster_id

        if _HAS_NETWORKX:
            g = nx.DiGraph()
            
            # Add nodes
            for claim in claims:
                g.add_node(
                    claim.claim_id,
                    claim_id=claim.claim_id,
                    normalized_text=claim.normalized_text,
                    claim_type=claim.claim_type.value,
                    chunk_id=claim.chunk_id,
                    doc_id=claim.doc_id,
                    source_title=claim.source_title,
                    confidence=claim.confidence,
                    cluster_id=claim_cluster_map.get(claim.claim_id, "")
                )
                
            # Add NLI edges
            for res in nli_matrix.results:
                c1 = next((c for c in claims if c.claim_id == res.claim_a_id), None)
                c2 = next((c for c in claims if c.claim_id == res.claim_b_id), None)
                if not c1 or not c2:
                    continue
                
                # Entailment -> SUPPORTS
                if res.final_verdict == NLILabel.ENTAILMENT:
                    fwd_score = res.forward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    bwd_score = res.backward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    g.add_edge(c1.claim_id, c2.claim_id, type="SUPPORTS", weight=max(fwd_score, bwd_score), color="green")
                
                # Contradiction -> CONTRADICTS
                elif res.final_verdict == NLILabel.CONTRADICTION:
                    g.add_edge(c1.claim_id, c2.claim_id, type="CONTRADICTS", weight=res.contradiction_strength, color="red")
                    # Make it bidirectional in the graph if bidirectional NLI flagged
                    if res.is_bidirectional:
                        g.add_edge(c2.claim_id, c1.claim_id, type="CONTRADICTS", weight=res.contradiction_strength, color="red")
                        
            # Neutral / Related edges (cosine similarity > 0.6)
            n_claims = len(claims)
            for i in range(n_claims):
                for j in range(i + 1, n_claims):
                    c1, c2 = claims[i], claims[j]
                    if c1.chunk_id == c2.chunk_id:
                        continue
                    
                    # Ensure no existing edge was set by NLI
                    if not g.has_edge(c1.claim_id, c2.claim_id) and not g.has_edge(c2.claim_id, c1.claim_id):
                        sim = self._cosine_similarity(c1.embedding, c2.embedding)
                        if sim > 0.6:
                            g.add_edge(c1.claim_id, c2.claim_id, type="RELATED", weight=sim, color="gray")
                            g.add_edge(c2.claim_id, c1.claim_id, type="RELATED", weight=sim, color="gray")
        else:
            # Fallback dictionary-based graph structure
            g = {"nodes": {}, "edges": []}
            for c in claims:
                g["nodes"][c.claim_id] = {
                    "claim_id": c.claim_id,
                    "normalized_text": c.normalized_text,
                    "claim_type": c.claim_type.value,
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "source_title": c.source_title,
                    "confidence": c.confidence,
                    "cluster_id": claim_cluster_map.get(c.claim_id, "")
                }
            for res in nli_matrix.results:
                if res.final_verdict == NLILabel.CONTRADICTION:
                    g["edges"].append({"source": res.claim_a_id, "target": res.claim_b_id, "type": "CONTRADICTS", "weight": res.contradiction_strength, "color": "red"})
                    if res.is_bidirectional:
                        g["edges"].append({"source": res.claim_b_id, "target": res.claim_a_id, "type": "CONTRADICTS", "weight": res.contradiction_strength, "color": "red"})
                elif res.final_verdict == NLILabel.ENTAILMENT:
                    fwd_score = res.forward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    bwd_score = res.backward_scores.get(NLILabel.ENTAILMENT.value, 0.0)
                    g["edges"].append({"source": res.claim_a_id, "target": res.claim_b_id, "type": "SUPPORTS", "weight": max(fwd_score, bwd_score), "color": "green"})

        metrics = self.compute_graph_metrics(g, claims, clusters)
        
        return ConflictGraph(
            graph=g,
            claims=claims,
            clusters=clusters,
            metrics=metrics,
            neo4j_persisted=False,
            built_at=datetime.utcnow()
        )

    def find_contradiction_paths(self, conflict_graph: ConflictGraph, claim_a_id: str, claim_b_id: str) -> List[List[str]]:
        """Identifies logical inference paths linking two conflicting viewpoints."""
        if not _HAS_NETWORKX:
            return []
        
        g = conflict_graph.graph
        if not isinstance(g, nx.DiGraph):
            return []

        if claim_a_id not in g or claim_b_id not in g:
            return []
            
        try:
            # Find all simple paths (ignoring direction for relationship paths, or using directed paths)
            paths = list(nx.all_simple_paths(g, source=claim_a_id, target=claim_b_id, cutoff=4))
            return paths
        except Exception as e:
            logger.error(f"Failed to calculate paths: {str(e)}")
            return []

    def compute_graph_metrics(self, g: Any, claims: List[Claim], clusters: List[EvidenceCluster]) -> GraphMetrics:
        """Calculates topological properties (hubs, contradiction density, cluster separation)."""
        node_count = len(claims)
        edge_count = 0
        contradiction_edge_count = 0
        entailment_edge_count = 0
        
        # Calculate degrees for hub identification
        claim_contra_degrees = {c.claim_id: 0 for c in claims}
        largest_comp_size = 0

        if _HAS_NETWORKX and isinstance(g, nx.DiGraph):
            edge_count = g.number_of_edges()
            for u, v, d in g.edges(data=True):
                etype = d.get("type", "")
                if etype == "CONTRADICTS":
                    contradiction_edge_count += 1
                    claim_contra_degrees[u] += 1
                    claim_contra_degrees[v] += 1
                elif etype == "SUPPORTS":
                    entailment_edge_count += 1
            
            # Find largest connected component inside contradiction subgraph
            try:
                contra_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("type") == "CONTRADICTS"]
                sub = g.edge_subgraph(contra_edges).to_undirected()
                if sub.number_of_nodes() > 0:
                    largest_comp_size = len(max(nx.connected_components(sub), key=len))
            except Exception:
                largest_comp_size = 0
        else:
            # Fallback dictionary metrics
            edge_count = len(g["edges"])
            for edge in g["edges"]:
                etype = edge["type"]
                if etype == "CONTRADICTS":
                    contradiction_edge_count += 1
                    claim_contra_degrees[edge["source"]] += 1
                    claim_contra_degrees[edge["target"]] += 1
                elif etype == "SUPPORTS":
                    entailment_edge_count += 1

        # Retrieve top 3 hubs (highest contradiction counts)
        sorted_hubs = sorted(claim_contra_degrees.items(), key=lambda x: x[1], reverse=True)
        hub_claims = []
        for cid, degree in sorted_hubs[:3]:
            if degree > 0:
                c_obj = next((c for c in claims if c.claim_id == cid), None)
                if c_obj:
                    hub_claims.append(c_obj)

        total_possible_edges = (node_count * (node_count - 1)) if node_count > 1 else 1
        contra_density = contradiction_edge_count / total_possible_edges if total_possible_edges > 0 else 0.0

        # Cluster separation score (average cosine distance between centroids)
        n_clusters = len(clusters)
        sep_scores = []
        for i in range(n_clusters):
            for j in range(i + 1, n_clusters):
                sim = self._cosine_similarity(clusters[i].centroid_embedding, clusters[j].centroid_embedding)
                sep_scores.append(1.0 - sim)
        cluster_sep = float(np.mean(sep_scores)) if sep_scores else 0.0

        return GraphMetrics(
            node_count=node_count,
            edge_count=edge_count,
            contradiction_edge_count=contradiction_edge_count,
            entailment_edge_count=entailment_edge_count,
            contradiction_density=contra_density,
            hub_claims=hub_claims,
            largest_contradiction_component=largest_comp_size,
            cluster_separation_score=cluster_sep
        )

    def export_for_visualization(self, conflict_graph: ConflictGraph) -> Dict[str, Any]:
        """Serializes the graph topology into a format ready for force-directed D3 rendering."""
        g = conflict_graph.graph
        nodes_out = []
        edges_out = []

        if _HAS_NETWORKX and isinstance(g, nx.DiGraph):
            for node_id, data in g.nodes(data=True):
                nodes_out.append({
                    "id": node_id,
                    "claim_id": data.get("claim_id"),
                    "label": data.get("normalized_text")[:50] + "..." if len(data.get("normalized_text", "")) > 50 else data.get("normalized_text"),
                    "full_text": data.get("normalized_text"),
                    "type": data.get("claim_type"),
                    "doc_id": data.get("doc_id"),
                    "source_title": data.get("source_title"),
                    "confidence": data.get("confidence"),
                    "cluster_id": data.get("cluster_id")
                })
            for u, v, d in g.edges(data=True):
                edges_out.append({
                    "source": u,
                    "target": v,
                    "type": d.get("type"),
                    "weight": d.get("weight"),
                    "color": d.get("color")
                })
        else:
            # Fallback format
            for node_id, data in g["nodes"].items():
                nodes_out.append({
                    "id": node_id,
                    "claim_id": data["claim_id"],
                    "label": data["normalized_text"][:50] + "..." if len(data["normalized_text"]) > 50 else data["normalized_text"],
                    "full_text": data["normalized_text"],
                    "type": data["claim_type"],
                    "doc_id": data["doc_id"],
                    "source_title": data["source_title"],
                    "confidence": data["confidence"],
                    "cluster_id": data["cluster_id"]
                })
            for e in g["edges"]:
                edges_out.append({
                    "source": e["source"],
                    "target": e["target"],
                    "type": e["type"],
                    "weight": e["weight"],
                    "color": e["color"]
                })

        return {
            "nodes": nodes_out,
            "edges": edges_out,
            "metrics": conflict_graph.metrics.to_dict()
        }

    def persist_to_neo4j(self, conflict_graph: ConflictGraph, query_hash: str) -> None:
        """Asynchronously writes node structures and NLI relations into Neo4j graph schemas."""
        if not _HAS_NEO4J:
            logger.info("Neo4j python package not installed. Skipping Neo4j persistence.")
            return

        try:
            driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            
            with driver.session() as session:
                # Merge claims and documents
                for claim in conflict_graph.claims:
                    session.run(
                        """
                        MERGE (d:Document {doc_id: $doc_id})
                        ON CREATE SET d.title = $doc_title, d.ingested_at = timestamp()
                        
                        MERGE (c:Claim {claim_id: $claim_id})
                        ON CREATE SET c.normalized_text = $normalized_text, 
                                      c.claim_text = $claim_text,
                                      c.claim_type = $claim_type,
                                      c.confidence = $confidence,
                                      c.created_at = timestamp()
                        
                        MERGE (c)-[:EXTRACTED_FROM]->(d)
                        """,
                        doc_id=claim.doc_id,
                        doc_title=claim.source_title,
                        claim_id=claim.claim_id,
                        normalized_text=claim.normalized_text,
                        claim_text=claim.claim_text,
                        claim_type=claim.claim_type.value,
                        confidence=claim.confidence
                    )
                
                # Merge clusters
                for cluster in conflict_graph.clusters:
                    session.run(
                        """
                        MERGE (cl:Cluster {cluster_id: $cluster_id})
                        ON CREATE SET cl.label = $label,
                                      cl.stance = $stance,
                                      cl.query_hash = $query_hash,
                                      cl.created_at = timestamp()
                        """,
                        cluster_id=cluster.cluster_id,
                        label=cluster.label,
                        stance=cluster.stance.value,
                        query_hash=query_hash
                    )
                    
                    # Associate claims with clusters
                    for claim in cluster.claims:
                        session.run(
                            """
                            MATCH (c:Claim {claim_id: $claim_id})
                            MATCH (cl:Cluster {cluster_id: $cluster_id})
                            MERGE (c)-[:BELONGS_TO]->(cl)
                            """,
                            claim_id=claim.claim_id,
                            cluster_id=cluster.cluster_id
                        )

                # Persist NLI relationships
                g = conflict_graph.graph
                if _HAS_NETWORKX and isinstance(g, nx.DiGraph):
                    for u, v, d in g.edges(data=True):
                        etype = d.get("type")
                        weight = d.get("weight", 0.0)
                        
                        if etype == "CONTRADICTS":
                            session.run(
                                """
                                MATCH (c1:Claim {claim_id: $u})
                                MATCH (c2:Claim {claim_id: $v})
                                MERGE (c1)-[r:CONTRADICTS {query_hash: $query_hash}]->(c2)
                                SET r.strength = $weight
                                """,
                                u=u, v=v, query_hash=query_hash, weight=weight
                            )
                        elif etype == "SUPPORTS":
                            session.run(
                                """
                                MATCH (c1:Claim {claim_id: $u})
                                MATCH (c2:Claim {claim_id: $v})
                                MERGE (c1)-[r:SUPPORTS {query_hash: $query_hash}]->(c2)
                                SET r.score = $weight
                                """,
                                u=u, v=v, query_hash=query_hash, weight=weight
                            )
                            
            driver.close()
            logger.info("Successfully persisted Conflict Graph structures to Neo4j database.")
            conflict_graph.neo4j_persisted = True
            
        except Exception as e:
            logger.warning(f"Failed to persist graph data to Neo4j: {str(e)}. Proceeding without graph persistence.")
