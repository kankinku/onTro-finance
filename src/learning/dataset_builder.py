"""
L1. Training Dataset Builder
"로그 + KG에서 학습용 데이터셋을 만드는 공장"

입력: Validation Log, Domain KG, Personal KG, Query Log, User QA Log
출력: Task별 DatasetSnapshot (버전 관리)
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.learning.models import (
    TrainingSample, DatasetSnapshot, DataSource, TaskType
)
from src.domain.dynamic_update import DynamicDomainUpdate
from src.personal.pkg_update import PersonalKGUpdate

logger = logging.getLogger(__name__)


# Source별 신뢰도
SOURCE_CONFIDENCE = {
    DataSource.DOMAIN_STATIC: 1.0,
    DataSource.DOMAIN_DYNAMIC: 0.8,
    DataSource.USER_QA: 0.9,
    DataSource.TEACHER_LLM: 0.7,
    DataSource.VALIDATION_LOG: 0.6,
    DataSource.DRIFT_LOG: 0.6,
    DataSource.PERSONAL: 0.4,
}


class TrainingDatasetBuilder:
    """
    L1. Training Dataset Builder
    학습 데이터셋 생성 및 관리
    """
    
    def __init__(
        self,
        domain: Optional[DynamicDomainUpdate] = None,
        personal: Optional[PersonalKGUpdate] = None,
    ):
        self.domain = domain
        self.personal = personal
        
        # 로그 저장소
        self._validation_logs: List[Dict] = []
        self._drift_logs: List[Dict] = []
        self._query_logs: List[Dict] = []
        self._user_qa_logs: List[Dict] = []
        
        # 데이터셋 스냅샷 저장
        self._snapshots: Dict[str, DatasetSnapshot] = {}
    
    def add_validation_log(self, log: Dict):
        """Validation 실패 로그 추가"""
        log["logged_at"] = datetime.now()
        self._validation_logs.append(log)
    
    def add_drift_log(self, log: Dict):
        """Drift 로그 추가"""
        log["logged_at"] = datetime.now()
        self._drift_logs.append(log)
    
    def add_query_log(self, log: Dict):
        """Query Reasoning 로그 추가"""
        log["logged_at"] = datetime.now()
        self._query_logs.append(log)
    
    def add_user_qa(self, sample: Dict):
        """User QA 피드백 추가"""
        sample["logged_at"] = datetime.now()
        self._user_qa_logs.append(sample)
    
    def build_dataset(
        self,
        task_type: TaskType,
        version_suffix: str = "v1",
        include_domain: bool = True,
        include_personal: bool = True,
        include_logs: bool = True,
        include_user_qa: bool = True,
    ) -> DatasetSnapshot:
        """
        데이터셋 빌드
        
        Args:
            task_type: 태스크 유형
            version_suffix: 버전 접미사
            include_*: 포함할 소스
        
        Returns:
            DatasetSnapshot
        """
        samples = []
        source_counts = {}
        
        # Domain에서 샘플 생성
        if include_domain and self.domain:
            domain_samples = self._build_from_domain(task_type)
            samples.extend(domain_samples)
            source_counts["domain"] = len(domain_samples)
        
        # Personal에서 샘플 생성
        if include_personal and self.personal:
            personal_samples = self._build_from_personal(task_type)
            samples.extend(personal_samples)
            source_counts["personal"] = len(personal_samples)
        
        # 로그에서 샘플 생성
        if include_logs:
            log_samples = self._build_from_logs(task_type)
            samples.extend(log_samples)
            source_counts["logs"] = len(log_samples)
        
        # User QA에서 샘플 생성
        if include_user_qa:
            qa_samples = self._build_from_user_qa(task_type)
            samples.extend(qa_samples)
            source_counts["user_qa"] = len(qa_samples)
        
        # 평균 신뢰도 계산
        avg_conf = 0.0
        if samples:
            avg_conf = sum(s.label_confidence for s in samples) / len(samples)
        
        # 스냅샷 생성
        version = f"{datetime.now().strftime('%Y-%m-%d')}_{version_suffix}"
        snapshot = DatasetSnapshot(
            version=version,
            task_type=task_type,
            samples=samples,
            sample_count=len(samples),
            source_distribution=source_counts,
            avg_label_confidence=avg_conf,
            frozen=True,
        )
        
        # 저장
        self._snapshots[snapshot.dataset_id] = snapshot
        
        logger.info(
            f"Built dataset {snapshot.dataset_id}: "
            f"{len(samples)} samples, avg_conf={avg_conf:.2f}"
        )
        
        return snapshot
    
    def _build_from_domain(self, task_type: TaskType) -> List[TrainingSample]:
        """Domain KG에서 샘플 생성"""
        samples = []
        
        for rel in self.domain.get_all_relations().values():
            if task_type == TaskType.RELATION:
                sample = TrainingSample(
                    text=f"{rel.head_name} {rel.relation_type} {rel.tail_name}",
                    task_type=task_type,
                    labels={
                        "head": rel.head_id,
                        "tail": rel.tail_id,
                        "relation_type": rel.relation_type,
                        "sign": rel.sign,
                    },
                    source=DataSource.DOMAIN_DYNAMIC,
                    label_confidence=rel.domain_conf * SOURCE_CONFIDENCE[DataSource.DOMAIN_DYNAMIC],
                    source_relation_id=rel.relation_id,
                )
                samples.append(sample)
            
            elif task_type == TaskType.SIGN_VALIDATION:
                sample = TrainingSample(
                    text=f"{rel.head_name} → {rel.tail_name}",
                    task_type=task_type,
                    labels={
                        "sign": rel.sign,
                        "valid": True,
                    },
                    source=DataSource.DOMAIN_DYNAMIC,
                    label_confidence=rel.domain_conf * SOURCE_CONFIDENCE[DataSource.DOMAIN_DYNAMIC],
                    source_relation_id=rel.relation_id,
                )
                samples.append(sample)
        
        return samples
    
    def _build_from_personal(self, task_type: TaskType) -> List[TrainingSample]:
        """Personal KG에서 샘플 생성"""
        samples = []
        
        for rel in self.personal.get_all_relations().values():
            if task_type in [TaskType.RELATION, TaskType.SIGN_VALIDATION]:
                sample = TrainingSample(
                    text=f"{rel.head_name} → {rel.tail_name}",
                    task_type=task_type,
                    labels={
                        "head": rel.head_id,
                        "tail": rel.tail_id,
                        "sign": rel.sign,
                        "personal_label": rel.personal_label.value,
                    },
                    source=DataSource.PERSONAL,
                    label_confidence=rel.pcs_score * SOURCE_CONFIDENCE[DataSource.PERSONAL],
                    source_relation_id=rel.relation_id,
                )
                samples.append(sample)
        
        return samples
    
    def _build_from_logs(self, task_type: TaskType) -> List[TrainingSample]:
        """로그에서 샘플 생성"""
        samples = []
        
        # Validation 실패 로그
        for log in self._validation_logs:
            if task_type == TaskType.SEMANTIC_VALIDATION:
                sample = TrainingSample(
                    text=log.get("fragment_text", ""),
                    task_type=task_type,
                    labels={
                        "semantic_tag": log.get("semantic_tag", "unknown"),
                        "rejection_reason": log.get("rejection_reason", ""),
                    },
                    source=DataSource.VALIDATION_LOG,
                    label_confidence=SOURCE_CONFIDENCE[DataSource.VALIDATION_LOG],
                    source_edge_id=log.get("edge_id"),
                )
                samples.append(sample)
        
        return samples
    
    def _build_from_user_qa(self, task_type: TaskType) -> List[TrainingSample]:
        """User QA에서 샘플 생성"""
        samples = []
        
        for qa in self._user_qa_logs:
            sample = TrainingSample(
                text=qa.get("text", ""),
                task_type=task_type,
                labels=qa.get("labels", {}),
                source=DataSource.USER_QA,
                label_confidence=SOURCE_CONFIDENCE[DataSource.USER_QA],
            )
            samples.append(sample)
        
        return samples
    
    def get_snapshot(self, dataset_id: str) -> Optional[DatasetSnapshot]:
        """스냅샷 조회"""
        return self._snapshots.get(dataset_id)
    
    def list_snapshots(self) -> List[Dict]:
        """스냅샷 목록"""
        return [
            {
                "dataset_id": s.dataset_id,
                "version": s.version,
                "task_type": s.task_type.value,
                "sample_count": s.sample_count,
                "avg_confidence": s.avg_label_confidence,
                "created_at": s.created_at.isoformat(),
            }
            for s in self._snapshots.values()
        ]
    
    def get_stats(self) -> Dict:
        """통계"""
        return {
            "snapshots": len(self._snapshots),
            "validation_logs": len(self._validation_logs),
            "drift_logs": len(self._drift_logs),
            "query_logs": len(self._query_logs),
            "user_qa_logs": len(self._user_qa_logs),
        }
