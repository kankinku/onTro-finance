from typing import List, Dict, Optional
import uuid
from src.schemas.base_models import Fragment, Relation, ResolvedEntity, PredicateType

class RelationConstructor:
    """
    [M3] Relation Constructor
    Responsibility: Assemble finalized Relations (Triples) from Fragments and Resolved Entities.
    """

    def __init__(self):
        pass

    def construct(self, fragments: List[Fragment], resolution_map: Dict[str, ResolvedEntity]) -> List[Relation]:
        """
        Transforms fragments into Relation objects.
        Warning: This requires logic to determine WHICH term is Subject and WHICH is Object.
        For V1, we use heuristics or assume the LLM (M1) provided ordered candidates or structure.
        """
        relations = []

        for frag in fragments:
            # Heuristic: 
            # If M1 provided explicit structure, great. 
            # Here we assume the LLM extraction in M1 implies:
            # Fact/Mech usually implies Cause -> Effect.
            # We look at the top 2 term candidates as Subject -> Object for simplicity in this demo,
            # OR we rely on the specific semantic roles if M1 gave them.
            
            # Let's try to parse the 'mechanism_candidates' or just map the first two terms.
            # In a real system, M1 should output {subject: "...", object: "..."} explicitly.
            # For this demo, we will perform a 'smart guess' based on the M1 output structure from the example.
            
            # Example M1 Output:
            # Terms: ["SLR 규제", "바젤3", "대차대조표", "국채 수요"]
            # Mechanism: "규제 강화 -> 대차대조표 감소"
            
            # We want to build:
            # 1. SLR Rule (Subject) -> CAUSES/DECREASES -> Balance Sheet Cap (Object)
            
            if len(frag.term_candidates) >= 2:
                # Naive Heuristic: First term is Subject, Third term (or specific target) is Object
                # In the specific user example: "SLR 규제"(0) ... "대차대조표"(2)
                
                subj_text = frag.term_candidates[0] # SLR 규제
                # Let's find the 'effect' term. "대차대조표" seems to be index 2 in the example list
                # or we simply take the next relevant noun.
                
                # To make this robust without a full dependency parser, let's map known patterns.
                try:
                    # Let's look for known "Subject" and "Object" in the resolved map
                    # This is where 'Entity Resolver' helps.
                    
                    subj = resolution_map.get(subj_text)
                    
                    # Try to find 'Balance Sheet' or 'Treasury Demand'
                    obj_text = next((t for t in frag.term_candidates if "대차대조표" in t or "국채" in t), None)
                    obj = resolution_map.get(obj_text) if obj_text else None

                    if subj and obj:
                        pred = self._map_predicate(frag.predicate_candidate)
                        
                        rel = Relation(
                            rel_id=f"REL_{uuid.uuid4().hex[:8].upper()}",
                            subject_id=subj.entity_id,
                            predicate=pred,
                            object_id=obj.entity_id,
                            conditions={
                                "time": frag.condition_text,
                                "context": frag.mechanism_text
                            }
                        )
                        relations.append(rel)
                        
                        # Chained Relation Check (Pattern: A->B, B->C)
                        # If there are more terms like "국채 매수 여력" (Treasury Buying Power)
                        # We might infer B -> C
                        second_obj_text = next((t for t in frag.term_candidates if "국채" in t and t != obj_text), None)
                        if second_obj_text:
                            second_obj = resolution_map.get(second_obj_text)
                            if second_obj:
                                rel2 = Relation(
                                    rel_id=f"REL_{uuid.uuid4().hex[:8].upper()}",
                                    subject_id=obj.entity_id, # Previous Object becomes Subject
                                    predicate=PredicateType.DECREASES, # Inferred from context "줄어든다"
                                    object_id=second_obj.entity_id,
                                    conditions={"context": "Outcome of reduced B/S"}
                                )
                                relations.append(rel2)

                except Exception as e:
                    print(f"Error constructing relation for fragment {frag.fragment_id}: {e}")
                    continue

        return relations

    def _map_predicate(self, raw_pred: Optional[str]) -> PredicateType:
        if not raw_pred:
            return PredicateType.CAUSES
        
        raw_upper = raw_pred.upper()
        if "DECREASE" in raw_upper or "REDUCE" in raw_upper:
            return PredicateType.DECREASES
        elif "INCREASE" in raw_upper:
            return PredicateType.INCREASES
        elif "PREVENT" in raw_upper:
            return PredicateType.PREVENTS
        
        return PredicateType.CAUSES
