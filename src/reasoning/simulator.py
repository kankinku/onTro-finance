from typing import List, Dict, Tuple, Union
from collections import deque
import math
from src.schemas.base_models import InferredOutcome, Relation
from src.api.market_data import MarketDataProvider
from src.reasoning.temporal_integrator import TemporalIntegrator


class ScenarioSimulator:
    """
    [Reasoning Engine v5.0]
    Advanced Simulator with Temporal & Data layers.
    Refactored to support Causal Propagation (Strong Ontology).
    Supports both KnowledgeGraph and KnowledgeGraphService.
    """

    def __init__(self, kg):
        """
        Args:
            kg: KnowledgeGraph 또는 KnowledgeGraphService 인스턴스
        """
        # KnowledgeGraphService인 경우 내부 graph 속성 사용
        if hasattr(kg, 'graph'):
            self.kg = kg
        else:
            self.kg = kg
        self.market_data = MarketDataProvider()
        self.temporal = TemporalIntegrator()

    def simulate(self, trigger_nodes: List[str]) -> InferredOutcome:
        """
        [Strong Ontology Inference Engine]
        Causal Propagation with Sign & Strength.
        Algorithm:
        1. Initialize triggers with Impact=1.0, Sign=+1 (Hypothetical Increase)
        2. Propagate through graph:
           - Next Impact = Current Impact * Edge Strength
           - Next Sign = Current Sign * Edge Sign
        3. Aggregate impacts per node.
        """
        MAX_DEPTH = 3
        
        # Queue: (node_id, current_sign, current_strength, path_history_list)
        # Using list as queue
        queue = []
        
        # Result Storage
        # node_id: { "score": float, "market_val": val, "paths": [] }
        impact_analysis = {}
        all_paths_objects = []

        # 1. Initialize
        for start_node in trigger_nodes:
            # We assume the trigger event is happening / increasing
            queue.append((start_node, 1, 1.0, []))
            
            # Context Check
            start_data = self.market_data.get_market_indicator(start_node)
            if start_data:
                impact_analysis[start_node] = {
                    "score": 0, "sources": ["Trigger (Reality Check)"], 
                    "market_val": getattr(start_data, 'value', None),
                    "paths": []
                }

        # 2. Propagation (BFS-like Causal Walk)
        viz_logs = []
        
        while queue:
            curr_node, curr_sign, curr_str, history = queue.pop(0)
            
            if len(history) >= MAX_DEPTH:
                continue
            
            # Use Knowledge Graph to find out_edges
            if curr_node not in self.kg.graph:
                continue
                
            out_edges = self.kg.graph.out_edges(curr_node, data=True)
            
            for u, v, data in out_edges:
                # Simple Cycle Check (Prevent loop in current path)
                path_nodes = [h['node'] for h in history]
                if v in path_nodes or v == curr_node:
                    continue

                rel_obj = data.get("relation_object") 
                if not rel_obj: continue

                # Extract Edge Param (Safe Get with Defaults)
                # Simulator Update for Dict/Object compatibility
                if isinstance(rel_obj, dict):
                    edge_sign = rel_obj.get("sign", 1)
                    edge_strength = rel_obj.get("strength", 1.0)
                else:
                    edge_sign = getattr(rel_obj, "sign", 1)
                    edge_strength = getattr(rel_obj, "strength", 1.0)
                
                # Logic: Sign multiplication & Strength decay
                next_sign = curr_sign * edge_sign
                next_str = curr_str * edge_strength
                
                # Decay factor (0.9 per hop to prioritize closer impacts)
                next_str *= 0.9
                
                if next_str < 0.1: continue # Prune weak paths

                # Record Path
                new_hist = history + [{
                    "node": curr_node, 
                    "edge": rel_obj,
                    "target": v
                }]
                
                # Aggregate Impact
                if v not in impact_analysis:
                    impact_analysis[v] = {"score": 0.0, "paths": []}
                
                impact_val = next_sign * next_str
                impact_analysis[v]["score"] += impact_val
                
                # Store readable path for explanation
                path_desc = f"{' -> '.join([self._get_label(h['node']) for h in new_hist])} -> {self._get_label(v)}"
                impact_analysis[v]["paths"].append(path_desc)
                
                all_paths_objects.append(rel_obj)
                
                # Log for Visualization in Outcome (No Emoji, Pure Text)
                arrow = "[긍정 영향]" if next_sign > 0 else "[부정 영향]"
                viz_logs.append(f"  - {self._get_label(curr_node)} --(강도 {edge_strength:.1f})--> {self._get_label(v)} : {arrow} (누적: {next_str:.2f})")

                # Enqueue next step
                queue.append((v, next_sign, next_str, new_hist))

        # 3. Final Report Generation
        final_narratives = []
        final_narratives.append(f"[시뮬레이션 시작] 트리거: {', '.join([self._get_label(t) for t in trigger_nodes])} (가정: 상승/발생)")
        
        # Sort impacts by absolute score
        sorted_impacts = sorted(impact_analysis.items(), key=lambda x: abs(x[1]['score']), reverse=True)
        
        if not sorted_impacts:
             final_narratives.append("유의미한 파급 효과가 발견되지 않았습니다. (그래프 연결 부족 또는 약한 상관관계)")

        # Top Impacts
        for node_id, data in sorted_impacts:
            if node_id in trigger_nodes: continue # Skip trigger itself from impact list
            
            score = data["score"]
            label = self._get_label(node_id)
            
            if abs(score) < 0.15: continue # Ignore noise
            
            direction = "증가/상승" if score > 0 else "감소/하락"
            strength_desc = "강함" if abs(score) > 0.6 else "중간" if abs(score) > 0.4 else "약함"
            
            # Pure Text Format
            final_narratives.append(f"- {label}: {direction} (강도: {strength_desc}, 순영향: {score:.2f})")
            
            # Show top reasoning path
            if data["paths"]:
                # Shorten path string if too long
                shortest_path = sorted(data["paths"], key=len)[0]
                final_narratives.append(f"   └ 주요 경로: {shortest_path}")

        final_narratives.append("")
        final_narratives.append("[추론 상세 로그]")
        final_narratives.extend(viz_logs[:15]) # Show top 15 logs for transparency

        avg_conf = sum([abs(x[1]['score']) for x in sorted_impacts]) / len(sorted_impacts) if sorted_impacts else 0.0

        return InferredOutcome(
            outcome_text=final_narratives,
            path=all_paths_objects,
            confidence=round(min(avg_conf, 1.0), 2)
        )

    def _humanize_predicate_kr(self, pred) -> str:
        # Compatibility with old predicate strings if needed, but mainly relying on sign now.
        mapping = {
            "P_INCREASES": "증가시킴",
            "P_DECREASES": "감소시킴",
            "P_CAUSES": "유발함",
            "P_PREVENTS": "저지함"
        }
        return mapping.get(pred, "영향을 줌")
        
    def _translate_trend(self, trend_en) -> str:
        if trend_en == "UP": return "상승"
        if trend_en == "DOWN": return "하락"
        return "보합"

    def _get_label(self, term_id: str) -> str:
        # Helper to get human readable label from ID if possible
        if term_id.startswith("TERM_"):
            return term_id.replace("TERM_", "").replace("_", " ")
        if term_id.startswith("NODE_"):
            return term_id.replace("NODE_", "").replace("_", " ")
        return term_id
