from typing import Any


async def post_chat_completion(
    *,
    base_url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None,
    timeout,
):
    from ....clients import omlx as omlx_client

    async with omlx_client.httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
    return resp
