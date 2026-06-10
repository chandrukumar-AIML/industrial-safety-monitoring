"""
cameras/camera_process.py

Per-camera inference process.
Runs in a separate OS process — complete isolation from other cameras.

Architecture:
  MainProcess → spawns CameraProcess per camera
  CameraProcess:
    - Opens RTSP stream via cv2.VideoCapture
    - Runs PPEDetector + ByteTracker
    - Puts FrameResult into multiprocessing.Queue
    - Handles reconnection with exponential backoff
    - Reports health via status queue
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import time
from dataclasses import dataclass, field
from typing      import Optional

_RECONNECT_BASE   = float(os.getenv("CAMERA_RECONNECT_BASE_DELAY_S", "2.0"))
_RECONNECT_MAX    = float(os.getenv("CAMERA_RECONNECT_MAX_DELAY_S",  "60.0"))
_MAX_ATTEMPTS     = int  (os.getenv("CAMERA_RECONNECT_MAX_ATTEMPTS", "5"))
_QUEUE_SIZE       = int  (os.getenv("CAMERA_FRAME_QUEUE_SIZE",       "8"))


@dataclass
class CameraHealthEvent:
    """Status event from camera process to manager."""
    camera_id     : str
    event_type    : str    # connected | disconnected | error | frame
    fps           : float  = 0.0
    error_msg     : str    = ""
    timestamp     : float  = field(default_factory=time.time)


@dataclass
class CameraFrameResult:
    """Lightweight frame result from camera process."""
    camera_id        : str
    frame_idx        : int
    timestamp        : float
    jpeg_bytes       : bytes          # JPEG-encoded annotated frame
    violation_count  : int
    detection_count  : int
    active_tracks    : int
    fps              : float
    violations       : list           # serialisable violation dicts


def _camera_worker(
    camera_id    : str,
    camera_name  : str,
    rtsp_url     : str,
    zone_id      : Optional[str],
    model_path   : str,
    device       : str,
    frame_queue  : mp.Queue,
    health_queue : mp.Queue,
    stop_event   : mp.Event,
    frame_skip   : int = 2,
) -> None:
    """
    Main camera worker function — runs in child process.

    Responsible for:
      1. Opening RTSP stream
      2. Running PPE inference
      3. Pushing results to frame_queue
      4. Reconnecting on failure
      5. Reporting health via health_queue

    This function never raises — all errors are caught and reported.
    """
    # Import inside worker process (each process gets own memory space)
    import cv2
    import numpy as np
    from loguru import logger

    logger.info("Camera process started | id={} | url={}", camera_id, rtsp_url)

    def _put_health(event_type: str, fps: float = 0.0, error: str = "") -> None:
        try:
            health_queue.put_nowait(CameraHealthEvent(
                camera_id  = camera_id,
                event_type = event_type,
                fps        = fps,
                error_msg  = error,
            ))
        except Exception:
            pass

    # Load detector inside process (separate from main process)
    try:
        from inference.detector import PPEDetector
        from inference.tracker  import ByteTracker

        detector = PPEDetector(
            model_path     = model_path,
            device         = device,
            conf_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35")),
            iou_threshold  = float(os.getenv("IOU_THRESHOLD",        "0.45")),
        )
        class_names = detector.class_names
        tracker     = ByteTracker(class_names=class_names)

    except Exception as exc:
        _put_health("error", error=f"Model load failed: {exc}")
        logger.error("Camera {}: model load failed: {}", camera_id, exc)
        return

    reconnect_attempts = 0
    reconnect_delay    = _RECONNECT_BASE

    while not stop_event.is_set():
        cap = None
        try:
            # Open stream
            logger.info("Camera {}: connecting to {}", camera_id, rtsp_url)
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)

            if not cap.isOpened():
                raise ConnectionError(f"Cannot open: {rtsp_url}")

            reconnect_attempts = 0
            reconnect_delay    = _RECONNECT_BASE
            _put_health("connected", fps=0.0)
            logger.info("Camera {}: connected", camera_id)

            frame_idx   = 0
            fps_times   : list = []
            stats_frames = 0
            stats_viols  = 0
            stats_dets   = 0
            last_stats_t = time.monotonic()

            while not stop_event.is_set():
                t0 = time.perf_counter()

                ret, frame = cap.read()
                if not ret or frame is None:
                    raise ConnectionError("Stream read failed — camera disconnected")

                frame_idx += 1
                if frame_idx % frame_skip != 0:
                    continue

                # ── Inference ─────────────────────────────────
                try:
                    yolo_result = detector.predict(frame)
                    h, w        = frame.shape[:2]
                    tracked     = tracker.update(
                        yolo_result,
                        frame_idx = frame_idx,
                        frame_wh  = (w, h),
                    )
                    violations  = [d for d in tracked if d.is_violation]

                except Exception as exc:
                    logger.warning("Camera {}: inference error: {}", camera_id, exc)
                    continue

                # ── FPS calculation ───────────────────────────
                elapsed = time.perf_counter() - t0
                fps_times.append(elapsed)
                if len(fps_times) > 30:
                    fps_times.pop(0)
                fps = 1.0 / (sum(fps_times) / len(fps_times) + 1e-6)

                # ── Annotate frame ────────────────────────────
                annotated = _annotate_frame(frame, tracked, camera_id, fps)

                # ── JPEG encode ───────────────────────────────
                _, jpeg_buf = cv2.imencode(
                    ".jpg", annotated,
                    [cv2.IMWRITE_JPEG_QUALITY, 75],
                )
                jpeg_bytes = jpeg_buf.tobytes()

                # ── Build result ──────────────────────────────
                result = CameraFrameResult(
                    camera_id       = camera_id,
                    frame_idx       = frame_idx,
                    timestamp       = time.time(),
                    jpeg_bytes      = jpeg_bytes,
                    violation_count = len(violations),
                    detection_count = len(tracked),
                    active_tracks   = len(tracked),
                    fps             = round(fps, 1),
                    violations      = [
                        {
                            "track_id"  : d.track_id,
                            "class_name": d.class_name,
                            "confidence": d.confidence,
                            "zone_id"   : d.zone_id,
                            "bbox_xyxy" : d.bbox_xyxy,
                        }
                        for d in violations
                    ],
                )

                # ── Put on queue (drop oldest if full) ────────
                try:
                    frame_queue.put_nowait(result)
                except queue.Full:
                    try:
                        frame_queue.get_nowait()
                        frame_queue.put_nowait(result)
                    except Exception:
                        pass

                # ── Accumulate stats ──────────────────────────
                stats_frames += 1
                stats_dets   += len(tracked)
                stats_viols  += len(violations)

                # Health heartbeat every 5 seconds
                now = time.monotonic()
                if now - last_stats_t > 5.0:
                    _put_health("frame", fps=fps)
                    last_stats_t = now

        except ConnectionError as exc:
            reconnect_attempts += 1
            error_msg = str(exc)
            _put_health("disconnected", error=error_msg)
            logger.warning(
                "Camera {}: disconnected (attempt {}/{}) — {}",
                camera_id, reconnect_attempts, _MAX_ATTEMPTS, error_msg,
            )

            if reconnect_attempts >= _MAX_ATTEMPTS:
                _put_health("error", error=f"Max reconnect attempts reached: {error_msg}")
                logger.error(
                    "Camera {}: giving up after {} attempts",
                    camera_id, _MAX_ATTEMPTS,
                )
                break

            # Exponential backoff
            time.sleep(min(reconnect_delay, _RECONNECT_MAX))
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX)

        except Exception as exc:
            _put_health("error", error=str(exc))
            logger.exception("Camera {}: unexpected error", camera_id)
            time.sleep(_RECONNECT_BASE)

        finally:
            if cap is not None:
                cap.release()

    logger.info("Camera process stopped | id={}", camera_id)


def _annotate_frame(
    frame     : "np.ndarray",
    tracked   : list,
    camera_id : str,
    fps       : float,
) -> "np.ndarray":
    """Minimal annotation for multi-camera mode."""
    import cv2

    annotated = frame.copy()
    h, w      = annotated.shape[:2]

    for det in tracked:
        x1, y1, x2, y2 = [int(v) for v in det.bbox_xyxy]
        color = (0, 80, 220) if det.is_violation else (46, 204, 113)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"{det.class_name} ID:{det.track_id}"
        cv2.putText(
            annotated, label,
            (x1, max(y1 - 4, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4, color, 1, cv2.LINE_AA,
        )

    violations = sum(1 for d in tracked if d.is_violation)
    cv2.putText(
        annotated,
        f"{camera_id} | FPS:{fps:.0f} | V:{violations}",
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5, (255, 255, 255), 2, cv2.LINE_AA,
    )
    return annotated


class CameraProcess:
    """
    Manages one camera's inference subprocess.

    Start/stop lifecycle controlled by StreamManager.
    Frame results pulled via frame_queue.
    Health events pulled via health_queue.
    """

    def __init__(
        self,
        camera_id  : str,
        camera_name: str,
        rtsp_url   : str,
        zone_id    : Optional[str],
        model_path : str,
        device     : str = "cpu",
        frame_skip : int = 2,
    ) -> None:
        self.camera_id   = camera_id
        self.camera_name = camera_name
        self.rtsp_url    = rtsp_url

        ctx = mp.get_context("spawn")
        self.frame_queue  = ctx.Queue(maxsize=_QUEUE_SIZE)
        self.health_queue = ctx.Queue(maxsize=50)
        self._stop_event  = ctx.Event()
        self._process     : Optional[mp.Process] = None

        self._start_kwargs = dict(
            camera_id    = camera_id,
            camera_name  = camera_name,
            rtsp_url     = rtsp_url,
            zone_id      = zone_id,
            model_path   = model_path,
            device       = device,
            frame_queue  = self.frame_queue,
            health_queue = self.health_queue,
            stop_event   = self._stop_event,
            frame_skip   = frame_skip,
        )

    def start(self) -> None:
        """Spawn the camera subprocess."""
        self._stop_event.clear()
        self._process = mp.Process(
            target = _camera_worker,
            kwargs = self._start_kwargs,
            name   = f"camera-{self.camera_id}",
            daemon = True,
        )
        self._process.start()

    def stop(self) -> None:
        """Signal subprocess to stop and wait for it."""
        self._stop_event.set()
        if self._process and self._process.is_alive():
            self._process.join(timeout=5.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2.0)

    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def drain_frames(self) -> list:
        """Non-blocking drain of available frames."""
        frames = []
        while True:
            try:
                frames.append(self.frame_queue.get_nowait())
            except queue.Empty:
                break
        return frames

    def drain_health(self) -> list:
        """Non-blocking drain of health events."""
        events = []
        while True:
            try:
                events.append(self.health_queue.get_nowait())
            except queue.Empty:
                break
        return events