from __future__ import annotations

from httpx import AsyncClient


async def test_langgraph_images_are_served_via_api_prefix(client: AsyncClient) -> None:
    api_response = await client.get("/api/langgraph-images/")
    direct_response = await client.get("/langgraph-images/")

    assert api_response.status_code == 200
    assert direct_response.status_code == 200
    assert "LangGraph Images" in api_response.text
    assert "chat_graph.png" in api_response.text
