import base64


def generate_vision_sync(
    *,
    base_url: str,
    model: str,
    prompt: str,
    jpeg_bytes: bytes,
    temperature: float,
    timeout: float | int,
) -> str:
    from ....clients import ollama as ollama_client

    img_b64 = base64.b64encode(jpeg_bytes).decode()
    resp = ollama_client.requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def generate_text_sync(*, base_url: str, model: str, prompt: str, timeout: float | int) -> str:
    from ....clients import ollama as ollama_client

    resp = ollama_client.requests.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


async def generate_vision_async(
    *,
    base_url: str,
    model: str,
    prompt: str,
    jpeg_bytes: bytes,
    temperature: float,
    timeout,
) -> str:
    from ....clients import ollama as ollama_client

    img_b64 = base64.b64encode(jpeg_bytes).decode()
    async with ollama_client.httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
    resp.raise_for_status()
    return resp.json()["response"]


async def generate_text_async(*, base_url: str, model: str, prompt: str, timeout) -> str:
    from ....clients import ollama as ollama_client

    async with ollama_client.httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
    resp.raise_for_status()
    return resp.json()["response"].strip()
