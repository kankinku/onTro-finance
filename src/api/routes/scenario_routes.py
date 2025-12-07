"""
Scenario Routes
시나리오 학습/추론 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from src.schemas.base_models import ScenarioInput, InferredOutcome
from src.pipeline.m1_analyzer import InputAnalyzer
from src.pipeline.m2_entity_resolver import EntityResolver
from src.pipeline.m3_relation import RelationConstructor
from src.services.kg_service import kg_service
from src.reasoning.simulator import ScenarioSimulator
from src.core.logger import logger

router = APIRouter()


@router.post("/learn")
async def learn_scenario(
    input_data: ScenarioInput, 
    background_tasks: BackgroundTasks
):
    """
    새로운 시나리오 학습
    텍스트를 분석하여 Knowledge Graph에 추가
    """
    try:
        # M1: 텍스트 분석
        analyzer = InputAnalyzer()
        fragments = analyzer.analyze(input_data.text)
        
        if not fragments:
            return {"status": "no_fragments", "message": "분석된 Fragment가 없습니다."}
        
        # M2: 엔티티 해결
        resolver = EntityResolver()
        resolution_map = resolver.resolve(fragments)
        
        # M3: 관계 구축
        constructor = RelationConstructor()
        relations = constructor.construct(fragments, resolution_map)
        
        # 백그라운드에서 KG 저장
        background_tasks.add_task(_save_to_knowledge_base, resolution_map, relations)
        
        return {
            "status": "success",
            "fragments_count": len(fragments),
            "relations_count": len(relations),
            "relations": [r.model_dump() for r in relations]
        }
        
    except Exception as e:
        logger.error(f"[Scenario] Learn failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/infer/{target_term_id}")
async def infer_scenario(target_term_id: str) -> InferredOutcome:
    """
    특정 Term에서 시작하는 시나리오 추론
    """
    try:
        simulator = ScenarioSimulator(kg_service)
        result = simulator.simulate([target_term_id])
        return result
    except Exception as e:
        logger.error(f"[Scenario] Inference failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _save_to_knowledge_base(resolution_map, relations):
    """백그라운드 태스크: KG에 저장"""
    from src.schemas.base_models import Term
    
    # 새로운 Term 추가
    for surface, resolved in resolution_map.items():
        if resolved.confidence < 1.0:
            new_term = Term(
                term_id=resolved.entity_id,
                label=surface,
                aliases=[],
                attributes={"auto_generated": True}
            )
            kg_service.add_term(new_term)
    
    # Relation 추가
    for rel in relations:
        kg_service.add_relation(rel)
    
    logger.info(f"[Scenario] Saved {len(relations)} relations to KG")
