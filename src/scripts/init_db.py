import sys
import os
import networkx as nx
from networkx.readwrite import json_graph

# Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.config import settings
from src.schemas.base_models import Term, Relation, PredicateType
from src.core.knowledge_graph import KnowledgeGraph
from src.core.logger import logger

def init_db():
    """
    Initializes the Knowledge Graph with a rich set of financial domain terms and relations.
    WARNING: This will overwrite existing data.
    """
    print(f"Initializing database at {settings.PERSISTENCE_FILE}...")
    
    # 1. Initialize Graph Wrapper
    kg = KnowledgeGraph()
    # Clear existing graph
    kg.graph.clear()
    
    # 2. Define Initial Terms
    terms = [
        # Regulation
        Term(term_id="TERM_SLR_RULE", label="SLR 규제", aliases=["SLR", "Supplementary Leverage Ratio"]),
        Term(term_id="TERM_BASEL3", label="바젤 III", aliases=["Basel 3", "바젤III"]),
        Term(term_id="TERM_LCR", label="LCR", aliases=["Liquidity Coverage Ratio", "유동성 커버리지 비율"]),
        Term(term_id="TERM_BIS_RATIO", label="BIS 비율", aliases=["BIS Ratio", "BIS"]),

        # Macro Indicators
        Term(term_id="TERM_BASE_RATE", label="기준금리", aliases=["Policy Rate", "Base Rate"]),
        Term(term_id="TERM_INFLATION", label="인플레이션", aliases=["물가상승", "Inflation Rate"]),
        Term(term_id="TERM_EXCHANGE_RATE", label="환율", aliases=["FX Rate", "원달러 환율"]),
        Term(term_id="TERM_TREASURY_YIELD", label="국채 금리", aliases=["Treasury Yield", "국채 수익률"]),
        Term(term_id="TERM_LIQUIDITY", label="유동성", aliases=["Market Liquidity", "자금 사정"]),
        
        # Market & Risk
        Term(term_id="TERM_CREDIT_SPREAD", label="신용 스프레드", aliases=["회사채 스프레드", "Credit Spread"]),
        Term(term_id="TERM_ASSET_PRICE", label="자산 가격", aliases=["주가", "부동산 가격"]),
        
        # Financial Capacity/Metrics
        Term(term_id="TERM_BALANCE_SHEET_CAP", label="대차대조표", aliases=["B/S", "대차대조표 여력"]),
        Term(term_id="TERM_TREASURY_DEMAND", label="국채 수요", aliases=["UST Demand", "국채 매수"]),
        Term(term_id="TERM_TREASURY_BUYING_POWER", label="국채 매수 여력", aliases=[]),
        
        # Assets
        Term(term_id="TERM_UST", label="미국채", aliases=["UST", "U.S. Treasury"]),
        Term(term_id="TERM_CORP_BOND", label="회사채", aliases=["Corporate Bond"]),
        
        # Participants
        Term(term_id="NODE_CENTRAL_BANK", label="중앙은행", aliases=["Fed", "BOK", "한국은행"]),
        Term(term_id="NODE_COMMERCIAL_BANK", label="시중은행", aliases=["Commercial Bank", "은행권"]),
        Term(term_id="NODE_HEDGE_FUND", label="헤지펀드", aliases=["Hedge Fund"]),
    ]
    
    for term in terms:
        kg.add_term(term)
        print(f"Added Term: {term.label}")

    # 3. Define Initial Relations
    relations = [
        # Regulation -> Bank Capacity
        Relation(rel_id="REL_SLR_BS", subject_id="TERM_SLR_RULE", object_id="TERM_BALANCE_SHEET_CAP", predicate=PredicateType.DECREASES, conditions={"context": "Regulation"}),
        
        # Capacity -> Market Action
        Relation(rel_id="REL_BS_BUYPOWER", subject_id="TERM_BALANCE_SHEET_CAP", object_id="TERM_TREASURY_BUYING_POWER", predicate=PredicateType.INCREASES, conditions={"context": "Mechanism"}),
        Relation(rel_id="REL_BUYPOWER_DEMAND", subject_id="TERM_TREASURY_BUYING_POWER", object_id="TERM_TREASURY_DEMAND", predicate=PredicateType.INCREASES, conditions={"context": "Mechanism"}),
        
        # Central Bank Policy
        Relation(rel_id="REL_CB_RATE", subject_id="NODE_CENTRAL_BANK", object_id="TERM_BASE_RATE", predicate=PredicateType.INCREASES, conditions={"context": "Policy"}),
        
        # Macroecomics (Taylor Ruleish)
        Relation(rel_id="REL_INFLATION_RATE", subject_id="TERM_INFLATION", object_id="TERM_BASE_RATE", predicate=PredicateType.INCREASES, conditions={"context": "Taylor Rule"}),
        
        # Rates -> Yields
        Relation(rel_id="REL_RATE_YIELD", subject_id="TERM_BASE_RATE", object_id="TERM_TREASURY_YIELD", predicate=PredicateType.INCREASES, conditions={"context": "Correlation"}),
        
        # Liquidity -> Assets
        Relation(rel_id="REL_LIQ_ASSET", subject_id="TERM_LIQUIDITY", object_id="TERM_ASSET_PRICE", predicate=PredicateType.INCREASES, conditions={"context": "Market"}),
        
        # Risk
        Relation(rel_id="REL_RISK_SPREAD", subject_id="TERM_INFLATION", object_id="TERM_CREDIT_SPREAD", predicate=PredicateType.INCREASES, conditions={"context": "Risk Off"}),
    ]
    
    for rel in relations:
        kg.add_relation(rel)
        print(f"Added Relation: {rel.subject_id} --[{rel.predicate}]--> {rel.object_id}")

    # 4. Save
    kg.save_to_disk()
    print("Database initialization complete.")

if __name__ == "__main__":
    confirm = input("This will reset the Knowledge Graph database. Continue? (y/n): ")
    if confirm.lower() == 'y':
        init_db()
    else:
        print("Aborted.")
