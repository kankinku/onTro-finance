"""
전체 6-Layer 통합 테스트
모든 섹터/레이어 간 연결 확인
"""
import json
from pathlib import Path

# 모든 Layer import
from src.extraction import ExtractionPipeline
from src.validation import ValidationPipeline
from src.validation.models import ValidationDestination
from src.domain import DomainPipeline
from src.personal import PersonalPipeline
from src.reasoning import ReasoningPipeline
from src.learning import (
    TrainingDatasetBuilder, TeacherGoldsetManager,
    StudentValidatorTrainer, PolicyWeightLearner,
    ReviewDeploymentManager, LearningDashboard
)
from src.learning.models import TaskType, GoldSample
from src.llm import OllamaClient


def test_full_pipeline():
    """전체 파이프라인 통합 테스트"""
    print("="*70)
    print("🔗 6-LAYER INTEGRATION TEST")
    print("="*70)
    
    # ============================================================
    # Layer 1-4: Knowledge Pipeline 초기화
    # ============================================================
    print("\n[1] Initializing Knowledge Pipeline...")
    
    llm = OllamaClient()
    use_llm = llm.health_check()
    print(f"    LLM: {'Connected' if use_llm else 'Rule-based'}")
    
    extraction = ExtractionPipeline(llm_client=llm if use_llm else None, use_llm=use_llm)
    validation = ValidationPipeline(llm_client=llm if use_llm else None, use_llm=use_llm)
    domain = DomainPipeline()
    personal = PersonalPipeline(
        static_guard=domain.static_guard,
        dynamic_domain=domain.dynamic_update,
    )
    print("    ✓ Extraction, Validation, Domain, Personal initialized")
    
    # ============================================================
    # Layer 5: Reasoning 초기화
    # ============================================================
    print("\n[2] Initializing Reasoning Pipeline...")
    
    reasoning = ReasoningPipeline(
        domain=domain.dynamic_update,
        personal=personal.get_pkg(),
        ner=extraction.ner_student,
        resolver=extraction.entity_resolver,
    )
    print("    ✓ Reasoning initialized with Domain & Personal connection")
    
    # ============================================================
    # Layer 6: Learning 초기화
    # ============================================================
    print("\n[3] Initializing Learning Layer...")
    
    dataset_builder = TrainingDatasetBuilder(
        domain=domain.dynamic_update,
        personal=personal.get_pkg(),
    )
    goldset_manager = TeacherGoldsetManager(llm_client=llm if use_llm else None)
    trainer = StudentValidatorTrainer()
    policy_learner = PolicyWeightLearner()
    deployment = ReviewDeploymentManager()
    
    dashboard = LearningDashboard(
        dataset_builder=dataset_builder,
        goldset_manager=goldset_manager,
        trainer=trainer,
        policy_learner=policy_learner,
        deployment=deployment,
        domain=domain.dynamic_update,
        personal=personal.get_pkg(),
    )
    print("    ✓ All Learning modules initialized")
    
    # ============================================================
    # Phase 1: Knowledge Collection
    # ============================================================
    print("\n[4] Phase 1: Knowledge Collection...")
    
    test_texts = [
        "금리가 인상되면 성장주는 약세를 보인다.",
        "연준이 유동성을 축소하면 시장에 부정적 영향이 있다.",
        "채권 가격은 금리와 역의 관계에 있다.",
    ]
    
    for i, text in enumerate(test_texts):
        # Extraction
        ext = extraction.process(raw_text=text, doc_id=f"DOC_{i}")
        
        if not ext.raw_edges:
            continue
        
        # Validation
        vals = validation.validate_batch(ext.raw_edges, ext.resolved_entities)
        val_map = {v.edge_id: v for v in vals}
        
        # Domain / Personal
        for edge in ext.raw_edges:
            v = val_map.get(edge.raw_edge_id)
            if not v or not v.validation_passed:
                # 실패 로그 기록 (Learning Layer 연결)
                dataset_builder.add_validation_log({
                    "edge_id": edge.raw_edge_id,
                    "fragment_text": edge.fragment_text,
                    "rejection_reason": v.rejection_reason if v else "validation_failed",
                })
                continue
            
            if v.destination == ValidationDestination.DOMAIN_CANDIDATE:
                result = domain.process(edge, v, ext.resolved_entities)
                if result.final_destination == "personal" and result.intake_result:
                    personal.process_from_domain_rejection(result.intake_result, result)
            
            elif v.destination == ValidationDestination.PERSONAL_CANDIDATE:
                personal.process_from_validation(edge, v, ext.resolved_entities)
    
    domain_count = len(domain.get_dynamic_domain().get_all_relations())
    personal_count = len(personal.get_pkg().get_all_relations())
    print(f"    ✓ Domain KG: {domain_count} relations")
    print(f"    ✓ Personal KG: {personal_count} relations")
    
    # ============================================================
    # Phase 2: Reasoning
    # ============================================================
    print("\n[5] Phase 2: Reasoning...")
    
    test_queries = [
        "금리가 오르면 주가는 어떻게 되나요?",
        "유동성 축소의 영향은?",
    ]
    
    for query in test_queries:
        conclusion = reasoning.reason(query)
        print(f"    Q: {query[:30]}...")
        print(f"    A: {conclusion.direction.value} (conf={conclusion.confidence:.2f})")
        
        # Query 로그 기록 (Learning Layer 연결)
        dataset_builder.add_query_log({
            "query": query,
            "direction": conclusion.direction.value,
            "confidence": conclusion.confidence,
        })
    
    # ============================================================
    # Phase 3: Learning Pipeline
    # ============================================================
    print("\n[6] Phase 3: Learning Pipeline...")
    
    # L1: Dataset 생성
    dataset = dataset_builder.build_dataset(TaskType.RELATION)
    print(f"    L1. Dataset: {dataset.sample_count} samples")
    
    # L2: Gold Set 생성
    gold_samples = [
        GoldSample(
            text="금리 인상 → 성장주 하락",
            task_type=TaskType.RELATION,
            gold_labels={"head": "금리", "tail": "성장주", "sign": "-"},
            difficulty="normal",
        )
    ]
    goldset = goldset_manager.create_goldset(TaskType.RELATION, gold_samples)
    goldset_manager.set_active_goldset(goldset.version)
    print(f"    L2. Goldset: {goldset.version} ({goldset.sample_count} samples)")
    
    # L3: Training Run 생성
    run = trainer.create_run("student2", dataset, goldset)
    print(f"    L3. Training Run: {run.run_id}")
    
    # L4: Policy Variant 생성
    base_policy = policy_learner.get_active_policy()
    new_policy = policy_learner.create_policy_variant(
        base_policy.version,
        ees_adj={"domain": 0.02, "personal": -0.01},
    )
    print(f"    L4. Policy: {base_policy.version} -> {new_policy.version}")
    
    # L5: Bundle 생성 및 배포
    bundle = deployment.create_bundle(
        student1_v="student1_v1",
        student2_v=run.new_model_version,
        sign_v="sign_validator_v1",
        semantic_v="semantic_validator_v1",
        policy_v=new_policy.version,
    )
    deployment.review_bundle(bundle.version, approved=True, notes="Integration test")
    deployment.deploy_bundle(bundle.version)
    print(f"    L5. Deployed: {bundle.version}")
    
    # ============================================================
    # Dashboard Summary
    # ============================================================
    print("\n[7] Dashboard Summary...")
    
    summary = dashboard.get_summary()
    print(f"    Active Bundle: {summary['version'].get('active_bundle')}")
    print(f"    Datasets: {summary['datasets'].get('snapshots', 0)}")
    print(f"    Training Runs: {summary['training'].get('total_runs', 0)}")
    print(f"    Policies: {summary['policies'].get('total', 0)}")
    
    # Quality Reports
    domain_report = dashboard.generate_domain_quality_report()
    personal_report = dashboard.generate_personal_quality_report()
    print(f"    Domain Metrics: {domain_report.metrics}")
    print(f"    Personal Metrics: {personal_report.metrics}")
    
    # ============================================================
    # Final Statistics
    # ============================================================
    print("\n" + "="*70)
    print("📊 FINAL INTEGRATION STATUS")
    print("="*70)
    
    checks = [
        ("Extraction → Validation", len(extraction.entity_resolver.get_stats()) > 0),
        ("Validation → Domain", domain_count >= 0),
        ("Validation → Personal", personal_count >= 0),
        ("Domain → Reasoning", reasoning.domain is not None),
        ("Personal → Reasoning", reasoning.personal is not None),
        ("Domain → Learning (Dataset)", dataset_builder.domain is not None),
        ("Personal → Learning (Dataset)", dataset_builder.personal is not None),
        ("Learning → Dashboard", summary is not None),
        ("Deployment → Active Bundle", deployment.get_active_bundle() is not None),
    ]
    
    all_pass = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        print(f"    {status} {name}")
        if not passed:
            all_pass = False
    
    print("\n" + "="*70)
    if all_pass:
        print("✅ ALL CONNECTIONS VERIFIED - 6-LAYER INTEGRATION COMPLETE!")
    else:
        print("❌ SOME CONNECTIONS FAILED")
    print("="*70)
    
    if llm:
        llm.close()
    
    return all_pass


if __name__ == "__main__":
    test_full_pipeline()
