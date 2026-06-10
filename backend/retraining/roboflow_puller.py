"""
retraining/roboflow_puller.py

Pulls the latest annotated dataset from Roboflow
when retraining is triggered.
"""

from __future__ import annotations

import os
import pathlib
from loguru import logger


ROBOFLOW_API_KEY  = os.getenv("ROBOFLOW_API_KEY",  "")
ROBOFLOW_WORKSPACE= os.getenv("ROBOFLOW_WORKSPACE", "")
ROBOFLOW_PROJECT  = os.getenv("ROBOFLOW_PROJECT",   "")
ROBOFLOW_VERSION  = int(os.getenv("ROBOFLOW_VERSION", "3"))
DOWNLOAD_DIR      = pathlib.Path("data/retrain_raw")


def pull_latest_dataset(version: int | None = None) -> pathlib.Path:
    """
    Pull latest Roboflow dataset version for retraining.

    Args:
        version: Specific version to pull. Defaults to ROBOFLOW_VERSION env var.

    Returns:
        Path to downloaded dataset root.

    Raises:
        EnvironmentError: If Roboflow credentials not configured.
        RuntimeError: If download fails.
    """
    if not all([ROBOFLOW_API_KEY, ROBOFLOW_WORKSPACE, ROBOFLOW_PROJECT]):
        raise EnvironmentError(
            "Roboflow credentials not set. "
            "Configure ROBOFLOW_API_KEY, ROBOFLOW_WORKSPACE, "
            "ROBOFLOW_PROJECT in .env"
        )

    from roboflow import Roboflow

    v   = version or ROBOFLOW_VERSION
    rf  = Roboflow(api_key=ROBOFLOW_API_KEY)
    prj = rf.workspace(ROBOFLOW_WORKSPACE).project(ROBOFLOW_PROJECT)

    logger.info(
        "Pulling Roboflow dataset | workspace={} | project={} | version={}",
        ROBOFLOW_WORKSPACE, ROBOFLOW_PROJECT, v,
    )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dataset = prj.version(v).download(
        model_format = "yolov8",
        location     = str(DOWNLOAD_DIR),
        overwrite    = True,
    )

    logger.info("Dataset downloaded → {}", dataset.location)
    return pathlib.Path(dataset.location)