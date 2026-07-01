import asyncio

from material_agent.utils.async_tools import run_coro_sync


async def _double(value: int) -> int:
    await asyncio.sleep(0)
    return value * 2


def test_run_coro_sync_outside_event_loop():
    assert run_coro_sync(_double(3)) == 6


def test_run_coro_sync_inside_running_event_loop():
    async def _run():
        return run_coro_sync(_double(5))

    assert asyncio.run(_run()) == 10
