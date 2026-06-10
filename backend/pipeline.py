"""
backend/pipeline.py

Runs the long-lived OpenCV + ML inference pipeline in a dedicated worker
thread so FastAPI's event loop stays free to answer HTTP requests instantly.

Why the old architecture blocked:
- FastAPI startup imported and initialised heavy CV/ML components inline.
- Model loading and pipeline bootstrap happened before the app could finish
  startup, so a slow or wedged pipeline delayed the entire HTTP layer.
- Some routes reached directly into synchronous pipeline helpers; that work
  belonged on the pipeline side, not on the request loop.

Why this fixes it:
- The worker thread owns the inference lifecycle and its own asyncio loop.
- FastAPI startup only starts the worker thread and returns immediately.
- Request handlers talk to thread-safe shared state or proxy work back onto the
  worker thread, so the FastAPI event loop never runs CPU/GPU-heavy tasks.
"""

from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import Future
from typing import Any, Optional

from loguru import logger

from .database import AsyncSessionLocal
from .event_writer import start_event_writer
from .state import AppState


class PipelineRuntime:
    """Owns the background thread that runs video capture and model inference."""

    def __init__(
        self,
        *,
        model_path: str,
        video_source: str | int,
        device: str,
        conf_threshold: float,
        iou_threshold: float,
        frame_skip: int,
        shap_background_dir: str,
        app_state: AppState,
    ) -> None:
        self._model_path = model_path
        self._video_source = video_source
        self._device = device
        self._conf_threshold = conf_threshold
        self._iou_threshold = iou_threshold
        self._frame_skip = frame_skip
        self._shap_background_dir = shap_background_dir
        self._app_state = app_state

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()

    def start(self) -> None:
        """
        Start the pipeline worker without blocking FastAPI startup.

        The HTTP server can begin serving `/health` immediately while models load
        in the background.
        """
        if self._thread and self._thread.is_alive():
            logger.warning("PipelineRuntime.start() called while already running")
            return

        self._stop_event.clear()
        self._ready.clear()
        self._app_state.set_pipeline_status("starting")
        self._thread = threading.Thread(
            target=self._thread_main,
            name="pipeline-runtime",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 20.0) -> None:
        """Signal the worker thread to stop and wait for a clean shutdown."""
        self._stop_event.set()

        loop = self._loop
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(lambda: None)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Pipeline runtime thread did not stop within {}s", timeout)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run())
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            self._loop = None
            self._ready.clear()

    async def _run(self) -> None:
        from .inference.pipeline import InferencePipeline
        from .inference.explainer import SHAPExplainer

        pipeline: Optional[InferencePipeline] = None
        event_writer_task: Optional[asyncio.Task] = None
        shap_task: Optional[asyncio.Task] = None

        try:
            logger.info(
                "Pipeline worker booting in background thread | source={} | device={}",
                self._video_source,
                self._device,
            )

            pipeline = InferencePipeline(
                model_path=self._model_path,
                video_source=self._video_source,
                device=self._device,
                conf_threshold=self._conf_threshold,
                iou_threshold=self._iou_threshold,
                frame_skip=self._frame_skip,
            )
            self._app_state.set_pipeline(pipeline)

            await pipeline.start()
            event_writer_task = asyncio.create_task(
                start_event_writer(pipeline, self._app_state, AsyncSessionLocal),
                name="event_writer",
            )

            async def _init_shap() -> None:
                try:
                    loop = asyncio.get_running_loop()
                    explainer = await loop.run_in_executor(
                        None,
                        lambda: SHAPExplainer(
                            model_path=self._model_path,
                            background_dir=self._shap_background_dir,
                            n_background=50,
                            device=self._device,
                        ),
                    )
                    self._app_state.set_shap_explainer(explainer)
                    logger.info("SHAP explainer initialised")
                except Exception as exc:
                    logger.warning(
                        "SHAP explainer failed to init: {} — /shap endpoints disabled",
                        type(exc).__name__,
                    )

            shap_task = asyncio.create_task(_init_shap(), name="shap_init")
            self._app_state.set_pipeline_status("running")
            self._ready.set()
            logger.info("Pipeline worker running")

            while not self._stop_event.is_set():
                await asyncio.sleep(0.25)

        except FileNotFoundError:
            self._app_state.set_pipeline_status(
                "degraded",
                f"Model not found at {self._model_path}",
            )
            logger.warning(
                "Pipeline not started: model not found — API remains responsive in degraded mode"
            )
        except Exception as exc:
            self._app_state.set_pipeline_status(
                "degraded",
                f"{type(exc).__name__}: {exc}",
            )
            logger.exception("Pipeline worker crashed during startup")
        finally:
            if shap_task and not shap_task.done():
                shap_task.cancel()
                await asyncio.gather(shap_task, return_exceptions=True)

            if event_writer_task and not event_writer_task.done():
                event_writer_task.cancel()
                await asyncio.gather(event_writer_task, return_exceptions=True)

            if pipeline is not None:
                await pipeline.stop()

            self._app_state.set_pipeline(None)
            self._app_state.set_shap_explainer(None)
            self._app_state.set_latest_frame(None)

            status, error = self._app_state.get_pipeline_status()
            if status == "running":
                self._app_state.set_pipeline_status("stopped", error)

            logger.info("Pipeline worker stopped")

    def _submit(self, func, *args, **kwargs) -> Future:
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("Inference pipeline is not available")

        async def _invoke():
            return func(*args, **kwargs)

        return asyncio.run_coroutine_threadsafe(_invoke(), loop)

    async def call(self, func, *args, **kwargs):
        """Run synchronous pipeline-side work on the worker thread."""
        return await asyncio.wrap_future(self._submit(func, *args, **kwargs))

    async def get_heatmap_png_bytes(self) -> bytes:
        pipeline = self._app_state.get_pipeline()
        if pipeline is None:
            raise RuntimeError("Inference pipeline is not running")
        return await self.call(pipeline.heatmap.get_heatmap_png_bytes)

    async def get_heatmap_meta(self) -> dict[str, Any]:
        pipeline = self._app_state.get_pipeline()
        if pipeline is None:
            return {
                "frame_count": 0,
                "stats": {
                    "frame_count": 0,
                    "accumulator_max": 0.0,
                    "accumulator_mean": 0.0,
                    "zones_registered": 0,
                    "kernel_cache_size": 0,
                    "max_history_len": 0,
                },
                "zone_risks": [],
            }
        return await self.call(
            lambda: {
                "frame_count": pipeline.heatmap.stats.get("frame_count", 0),
                "stats": pipeline.heatmap.stats,
                "zone_risks": pipeline.heatmap.zone_risks_as_dict(),
            }
        )

    async def reset_heatmap(self) -> None:
        pipeline = self._app_state.get_pipeline()
        if pipeline is None:
            raise RuntimeError("Inference pipeline is not running")
        await self.call(pipeline.heatmap.reset)

    async def get_fire_heatmap_png_bytes(self) -> bytes:
        pipeline = self._app_state.get_pipeline()
        if pipeline is None or not hasattr(pipeline, "_fire_detector") or pipeline._fire_detector is None:
            return b""
        return await self.call(pipeline._fire_detector.heatmap.get_png_bytes)

    async def reset_fire_heatmap(self) -> bool:
        pipeline = self._app_state.get_pipeline()
        if pipeline is None or not hasattr(pipeline, "_fire_detector") or pipeline._fire_detector is None:
            return False
        await self.call(pipeline._fire_detector.heatmap.reset)
        return True


def parse_video_source(raw: str) -> str | int:
    """Preserve existing behaviour: numeric sources become webcam indices."""
    return int(raw) if raw.isdigit() else raw


def reload_enabled() -> bool:
    """Hot reload is explicit; never auto-enable it on Windows."""
    requested = os.getenv("UVICORN_RELOAD", "").strip().lower()
    if requested not in {"1", "true", "yes", "on"}:
        return False
    if os.name == "nt":
        logger.warning(
            "UVICORN_RELOAD requested on Windows, but reload is disabled to keep HTTP responsive."
        )
        return False
    return True
