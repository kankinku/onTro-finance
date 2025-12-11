"""
KG Transaction Manager
"KG 변경 사항을 안전하게 묶어서 처리"

책임:
- 트랜잭션 범위 정의 (begin/commit/rollback)
- 변경 사항 추적 (change log)
- 롤백 지원
- 동시성 제어 (lock)
"""
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from contextlib import contextmanager

from src.storage.graph_repository import GraphRepository
from src.shared.error_framework import StorageError, ErrorSeverity

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """작업 유형"""
    CREATE_ENTITY = "create_entity"
    UPDATE_ENTITY = "update_entity"
    DELETE_ENTITY = "delete_entity"
    CREATE_RELATION = "create_relation"
    UPDATE_RELATION = "update_relation"
    DELETE_RELATION = "delete_relation"


@dataclass
class ChangeRecord:
    """변경 기록"""
    operation: OperationType
    entity_id: Optional[str] = None
    src_id: Optional[str] = None
    rel_type: Optional[str] = None
    dst_id: Optional[str] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)


class TransactionState(Enum):
    """트랜잭션 상태"""
    PENDING = "pending"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class Transaction:
    """트랜잭션"""
    tx_id: str = field(default_factory=lambda: f"tx_{uuid.uuid4().hex[:8]}")
    state: TransactionState = TransactionState.PENDING
    changes: List[ChangeRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    committed_at: Optional[datetime] = None
    error: Optional[str] = None


class KGTransactionManager:
    """
    KG Transaction Manager
    
    사용:
        with tx_manager.transaction() as tx:
            tx_manager.create_entity(tx, ...)
            tx_manager.create_relation(tx, ...)
        # 자동 commit, 에러시 자동 rollback
    """
    
    def __init__(self, repository: GraphRepository):
        self._repo = repository
        self._active_tx: Dict[str, Transaction] = {}
        self._tx_history: List[Transaction] = []
        self._lock = threading.RLock()
    
    @contextmanager
    def transaction(self):
        """트랜잭션 컨텍스트 매니저"""
        tx = self._begin()
        try:
            yield tx
            self._commit(tx)
        except Exception as e:
            self._rollback(tx, str(e))
            raise
    
    def _begin(self) -> Transaction:
        """트랜잭션 시작"""
        with self._lock:
            tx = Transaction(state=TransactionState.ACTIVE)
            self._active_tx[tx.tx_id] = tx
            logger.debug(f"Transaction started: {tx.tx_id}")
            return tx
    
    def _commit(self, tx: Transaction) -> None:
        """트랜잭션 커밋"""
        with self._lock:
            if tx.tx_id not in self._active_tx:
                raise StorageError(
                    f"Transaction not found: {tx.tx_id}",
                    operation="commit",
                    severity=ErrorSeverity.HIGH,
                )
            
            tx.state = TransactionState.COMMITTED
            tx.committed_at = datetime.now()
            
            del self._active_tx[tx.tx_id]
            self._tx_history.append(tx)
            
            logger.info(f"Transaction committed: {tx.tx_id}, changes={len(tx.changes)}")
    
    def _rollback(self, tx: Transaction, error: Optional[str] = None) -> None:
        """트랜잭션 롤백"""
        with self._lock:
            if tx.tx_id not in self._active_tx:
                logger.warning(f"Transaction already closed: {tx.tx_id}")
                return
            
            # 역순으로 변경 취소
            for change in reversed(tx.changes):
                self._undo_change(change)
            
            tx.state = TransactionState.ROLLED_BACK
            tx.error = error
            
            del self._active_tx[tx.tx_id]
            self._tx_history.append(tx)
            
            logger.warning(f"Transaction rolled back: {tx.tx_id}, reason={error}")
    
    def _undo_change(self, change: ChangeRecord) -> None:
        """변경 취소"""
        try:
            if change.operation == OperationType.CREATE_ENTITY:
                if change.entity_id:
                    self._repo.delete_entity(change.entity_id)
            
            elif change.operation == OperationType.UPDATE_ENTITY:
                if change.entity_id and change.before_state:
                    self._repo.upsert_entity(
                        change.entity_id,
                        change.before_state.get("labels", []),
                        change.before_state.get("props", {}),
                    )
            
            elif change.operation == OperationType.DELETE_ENTITY:
                if change.before_state:
                    self._repo.upsert_entity(
                        change.entity_id,
                        change.before_state.get("labels", []),
                        change.before_state.get("props", {}),
                    )
            
            elif change.operation == OperationType.CREATE_RELATION:
                if change.src_id and change.rel_type and change.dst_id:
                    self._repo.delete_relation(change.src_id, change.rel_type, change.dst_id)
            
            elif change.operation == OperationType.UPDATE_RELATION:
                if change.before_state and change.src_id and change.rel_type and change.dst_id:
                    self._repo.upsert_relation(
                        change.src_id, change.rel_type, change.dst_id,
                        change.before_state.get("props", {}),
                    )
            
            elif change.operation == OperationType.DELETE_RELATION:
                if change.before_state and change.src_id and change.rel_type and change.dst_id:
                    self._repo.upsert_relation(
                        change.src_id, change.rel_type, change.dst_id,
                        change.before_state.get("props", {}),
                    )
        
        except Exception as e:
            logger.error(f"Failed to undo change: {change.operation}, error={e}")
    
    # ===========================================================================
    # CRUD with Transaction
    # ===========================================================================
    
    def create_entity(
        self,
        tx: Transaction,
        entity_id: str,
        labels: List[str],
        props: Dict[str, Any],
    ) -> None:
        """엔티티 생성"""
        self._check_tx_active(tx)
        
        # 실행
        self._repo.upsert_entity(entity_id, labels, props)
        
        # 기록
        tx.changes.append(ChangeRecord(
            operation=OperationType.CREATE_ENTITY,
            entity_id=entity_id,
            after_state={"labels": labels, "props": props},
        ))
    
    def update_entity(
        self,
        tx: Transaction,
        entity_id: str,
        labels: List[str],
        props: Dict[str, Any],
    ) -> None:
        """엔티티 업데이트"""
        self._check_tx_active(tx)
        
        # 이전 상태 저장
        before = self._repo.get_entity(entity_id)
        
        # 실행
        self._repo.upsert_entity(entity_id, labels, props)
        
        # 기록
        tx.changes.append(ChangeRecord(
            operation=OperationType.UPDATE_ENTITY,
            entity_id=entity_id,
            before_state=before,
            after_state={"labels": labels, "props": props},
        ))
    
    def delete_entity(self, tx: Transaction, entity_id: str) -> bool:
        """엔티티 삭제"""
        self._check_tx_active(tx)
        
        # 이전 상태 저장
        before = self._repo.get_entity(entity_id)
        if not before:
            return False
        
        # 실행
        result = self._repo.delete_entity(entity_id)
        
        # 기록
        tx.changes.append(ChangeRecord(
            operation=OperationType.DELETE_ENTITY,
            entity_id=entity_id,
            before_state=before,
        ))
        
        return result
    
    def create_relation(
        self,
        tx: Transaction,
        src_id: str,
        rel_type: str,
        dst_id: str,
        props: Dict[str, Any],
    ) -> None:
        """관계 생성"""
        self._check_tx_active(tx)
        
        # 실행
        self._repo.upsert_relation(src_id, rel_type, dst_id, props)
        
        # 기록
        tx.changes.append(ChangeRecord(
            operation=OperationType.CREATE_RELATION,
            src_id=src_id,
            rel_type=rel_type,
            dst_id=dst_id,
            after_state={"props": props},
        ))
    
    def update_relation(
        self,
        tx: Transaction,
        src_id: str,
        rel_type: str,
        dst_id: str,
        props: Dict[str, Any],
    ) -> None:
        """관계 업데이트"""
        self._check_tx_active(tx)
        
        # 이전 상태
        before = self._repo.get_relation(src_id, rel_type, dst_id)
        
        # 실행
        self._repo.upsert_relation(src_id, rel_type, dst_id, props)
        
        # 기록
        tx.changes.append(ChangeRecord(
            operation=OperationType.UPDATE_RELATION,
            src_id=src_id,
            rel_type=rel_type,
            dst_id=dst_id,
            before_state=before,
            after_state={"props": props},
        ))
    
    def delete_relation(
        self,
        tx: Transaction,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> bool:
        """관계 삭제"""
        self._check_tx_active(tx)
        
        # 이전 상태
        before = self._repo.get_relation(src_id, rel_type, dst_id)
        if not before:
            return False
        
        # 실행
        result = self._repo.delete_relation(src_id, rel_type, dst_id)
        
        # 기록
        tx.changes.append(ChangeRecord(
            operation=OperationType.DELETE_RELATION,
            src_id=src_id,
            rel_type=rel_type,
            dst_id=dst_id,
            before_state=before,
        ))
        
        return result
    
    def _check_tx_active(self, tx: Transaction) -> None:
        """트랜잭션 활성 확인"""
        if tx.state != TransactionState.ACTIVE:
            raise StorageError(
                f"Transaction not active: {tx.tx_id}, state={tx.state.value}",
                operation="check",
                severity=ErrorSeverity.HIGH,
            )
    
    # ===========================================================================
    # 통계
    # ===========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """통계"""
        committed = [t for t in self._tx_history if t.state == TransactionState.COMMITTED]
        rolled_back = [t for t in self._tx_history if t.state == TransactionState.ROLLED_BACK]
        
        return {
            "active_transactions": len(self._active_tx),
            "total_committed": len(committed),
            "total_rolled_back": len(rolled_back),
            "total_changes": sum(len(t.changes) for t in committed),
        }
    
    def get_recent_transactions(self, count: int = 10) -> List[Dict]:
        """최근 트랜잭션"""
        return [
            {
                "tx_id": t.tx_id,
                "state": t.state.value,
                "changes": len(t.changes),
                "created_at": t.created_at.isoformat(),
            }
            for t in self._tx_history[-count:]
        ]
