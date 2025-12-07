import sys
import os
import asyncio

# Add project root to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.schemas.base_models import Fragment
from src.pipeline.m3_relation import RelationConstructor
from src.core.knowledge_graph import KnowledgeGraph
from src.reasoning.simulator import ScenarioSimulator
from src.schemas.ontology import RelationKind

async def run_test():
    print("🧪 [Test] Starting Strong Ontology Pipeline Test...")
    
    # --- 1. M1 Mocking (Fragment Generation) ---
    print("\n[Step 1] M1 Mocking: Creating synthetic fragments...")
    
    # Scenario: Interest Rate -> Liquidity -> Asset Price
    fragments = [
        Fragment(
            fragment_id="F01",
            text="금리 인상은 시장 유동성을 급격히 위축시킨다.",
            fact="금리 인상",
            mechanism_text="긴축 효과",
            outcome_text="유동성 축소",
            term_candidates=["기준 금리", "시장 유동성"],
            # Strong Ontology Fields
            relation_kind="PROPORTIONAL",
            sign=-1,          # 역의 관계 (금리 오르면 유동성 내림)
            strength=0.9,     # 매우 강함
            lag_days=0
        ),
        Fragment(
            fragment_id="F02",
            text="시장 유동성은 자산 가격과 정비례한다.",
            fact="유동성과 자산가격 동조화",
            mechanism_text="자금 유입 효과",
            outcome_text="가격 변동",
            term_candidates=["시장 유동성", "자산 가격"],
            # Strong Ontology Fields
            relation_kind="PROPORTIONAL", # 정비례
            sign=1,           # 정의 관계 (유동성 오르면 자산도 오름)
            strength=0.8,
            lag_days=7
        )
    ]
    print(f"   -> Generated {len(fragments)} fragments.")

    # --- 2. M3 Relation Construction ---
    print("\n[Step 2] M3 Relation Construction...")
    
    # Mock Entity Resolver Map (Simple identity map)
    class MockEntity:
        def __init__(self, name): self.entity_id = f"NODE_{name}"; self.surface_form = name
    
    resolution_map = {
        "기준 금리": MockEntity("INTEREST_RATE"),
        "시장 유동성": MockEntity("MARKET_LIQUIDITY"),
        "자산 가격": MockEntity("ASSET_PRICE")
    }
    
    constructor = RelationConstructor()
    relations = constructor.construct(fragments, resolution_map)
    
    print(f"   -> Constructed {len(relations)} relations.")
    for r in relations:
        print(f"      🔗 {r.subject_id} --(sign={r.sign}, str={r.strength})--> {r.object_id}")

    # --- 3. Knowledge Graph Loading ---
    print("\n[Step 3] Loading into Knowledge Graph...")
    kg = KnowledgeGraph()
    # Reset for test
    import networkx as nx
    kg.graph = nx.DiGraph() 
    
    for r in relations:
        kg.add_relation(r)
    print(f"   -> KG Nodes: {kg.graph.number_of_nodes()}, Edges: {kg.graph.number_of_edges()}")

    # --- 4. Simulation Execution ---
    print("\n[Step 4] Running Causal Simulation...")
    simulator = ScenarioSimulator(kg)
    
    # Mock Market Data Provider to avoid API calls
    simulator.market_data.get_market_indicator = lambda x: None # No real data context
    
    # Trigger: Interest Rate Hike
    trigger = "NODE_INTEREST_RATE"
    result = simulator.simulate([trigger])
    
    print("\n📊 [Simulation Result]")
    print(f"   Confidence: {result.confidence}")
    print("   Outcome Log:")
    for line in result.outcome_text:
        print(f"   {line}")

    # --- Validation ---
    print("\n[Step 5] Verification")
    # We expect ASSET_PRICE to decrease
    # Logic: Rate(+1) * Edge1(-1) * Edge2(+1) = -1 (Decrease)
    
    # Find outcome line for ASSET PRICE
    # It should look like: 🎯 **ASSET PRICE**: 감소/하락 ...
    
    found_outcome = False
    for line in result.outcome_text:
        if "ASSET PRICE" in line and ("감소" in line or "하락" in line):
            found_outcome = True
            print("   ✅ SUCCESS: 'ASSET PRICE' predicted to DECREASE correctly.")
            break
            
    if not found_outcome:
        print("   ❌ FAILURE: Prediction did not match expectation.")

if __name__ == "__main__":
    asyncio.run(run_test())
