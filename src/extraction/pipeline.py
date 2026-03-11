"""
Extraction Pipeline
전체 Extraction Sector 워크플로우를 통합
"""

import logging
import time
from typing import Any, List, Optional

from src.shared.models import (
    Fragment,
    EntityCandidate,
    ResolvedEntity,
    RawEdge,
    ExtractionResult,
    SourceDocument,
)
from src.shared.exceptions import ExtractionError
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
        llm_client: Optional[Any] = None,
        use_llm: bool = True,
    ):
        self.use_llm = use_llm
        self.llm_client = llm_client

        # 모듈 초기화
        self.fragment_extractor = FragmentExtractor(llm_client=llm_client)
        self.ner_student = NERStudent(llm_client=llm_client)
        self.entity_resolver = EntityResolver()
        self.relation_extractor = RelationExtractor(llm_client=llm_client)

    def process(
        self,
        raw_text: str,
        doc_id: str,
        source_document: Optional[SourceDocument] = None,
    ) -> ExtractionResult:
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
        source_document = source_document or SourceDocument(doc_id=doc_id)

        try:
            # Step 1: Fragment Extraction
            logger.info(f"[Pipeline] Step 1: Fragment Extraction for {doc_id}")
            fragments = self.fragment_extractor.extract(
                raw_text=raw_text,
                doc_id=doc_id,
                use_llm=self.use_llm,
            )
            for fragment in fragments:
                fragment.source_document = source_document
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
                    for raw_edge in raw_edges:
                        raw_edge.source_document_id = source_document.doc_id
                        raw_edge.source_type = source_document.source_type
                        raw_edge.published_at = source_document.published_at
                        raw_edge.citation_start = fragment.source_start
                        raw_edge.citation_end = fragment.source_end
                        raw_edge.citation_page_number = fragment.page_number
                        raw_edge.citation_chapter_title = fragment.chapter_title
                        raw_edge.citation_section_title = fragment.section_title
                        raw_edge.source_metadata = {
                            "title": source_document.title,
                            "author": source_document.author,
                            "institution": source_document.institution,
                            "region": source_document.region,
                            "asset_scope": source_document.asset_scope,
                            "language": source_document.language,
                            "document_quality_tier": source_document.document_quality_tier,
                            "page_number": fragment.page_number,
                            "chapter_title": fragment.chapter_title,
                            "section_title": fragment.section_title,
                            "block_type": fragment.block_type,
                            "table_caption": fragment.table_caption,
                            "table_rows": fragment.table_rows,
                            "table_columns": fragment.table_columns,
                            "table_headers": fragment.table_headers,
                            "table_cells": fragment.table_cells,
                            **source_document.metadata,
                        }
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
        consolidated_relations = self._consolidate_relations(all_edges)

        result = ExtractionResult(
            doc_id=doc_id,
            source_document=source_document,
            fragments=all_fragments,
            entity_candidates=all_entity_candidates,
            resolved_entities=all_resolved,
            raw_edges=all_edges,
            consolidated_relations=consolidated_relations,
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

    def _consolidate_relations(self, raw_edges: List[RawEdge]) -> List[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

        for edge in raw_edges:
            head_key = edge.head_canonical_name or edge.head_entity_id
            tail_key = edge.tail_canonical_name or edge.tail_entity_id
            key = (head_key, edge.relation_type, tail_key)
            item = grouped.setdefault(
                key,
                {
                    "head_entity_id": head_key,
                    "relation_type": edge.relation_type,
                    "tail_entity_id": tail_key,
                    "fragment_ids": set(),
                    "page_numbers": set(),
                    "section_titles": set(),
                    "chapter_titles": set(),
                    "block_types": set(),
                    "max_confidence": 0.0,
                    "polarity": edge.polarity_guess,
                },
            )
            item["fragment_ids"].add(edge.fragment_id)
            if edge.citation_page_number is not None:
                item["page_numbers"].add(edge.citation_page_number)
            if edge.citation_section_title:
                item["section_titles"].add(edge.citation_section_title)
            if edge.citation_chapter_title:
                item["chapter_titles"].add(edge.citation_chapter_title)
            block_type = edge.source_metadata.get("block_type")
            if block_type:
                item["block_types"].add(str(block_type))
            item["max_confidence"] = max(float(item["max_confidence"]), float(edge.student_conf))

        consolidated: List[dict[str, Any]] = []
        for value in grouped.values():
            consolidated.append(
                {
                    "head_entity_id": value["head_entity_id"],
                    "relation_type": value["relation_type"],
                    "tail_entity_id": value["tail_entity_id"],
                    "fragment_count": len(value["fragment_ids"]),
                    "page_numbers": sorted(value["page_numbers"]),
                    "chapter_titles": sorted(value["chapter_titles"]),
                    "section_titles": sorted(value["section_titles"]),
                    "block_types": sorted(value["block_types"]),
                    "max_confidence": value["max_confidence"],
                    "polarity": value["polarity"],
                }
            )

        consolidated.sort(
            key=lambda item: (
                -int(item["fragment_count"]),
                -float(item["max_confidence"]),
                str(item["relation_type"]),
            )
        )
        return consolidated

    def process_batch(
        self,
        documents: List[dict[str, Any]],
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
            source_document = doc.get("source_document")
            if source_document is None and doc.get("metadata"):
                source_document = SourceDocument(doc_id=doc_id, metadata=doc["metadata"])

            result = self.process(raw_text=text, doc_id=doc_id, source_document=source_document)
            results.append(result)

        return results
