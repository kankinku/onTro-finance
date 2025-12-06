from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List
from src.schemas.base_models import ScenarioInput, InferredOutcome, Fragment
from src.api.market_data import MarketDataProvider
from src.pipeline.m1_analyzer import InputAnalyzer
from src.pipeline.m2_entity_resolver import EntityResolver
from src.pipeline.m3_relation import RelationConstructor
from src.reasoning.simulator import ScenarioSimulator
from src.core.knowledge_graph import KnowledgeGraph
from src.core.database import db
from src.core.logger import logger
from networkx.readwrite import json_graph

api_router = APIRouter()

# Initialize Global Graph (will load from disk on validity)
global_kg = KnowledgeGraph()
# Initialize Global Market Data Provider
global_market = MarketDataProvider()

@api_router.get("/graph")
async def get_graph_data():
    """
    Returns the entire Knowledge Graph structure for visualization.
    Format: { "nodes": [...], "links": [...] }
    """
    logger.info("[API] /graph request received.")
    data = json_graph.node_link_data(global_kg.graph)
    return data

@api_router.get("/market/dashboard")
async def get_market_dashboard():
    """
    Returns summary cards for top-level dashboard (TGA, Reserves, etc.)
    """
    # Use global Singleton
    return global_market.get_dashboard_summary()

@api_router.get("/market/history")
async def get_market_history(source: str, ticker: str):
    """
    Returns historical data for a specific ticker provided by MarketDataProvider.
    """
    history = global_market.get_metric_history(source, ticker)
    if not history:
        return []
    return history

@api_router.get("/market/analyze-metric")
async def analyze_market_metric(source: str, ticker: str, title: str):
    """
    Triggers an on-demand LLM analysis for a specific metric.
    """
    logger.info(f"[API] Analyzing metric: {title} ({ticker})")
    report = global_market.analyze_metric_detail(source, ticker, title)
    return {"report": report}

@api_router.post("/learn", response_model=List[Fragment])
async def learn_scenario(input_data: ScenarioInput, background_tasks: BackgroundTasks):
    logger.info(f"[API] /learn request received. Length: {len(input_data.text)}")
    
    # 1. M1 Analysis (Ollama)
    analyzer = InputAnalyzer()
    fragments = analyzer.analyze(input_data.text)
    
    if not fragments:
        logger.warning("[API] No fragments extracted.")
        return []

    # 2. M2 Resolution
    resolver = EntityResolver()
    resolution_map = resolver.resolve(fragments)
    
    # 3. M3 Relation Construction
    constructor = RelationConstructor()
    relations = constructor.construct(fragments, resolution_map)
    
    # 4. Save
    background_tasks.add_task(_save_to_knowledge_base, resolution_map, relations)
    
    # 5. [New] Auto-Discover Data Sources (If keywords found)
    background_tasks.add_task(_auto_discover_data_sources, input_data.text)
    
    return fragments

@api_router.post("/infer", response_model=InferredOutcome)
async def infer_scenario(target_term_id: str):
    logger.info(f"[API] /infer request for {target_term_id}")
    
    simulator = ScenarioSimulator(global_kg)
    result = simulator.simulate([target_term_id])
    
    return result

def _save_to_knowledge_base(resolution_map, relations):
    from src.schemas.base_models import Term
    
    try:
        for surface, res in resolution_map.items():
            term_obj = Term(term_id=res.entity_id, label=surface, aliases=[surface])
            # db.merge_term(term_obj) # Disabled (Mock)
            global_kg.add_term(term_obj)

        for rel in relations:
            # db.create_relation(rel) # Disabled (Mock)
            global_kg.add_relation(rel)
            
        logger.info(f"[Worker] Saved {len(relations)} relations to Graph.")
    except Exception as e:
        logger.error(f"[Worker] Failed to save: {e}")

def _auto_discover_data_sources(text: str):
    """
    Analyzes input text for potential economic indicators or assets.
    If found, tries to find them in FRED and register them.
    """
    logger.info("[Auto-Discovery] Scanning text for data sources...")
    import requests
    from src.core.config import settings

    # 1. Ask LLM to extract potential assets
    prompt = f"""
    Extract any financial asset names or economic indicators from the text.
    Return ONLY a JSON list of strings (English preferred for search).
    If none, return [].
    
    Text: "{text}"
    
    Example Output: ["Bitcoin", "Unemployment Rate", "Gold"]
    """
    
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0}
            },
            timeout=10
        )
        if resp.status_code == 200:
            import json
            res_json = resp.json().get("response", "[]")
            keywords = json.loads(res_json)
            
            if isinstance(keywords, dict) and "assets" in keywords: # Handle potential { "assets": [...] } format
                 keywords = keywords["assets"]
            
            logger.info(f"[Auto-Discovery] Extracted keywords: {keywords}")
            
            for kw in keywords:
                # Try to register
                if isinstance(kw, str) and len(kw) > 2:
                    global_market.search_and_register_ticker(kw)
        else:
            logger.warning("Ollama failed for discovery.")
            
    except Exception as e:
        logger.error(f"[Auto-Discovery] Error: {e}")
