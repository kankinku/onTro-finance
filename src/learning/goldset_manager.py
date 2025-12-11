"""
L2. Teacher & Goldset Manager
"Teacher(LLM)와 사람이 만든 정답 세트를 관리하는 모듈"

역할:
- Teacher 라벨 생성 관리
- Gold Set 생성 및 버전 관리
- 정답 기준 제공
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.learning.models import (
    TeacherLabel, GoldSample, GoldSet, TaskType
)
from src.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class TeacherGoldsetManager:
    """
    L2. Teacher & Goldset Manager
    정답 세트 관리
    """
    
    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.llm_client = llm_client
        
        # Teacher 라벨 저장
        self._teacher_labels: Dict[str, List[TeacherLabel]] = {}  # version -> labels
        self._current_teacher_version: str = "teacher_v1"
        
        # Gold Set 저장
        self._goldsets: Dict[str, GoldSet] = {}  # version -> goldset
        self._active_goldset: Optional[str] = None
    
    def generate_teacher_labels(
        self,
        samples: List[Dict],
        task_type: TaskType,
        prompt_version: str = "prompt_v1",
        temperature: float = 0.1,
    ) -> List[TeacherLabel]:
        """
        Teacher LLM으로 라벨 생성
        
        Args:
            samples: 라벨링할 샘플들
            task_type: 태스크 유형
            prompt_version: 프롬프트 버전
            temperature: LLM 온도
        
        Returns:
            TeacherLabel 리스트
        """
        labels = []
        
        for sample in samples:
            text = sample.get("text", "")
            
            # 태스크별 프롬프트
            prompt = self._get_prompt(task_type, text, prompt_version)
            
            # LLM 호출
            predicted = {}
            if self.llm_client:
                try:
                    response = self.llm_client.generate_json(
                        prompt=prompt,
                        schema=self._get_schema(task_type),
                        temperature=temperature,
                    )
                    predicted = response if isinstance(response, dict) else {}
                except Exception as e:
                    logger.warning(f"Teacher labeling failed: {e}")
                    predicted = self._get_default_labels(task_type)
            else:
                predicted = self._get_default_labels(task_type)
            
            label = TeacherLabel(
                sample_id=sample.get("sample_id", ""),
                task_type=task_type,
                model_name=self.llm_client.model_name if self.llm_client else "rule_based",
                prompt_version=prompt_version,
                temperature=temperature,
                predicted_labels=predicted,
            )
            labels.append(label)
        
        # 저장
        version = f"teacher_{datetime.now().strftime('%Y%m%d_%H%M')}"
        self._teacher_labels[version] = labels
        self._current_teacher_version = version
        
        logger.info(f"Generated {len(labels)} teacher labels: {version}")
        return labels
    
    def _get_prompt(self, task_type: TaskType, text: str, version: str) -> str:
        """태스크별 프롬프트"""
        if task_type == TaskType.NER:
            return f"""Extract named entities from the following text.
Text: {text}
Output JSON with: entities (list of {{text, type, start, end}})"""
        
        elif task_type == TaskType.RELATION:
            return f"""Extract relations from the following text.
Text: {text}
Output JSON with: relations (list of {{head, tail, type, sign}})"""
        
        elif task_type == TaskType.SEMANTIC_VALIDATION:
            return f"""Evaluate the semantic validity of this relation.
Text: {text}
Output JSON with: semantic_tag (sem_confident/sem_weak/sem_spurious/sem_wrong/sem_ambiguous)"""
        
        elif task_type == TaskType.SIGN_VALIDATION:
            return f"""Determine the polarity/sign of this relation.
Text: {text}
Output JSON with: sign (+/-/neutral), confidence (0-1)"""
        
        return f"Analyze: {text}"
    
    def _get_schema(self, task_type: TaskType) -> Dict:
        """태스크별 스키마"""
        schemas = {
            TaskType.NER: {"entities": []},
            TaskType.RELATION: {"relations": []},
            TaskType.SEMANTIC_VALIDATION: {"semantic_tag": "sem_ambiguous"},
            TaskType.SIGN_VALIDATION: {"sign": "neutral", "confidence": 0.5},
        }
        return schemas.get(task_type, {})
    
    def _get_default_labels(self, task_type: TaskType) -> Dict:
        """기본 라벨"""
        return self._get_schema(task_type)
    
    def create_goldset(
        self,
        task_type: TaskType,
        samples: List[GoldSample],
        version: Optional[str] = None,
    ) -> GoldSet:
        """
        Gold Set 생성
        
        Args:
            task_type: 태스크 유형
            samples: Gold 샘플들
            version: 버전 (없으면 자동 생성)
        
        Returns:
            GoldSet
        """
        if version is None:
            existing = [k for k in self._goldsets.keys() if task_type.value in k]
            version = f"gold_{task_type.value}_v{len(existing) + 1}"
        
        # 통계 계산
        difficulty_dist = {}
        domain_dist = {}
        for s in samples:
            difficulty_dist[s.difficulty] = difficulty_dist.get(s.difficulty, 0) + 1
            domain_dist[s.domain_category] = domain_dist.get(s.domain_category, 0) + 1
        
        goldset = GoldSet(
            version=version,
            task_type=task_type,
            samples=samples,
            sample_count=len(samples),
            difficulty_distribution=difficulty_dist,
            domain_distribution=domain_dist,
        )
        
        # 저장 (append, 덮어쓰기 안 함)
        self._goldsets[version] = goldset
        
        logger.info(f"Created goldset {version}: {len(samples)} samples")
        return goldset
    
    def add_gold_sample(
        self,
        goldset_version: str,
        text: str,
        task_type: TaskType,
        gold_labels: Dict,
        difficulty: str = "normal",
        domain_category: str = "general",
        reviewer: str = "human",
    ) -> Optional[GoldSample]:
        """Gold Set에 샘플 추가"""
        goldset = self._goldsets.get(goldset_version)
        if not goldset:
            logger.warning(f"Goldset not found: {goldset_version}")
            return None
        
        sample = GoldSample(
            text=text,
            task_type=task_type,
            gold_labels=gold_labels,
            reviewer=reviewer,
            difficulty=difficulty,
            domain_category=domain_category,
        )
        
        goldset.samples.append(sample)
        goldset.sample_count += 1
        goldset.difficulty_distribution[difficulty] = goldset.difficulty_distribution.get(difficulty, 0) + 1
        goldset.domain_distribution[domain_category] = goldset.domain_distribution.get(domain_category, 0) + 1
        
        return sample
    
    def set_active_goldset(self, version: str) -> bool:
        """활성 Gold Set 설정"""
        if version not in self._goldsets:
            return False
        
        # 기존 비활성화
        for gs in self._goldsets.values():
            gs.is_active = False
        
        self._goldsets[version].is_active = True
        self._active_goldset = version
        
        logger.info(f"Active goldset: {version}")
        return True
    
    def get_goldset(self, version: str) -> Optional[GoldSet]:
        """Gold Set 조회"""
        return self._goldsets.get(version)
    
    def get_active_goldset(self) -> Optional[GoldSet]:
        """활성 Gold Set 조회"""
        if self._active_goldset:
            return self._goldsets.get(self._active_goldset)
        return None
    
    def list_goldsets(self) -> List[Dict]:
        """Gold Set 목록"""
        return [
            {
                "version": gs.version,
                "task_type": gs.task_type.value,
                "sample_count": gs.sample_count,
                "is_active": gs.is_active,
                "difficulty": gs.difficulty_distribution,
                "domain": gs.domain_distribution,
            }
            for gs in self._goldsets.values()
        ]
    
    def get_teacher_labels(self, version: str) -> List[TeacherLabel]:
        """Teacher 라벨 조회"""
        return self._teacher_labels.get(version, [])
    
    def get_stats(self) -> Dict:
        """통계"""
        return {
            "goldsets": len(self._goldsets),
            "teacher_versions": len(self._teacher_labels),
            "active_goldset": self._active_goldset,
            "current_teacher": self._current_teacher_version,
        }
