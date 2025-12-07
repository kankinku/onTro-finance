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
            # Strong Ontology Logic:
            # We trust M1 (LLM) output which is now structured with strict extraction rules.
            # Variables[0] -> Subject, Variables[1] -> Object
            
            if len(frag.term_candidates) >= 2:
                subj_text = frag.term_candidates[0]
                obj_text = frag.term_candidates[1]
                
                # entity resolution
                subj = resolution_map.get(subj_text)
                obj = resolution_map.get(obj_text)

                if subj and obj:
                    # Determine predicate for GraphViz/display compatibility
                    # If relation_kind is PROPORTIONAL, sign determines INC/DEC
                    final_pred = frag.predicate_candidate
                    if not final_pred:
                        if frag.sign > 0: final_pred = PredicateType.INCREASES
                        elif frag.sign < 0: final_pred = PredicateType.DECREASES
                        else: final_pred = PredicateType.CAUSES

                    rel = Relation(
                        rel_id=f"REL_{uuid.uuid4().hex[:8].upper()}",
                        subject_id=subj.entity_id,
                        predicate=final_pred or PredicateType.CAUSES,
                        object_id=obj.entity_id,
                        conditions={
                            "time": frag.condition_text,
                            "context": frag.mechanism_text,
                            "raw_kind": frag.relation_kind
                        },
                        # Strong Ontology Fields
                        relation_kind=frag.relation_kind or "CAUSAL",
                        sign=frag.sign if frag.sign is not None else 1,
                        strength=frag.strength if frag.strength is not None else 1.0,
                        lag_days=frag.lag_days if frag.lag_days is not None else 0
                    )
                    relations.append(rel)
                else:
                    print(f"Skipping fragment {frag.fragment_id}: Unresolved entities {subj_text}, {obj_text}")

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
