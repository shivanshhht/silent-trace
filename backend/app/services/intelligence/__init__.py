"""Stage C intelligence layer.

Read-only analytics over the investigation Stage B persists. Nothing in this
package writes to the database, and nothing in it constructs a graph of its own:
:mod:`graph_view` loads the persisted projection for exactly one case, and every
analytic works from that view.

Nothing here scores criminality. Centrality, signal strength and network
priority describe analytical relevance within one case; the explanations that
travel with them are the point, and the numbers are only an ordering.
"""

__all__ = [
    "anomaly_detection",
    "bridge_analysis",
    "community_detection",
    "context",
    "engine",
    "graph_view",
    "indicators",
    "lead_scoring",
    "network_analysis",
    "path_analysis",
    "temporal_analysis",
]
