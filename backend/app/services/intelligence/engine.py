"""The single entry point to the intelligence layer.

Analysis never reaches into the database on its own. It loads exactly one case
through :func:`build_case_graph_view`, which reads the projection Stage B wrote,
and every analytic below operates on that view. Because the view is built per
case and holds nothing else, no analytic can accidentally read across
investigations - case isolation is a property of construction here, not of
remembering to add a filter.

The lead pipeline reuses one view and one community partition across all its
detectors, so the communities a signal refers to are the same communities the
bridge report names, and the numbers in a lead always agree with the numbers in
the endpoint that produced them.
"""

from datetime import datetime

from app.services.intelligence import (
    anomaly_detection,
    bridge_analysis,
    community_detection,
    context,
    network_analysis,
    path_analysis,
    temporal_analysis,
)
from app.services.intelligence.graph_view import CaseGraphView, build_case_graph_view
from app.services.intelligence.indicators import activity_indicators
from app.services.intelligence.lead_scoring import investigative_leads


class IntelligenceEngine:
    """Read-only analytics over one persisted investigation at a time."""

    @staticmethod
    def view(session, case_id: str) -> CaseGraphView:
        return build_case_graph_view(session, case_id)

    def centrality(self, session, case_id: str, metric: str = "degree", limit: int | None = None):
        view = self.view(session, case_id)
        assignments = community_detection.detect_communities(view)
        return network_analysis.centrality(
            view, metric, communities=assignments, limit=limit
        )

    def communities(self, session, case_id: str):
        return community_detection.communities(self.view(session, case_id))

    def bridges(self, session, case_id: str):
        return bridge_analysis.bridges(self.view(session, case_id))

    def paths(
        self,
        session,
        case_id: str,
        source_entity_id: str,
        target_entity_id: str,
        max_depth: int = path_analysis.DEFAULT_MAX_DEPTH,
    ):
        return path_analysis.connection_paths(
            self.view(session, case_id), source_entity_id, target_entity_id, max_depth
        )

    def temporal(self, session, case_id: str, entity_id: str | None = None):
        return temporal_analysis.temporal(self.view(session, case_id), entity_id)

    def relationship_context(self, session, case_id: str):
        return context.classify_relationships(self.view(session, case_id))

    def anomalies(self, session, case_id: str, *, include_cross_case: bool = False):
        view = self.view(session, case_id)
        return anomaly_detection.detect_anomalies(
            view, session=session, include_cross_case=include_cross_case
        )

    def indicators(self, session, case_id: str):
        return activity_indicators(self.view(session, case_id))

    def leads(
        self,
        session,
        case_id: str,
        *,
        include_cross_case: bool = False,
        generated_at: datetime | None = None,
    ):
        """Run every detector over one shared view and aggregate the results."""
        view = self.view(session, case_id)
        assignments = community_detection.detect_communities(view)
        betweenness = network_analysis.normalized_betweenness(view)
        profiles = temporal_analysis.temporal_profiles(view)

        anomalies = anomaly_detection.detect_anomalies(
            view,
            assignments=assignments,
            profiles=profiles,
            betweenness=betweenness,
            session=session,
            include_cross_case=include_cross_case,
        )
        indicators = activity_indicators(view, assignments=assignments)
        bridges = bridge_analysis.bridges(view, assignments=assignments)

        return investigative_leads(
            view,
            anomalies.signals,
            indicators.indicators,
            bridges.bridges,
            generated_at=generated_at,
        )
