# Ontology System

Python 기반 지식 그래프 구축, 추론, 학습 시스템.

## 📋 개요

**6-Layer 아키텍처**로 구성된 지식 관리 및 추론 시스템:

```
[Layer 1-4: Knowledge Pipeline]
Raw Text → Extraction → Validation → Domain/Personal

[Layer 5: Reasoning]
Query → Graph Retrieval → Path Reasoning → Conclusion

[Layer 6: Learning/Evolution]
Logs → Dataset → Training → Policy → Deployment
```

## 🏗️ 6-Layer 아키텍처

### Layer 1: Extraction
텍스트에서 엔티티와 관계 추출

### Layer 2: Validation  
Schema, Sign, Semantic 검증

### Layer 3: Domain
Static/Dynamic 도메인 지식 관리

### Layer 4: Personal
개인 지식 저장 (삭제 없음)

### Layer 5: Reasoning
그래프 기반 인과 추론

### Layer 6: Learning/Evolution
| 모듈 | 역할 |
|------|------|
| L1. Dataset Builder | 로그/KG에서 학습 데이터셋 생성 |
| L2. Goldset Manager | Teacher 라벨/Gold Set 관리 |
| L3. Trainer | Student/Validator 학습 |
| L4. Policy Learner | EES/PCS/Threshold 최적화 |
| L5. Deployment | Review → Deploy 관리 |

## 📁 프로젝트 구조

```
ontology_system/
├── src/
│   ├── extraction/
│   ├── validation/
│   ├── domain/
│   ├── personal/
│   ├── reasoning/
│   ├── learning/      # NEW
│   ├── llm/
│   └── shared/
├── tests/
├── config/
└── main.py
```

## 🚀 설치 및 실행

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
pytest tests/ -v  # 58 tests
```

## ⚙️ Learning Layer 핵심 원칙

1. **투명성**: 모든 학습은 버전/메트릭/diff가 보임
2. **제어**: 자동 교체 금지, 사람이 최종 결정
3. **추적성**: run 단위 기록, 언제든 재현 가능
4. **점진적**: Proposal → Review → Deploy 구조

## 📊 Dashboard 기능

```python
from src.learning import LearningDashboard

dashboard = LearningDashboard(...)
summary = dashboard.get_summary()
# - 현재 활성 버전
# - Training run 목록
# - Domain/Personal 품질 리포트
```

## 🧪 테스트

```
58 passed ✅
- Extraction: 10
- Validation: 12
- Domain: 10
- Personal: 9
- Reasoning: 11
- Learning: 6
```

## 📝 라이선스

MIT License
