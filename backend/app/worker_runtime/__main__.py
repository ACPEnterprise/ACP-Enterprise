import asyncio
import signal

from app.worker_runtime.config import WorkerRuntimeConfig
from app.worker_runtime.service import AuthenticatedWorkerRuntime


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    runtime = AuthenticatedWorkerRuntime.production(
        WorkerRuntimeConfig.from_environment()
    )
    await runtime.run(stop)


if __name__ == "__main__":
    asyncio.run(run())
