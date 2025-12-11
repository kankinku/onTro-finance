"""
Extraction Pipeline
전체 Extraction Sector 워크플로우를 통합
"""
import logging
import time
from typing import List, Optional

from src.shared.models import (
    Fragment, EntityCandidate, ResolvedEntity, RawEdge, ExtractionResult
)
from src.shared.exceptions import ExtractionError
from src.llm.ollama_client import OllamaClient
from .fragment_extractor import FragmentExtractor
from .ner_student import NERStudent
from .entity_resolver import EntityResolver
from .relation_extractor import RelationExtractor

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """
    Extraction Sector 통합 파이프라인
    
    Raw Text → Fragment → Entity → Canonical Entity → Raw Edge
    """
    
    def __init__(
        self,
        llm_client: Optional[OllamaClient] = None,
        use_llm: bool = True,
    ):
        self.use_llm = use_llm
        self.llm_client = llm_client
        
        # 모듈 초기화
        self.fragment_extractor = FragmentExtractor(llm_client=llm_client)
        self.ner_student = NERStudent(llm_client=llm_client)
        self.entity_resolver = EntityResolver()
        self.relation_extractor = RelationExtractor(llm_client=llm_client)
    
    def process(self, raw_text: str, doc_id: str) -> ExtractionResult:
        """
        전체 추출 파이프라인 실행
        
        Args:
            raw_text: 원본 텍스트
            doc_id: 문서 ID
        
        Returns:
            ExtractionResult: 전체 추출 결과
        """
        start_time = time.time()
        warnings = []
        error_count = 0
        
        all_fragments: List[Fragment] = []
        all_entity_candidates: List[EntityCandidate] = []
        all_resolved: List[ResolvedEntity] = []
        all_edges: List[RawEdge] = []
        
        try:
            # Step 1: Fragment Extraction
            logger.info(f"[Pipeline] Step 1: Fragment Extraction for {doc_id}")
            fragments = self.fragment_extractor.extract(
                raw_text=raw_text,
                doc_id=doc_id,
                use_llm=self.use_llm,
            )
            all_fragments = fragments
            logger.info(f"  → Extracted {len(fragments)} fragments")
            
            # Step 2-4: 각 fragment에 대해 처리
            for fragment in fragments:
                try:
                    # Step 2: NER (Student1)
                    entity_candidates = self.ner_student.extract(
                        fragment_text=fragment.text,
                        fragment_id=fragment.fragment_id,
                        use_llm=self.use_llm,
                    )
                    all_entity_candidates.extend(entity_candidates)
                    
                    if not entity_candidates:
                        continue
                    
                    # Step 3: Entity Resolution
                    resolved_entities = self.entity_resolver.resolve(entity_candidates)
                    all_resolved.extend(resolved_entities)
                    
                    # Step 4: Relation Extraction (Student2)
                    raw_edges = self.relation_extractor.extract(
                        fragment_text=fragment.text,
                        fragment_id=fragment.fragment_id,
                        resolved_entities=resolved_entities,
                        use_llm=self.use_llm,
                    )
                    all_edges.extend(raw_edges)
                    
                except Exception as e:
                    error_count += 1
                    warnings.append(f"Fragment {fragment.fragment_id}: {str(e)}")
                    logger.warning(f"Error processing fragment: {e}")
                    continue
            
        except ExtractionError as e:
            error_count += 1
            warnings.append(f"Pipeline error: {str(e)}")
            logger.error(f"Pipeline failed: {e}")
        
        processing_time = (time.time() - start_time) * 1000
        
        result = ExtractionResult(
            doc_id=doc_id,
            fragments=all_fragments,
            entity_candidates=all_entity_candidates,
            resolved_entities=all_resolved,
            raw_edges=all_edges,
            processing_time_ms=processing_time,
            error_count=error_count,
            warning_messages=warnings,
        )
        
        logger.info(
            f"[Pipeline] Complete: {len(all_fragments)} fragments, "
            f"{len(all_entity_candidates)} entities, {len(all_edges)} edges, "
            f"{processing_time:.2f}ms"
        )
        
        return result
    
    def process_batch(
        self,
        documents: List[dict],
    ) -> List[ExtractionResult]:
        """
        여러 문서 배치 처리
        
        Args:
            documents: [{"doc_id": "...", "text": "..."}] 형태
        
        Returns:
            ExtractionResult 리스트
        """
        results = []
        for doc in documents:
            doc_id = doc.get("doc_id", f"doc_{len(results)}")
            text = doc.get("text", "")
            
            result = self.process(raw_text=text, doc_id=doc_id)
            results.append(result)
        
        return results
