"""
Graph Routes
지식 그래프 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from src.services.kg_service import kg_service

router = APIRouter()


@router.get("/data")
async def get_graph_data():
    """
    전체 Knowledge Graph 구조 반환 (시각화용)
    
    Returns:
        { "nodes": [...], "links": [...] }
    """
    try:
        data = kg_service.get_graph_data()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph data fetch failed: {e}")


@router.get("/stats")
async def get_graph_stats():
    """
    그래프 통계 정보 반환
    """
    return {
        "node_count": kg_service.get_node_count(),
        "edge_count": kg_service.get_edge_count()
    }
