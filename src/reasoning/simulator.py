from typing import List, Dict
from src.core.knowledge_graph import KnowledgeGraph
from src.schemas.base_models import InferredOutcome, Relation
from src.api.market_data import MarketDataProvider
from src.reasoning.temporal_integrator import TemporalIntegrator

class ScenarioSimulator:
    """
    [Reasoning Engine v4.0]
    Advanced Simulator with Temporal & Data layers.
    """

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.market_data = MarketDataProvider()
        self.temporal = TemporalIntegrator()

    def simulate(self, trigger_nodes: List[str]) -> InferredOutcome:
        """
        [Reasoning Core]
        Simulates propagation of effects from trigger nodes.
        Feature: 'Competing Narratives' - Aggregates conflicting impacts.
        """
        all_paths = []
        path_scores = []
        
        # Structure: { node_id: { "total_score": 0.0, "sources": [], "conflicts": False } }
        impact_map = {} 
        raw_narratives = []
        
        # 1. BFS Traversal & Impact Calculation
        for start_node in trigger_nodes:
            # Check market data (Context)
            start_data = self.market_data.get_market_indicator(start_node)
            context_text = ""
            if start_data:
                trend_kor = self._translate_trend(start_data['trend'])
                context_text = (
                    f"📊 [현황] {start_data['indicator']}: {start_data['value']} "
                    f"({trend_kor}, 1W: {start_data['change_1w']:+.2f}%)"
                )
                raw_narratives.append(context_text)
            else:
                 raw_narratives.append(f"ℹ️ [현황] '{start_node}' 데이터 없음. 가정 기반 시뮬레이션.")

            raw_narratives.append(f"🔄 [시작] '{start_node}'의 파급 효과 분석 중...")
            
            # Get flow
            flow = self.kg.get_downstream_flow(start_node, max_depth=4)
            current_confidence = 1.0
            
            for rel in flow:
                # Calculate Step Score
                step_score = 1.0
                
                # A. Temporal Check
                if rel.conditions.get('time'):
                    time_score = self.temporal.is_condition_met(rel.conditions['time'])
                    step_score *= time_score
                
                # B. Predicate Direction
                direction = 0 # 0: Neutral, 1: Increase, -1: Decrease
                if "INCREASES" in rel.predicate or "CAUSES" in rel.predicate: 
                    direction = 1
                elif "DECREASES" in rel.predicate or "PREVENTS" in rel.predicate: 
                    direction = -1
                
                # C. Data Validation (Reality Check)
                # If the 'Subject' of this relation has real data, does it match the causality?
                # (Simplified: Just checking if Object matches expectation is safer)
                obj_data = self.market_data.get_market_indicator(rel.object_id)
                if obj_data:
                    # If we expect Increase, but Data says Down -> Penalty
                    expected_trend = "UP" if direction > 0 else "DOWN"
                    if direction != 0:
                        alignment = self.market_data.check_trend_alignment(rel.object_id, "INCREASE" if direction > 0 else "DECREASE")
                        if alignment > 0.8: step_score *= 1.2 # Boost
                        elif alignment < 0.3: step_score *= 0.6 # Penalty

                current_confidence *= step_score
                
                # Accumulate Impact
                target = rel.object_id
                if target not in impact_map:
                    impact_map[target] = {"score": 0.0, "sources": []}
                
                impact_factor = direction * current_confidence
                impact_map[target]["score"] += impact_factor
                impact_map[target]["sources"].append(f"{rel.subject_id} -> {target}")

                # Verify paths
                all_paths.append(rel)
                path_scores.append(current_confidence)
                
                # Add Descriptive Line
                verb = self._humanize_predicate_kr(rel.predicate)
                subj = self._get_label(rel.subject_id)
                obj = self._get_label(rel.object_id)
                raw_narratives.append(f"  🔗 {subj} -> {obj} ({verb}) [신뢰도: {current_confidence:.2f}]")

        # 2. Synthesis (Conflict Resolution)
        final_narratives = []
        final_narratives.extend(raw_narratives)
        
        if impact_map:
            final_narratives.append("")
            final_narratives.append("⚖️ [종합 분석] 상충되는 요인 조정 결과:")
            
            sorted_impacts = sorted(impact_map.items(), key=lambda x: abs(x[1]['score']), reverse=True)
            for node_id, data in sorted_impacts[:5]: # Top 5 impacts
                score = data["score"]
                node_label = self._get_label(node_id)
                
                conclusion = "영향 없음"
                if score > 0.3: conclusion = "📈 상승 압력 우세"
                elif score < -0.3: conclusion = "📉 하락 압력 우세"
                else: conclusion = "⚖️ 중립/상충 (불확실)"
                
                final_narratives.append(f"  • {node_label}: {conclusion} (강도: {score:.2f})")

        final_confidence = sum(path_scores) / len(path_scores) if path_scores else 0.0

        return InferredOutcome(
            outcome_text=final_narratives,
            path=all_paths,
            confidence=round(final_confidence, 2)
        )

    def _humanize_predicate_kr(self, pred) -> str:
        mapping = {
            "P_INCREASES": "증가시킴 (🔼)",
            "P_DECREASES": "감소시킴 (🔽)",
            "P_CAUSES": "유발함 (➡️)",
            "P_PREVENTS": "저지함 (🚫)"
        }
        return mapping.get(pred, "영향을 줌")
        
    def _translate_trend(self, trend_en) -> str:
        if trend_en == "UP": return "상승 📈"
        if trend_en == "DOWN": return "하락 📉"
        return "보합 ➖"

    def _get_label(self, term_id: str) -> str:
        # Helper to get human readable label from ID if possible, roughly
        # In real app, KG lookup is better, but here we just process string
        if term_id.startswith("TERM_"):
            return term_id.replace("TERM_", "").replace("_", " ")
        if term_id.startswith("NODE_"):
            return term_id.replace("NODE_", "").replace("_", " ")
        return term_id
