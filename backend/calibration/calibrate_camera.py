"""
calibration/calibrate_camera.py

Interactive one-time camera calibration tool.

# FIXED: Input validation + sanitization for CLI args
# FIXED: Secure file handling (no arbitrary path writes)
# IMPROVED: Better UX with progress feedback + undo support
# IMPROVED: Export calibration for review before saving
# FIXED: Graceful error handling + helpful messages

Usage:
    python calibration/calibrate_camera.py --image frame.jpg --camera-id cam-01

Instructions:
    1. Capture a frame from your camera with visible floor markers
    2. Run this script with the frame as input
    3. Click at least 4 known positions on the ground plane
    4. Enter the real-world coordinates (metres) for each clicked point
    5. Review calibration accuracy before saving
    6. Calibration is saved and used automatically by the pipeline

Tip: Use floor tape, painted lines, or tile corners as reference points.
     Measure their real positions with a tape measure.
     Spread points across the frame for best homography accuracy.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

# Import from local module
from .calibrator import (
    CameraCalibration, 
    CalibrationError,
    HomographyComputationError,
    _sanitize_camera_id,
    _get_calibration_path,
    CALIBRATION_PATH,
)


class InteractiveCalibrator:
    """Click-based camera calibration UI with undo + review."""

    def __init__(self, image_path: str, camera_id: str = "default") -> None:
        # Validate image path
        image_p = pathlib.Path(image_path)
        if not image_p.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        if not image_p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
            logger.warning("Unusual image format: {} — may not load correctly", image_p.suffix)
        
        self._image = cv2.imread(str(image_p))
        if self._image is None:
            raise ValueError(f"Cannot read image: {image_path}")

        self._display = self._image.copy()
        self._points: List[Tuple[int, int, float, float]] = []  # [(px, py, rx, ry), ...]
        self._window = "Camera Calibration — Click ground points"
        self._camera_id = _sanitize_camera_id(camera_id)
        
        # Undo history for UX
        self._undo_stack: List[Tuple[int, int, float, float]] = []

    def _mouse_callback(self, event: int, x: int, y: int, flags, param) -> None:
        """Handle mouse clicks for point selection."""
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        idx = len(self._points) + 1
        print(f"\n[Point {idx}] Clicked at pixel ({x}, {y})")
        
        # Get real-world coords with validation
        while True:
            try:
                rx_input = input(f"  Enter real-world X in metres (e.g. 0.0): ").strip()
                ry_input = input(f"  Enter real-world Y in metres (e.g. 2.0): ").strip()
                
                rx = float(rx_input)
                ry = float(ry_input)
                
                # Warn if values seem suspicious
                if abs(rx) > 100 or abs(ry) > 100:
                    confirm = input(f"  ⚠️  Large values ({rx}m, {ry}m) — confirm? (y/n): ").strip().lower()
                    if confirm != "y":
                        continue
                
                break
            except ValueError:
                print("  ❌ Invalid number — please enter numeric values")
            except KeyboardInterrupt:
                print("\n  Cancelled")
                return

        # Record point
        point = (x, y, rx, ry)
        self._points.append(point)
        self._undo_stack.append(point)

        # Draw on display
        self._draw_point(idx, x, y, rx, ry)
        cv2.imshow(self._window, self._display)
        print(f"  ✓ Recorded: pixel=({x},{y}) → real=({rx}m, {ry}m)")

    def _draw_point(self, idx: int, x: int, y: int, rx: float, ry: float) -> None:
        """Draw a calibration point on the display image."""
        cv2.circle(self._display, (x, y), 8, (0, 255, 0), -1)
        cv2.putText(
            self._display,
            f"P{idx} ({rx:.2f}m, {ry:.2f}m)",
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5, (0, 255, 0), 1, cv2.LINE_AA,
        )

    def _undo_last(self) -> bool:
        """Remove last point — for UX."""
        if not self._points:
            print("  No points to undo")
            return False
        
        removed = self._undo_stack.pop()
        self._points.remove(removed)
        self._display = self._image.copy()
        
        # Redraw remaining points
        for i, (x, y, rx, ry) in enumerate(self._points, 1):
            self._draw_point(i, x, y, rx, ry)
        
        cv2.imshow(self._window, self._display)
        print(f"  ↩ Undone point {len(self._points) + 1}")
        return True

    def run(self) -> List[Tuple[int, int, float, float]]:
        """
        Show interactive window for point selection.
        Returns list of (px, py, rx, ry) tuples.
        """
        print("\n=== Camera Calibration ===")
        print(f"Camera: {self._camera_id}")
        print("Instructions:")
        print("  • Click at least 4 ground-plane reference points")
        print("  • Spread points across the frame for best accuracy")
        print("  • Press 'q' when done, 'u' to undo last, 'r' to reset all")
        print("  • Press 'v' to verify calibration before saving\n")

        cv2.namedWindow(self._window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self._window, 1200, 800)
        cv2.setMouseCallback(self._window, self._mouse_callback)
        cv2.imshow(self._window, self._display)

        while True:
            key = cv2.waitKey(50) & 0xFF
            if key == ord("q"):
                if len(self._points) < 4:
                    print(f"\n⚠️  Need at least 4 points, got {len(self._points)}")
                    cont = input("  Continue anyway? (y/n): ").strip().lower()
                    if cont == "y":
                        break
                    continue
                break
            if key == ord("u"):
                self._undo_last()
            if key == ord("r"):
                confirm = input("  Reset all points? (y/n): ").strip().lower()
                if confirm == "y":
                    self._points = []
                    self._undo_stack = []
                    self._display = self._image.copy()
                    cv2.imshow(self._window, self._display)
                    print("  ✓ Reset — click new points")
            if key == ord("v"):
                self._verify_preview()

        cv2.destroyAllWindows()
        return self._points

    def _verify_preview(self) -> None:
        """Show quick calibration preview without saving."""
        if len(self._points) < 4:
            print("  ⚠️  Need at least 4 points to verify")
            return
        
        print("\n[Preview] Computing homography...")
        try:
            pixel_pts = [(p[0], p[1]) for p in self._points]
            real_pts = [(p[2], p[3]) for p in self._points]
            
            cal = CameraCalibration.from_point_pairs(
                pixel_points=pixel_pts,
                real_world_points=real_pts,
                camera_id=self._camera_id,
            )
            
            # Show verification
            print("\n[Preview] Verification results:")
            result = cal.verify()
            print(f"  • Mean error: {result.get('mean_error_m', 'N/A'):.3f}m")
            print(f"  • Max error: {result.get('max_error_m', 'N/A'):.3f}m")
            print(f"  • Status: {'✓ PASS' if result.get('pass') else '✗ FAIL'}")
            
            if result.get('pass'):
                print("  ✓ Calibration looks good — press 'q' to save")
            else:
                print("  ⚠️  Consider re-clicking points for better accuracy")
                
        except HomographyComputationError as e:
            print(f"  ✗ Homography failed: {e}")
        except Exception as e:
            print(f"  ✗ Verification error: {e}")


def calibrate(image_path: str, camera_id: str = "default", output_path: Optional[str] = None) -> CameraCalibration:
    """
    Run interactive calibration and save result.

    Args:
        image_path  : Path to a captured frame from the camera.
        camera_id   : Identifier for this camera.
        output_path : Optional custom output path (for testing).

    Returns:
        CameraCalibration instance.
    """
    camera_id_safe = _sanitize_camera_id(camera_id)
    
    print(f"\n🎯 Starting calibration for camera: {camera_id_safe}")
    
    calibrator = InteractiveCalibrator(image_path, camera_id_safe)
    points = calibrator.run()

    if len(points) < 4:
        print(f"\n❌ ERROR: Need at least 4 points, got {len(points)}.")
        print("   Re-run and click more well-spread reference points.")
        sys.exit(1)

    pixel_pts = [(p[0], p[1]) for p in points]
    real_pts = [(p[2], p[3]) for p in points]

    try:
        cal = CameraCalibration.from_point_pairs(
            pixel_points=pixel_pts,
            real_world_points=real_pts,
            camera_id=camera_id_safe,
        )
    except HomographyComputationError as e:
        print(f"\n❌ Homography computation failed: {e}")
        print("   Tips:")
        print("   • Ensure points are not collinear (spread across frame)")
        print("   • Click accurately on marker centres")
        print("   • Use high-contrast markers for precise clicking")
        sys.exit(1)

    # Verify before saving
    print("\n=== Calibration Verification ===")
    result = cal.verify()
    print(f"Mean error: {result['mean_error_m']:.3f}m")
    print(f"Max error: {result['max_error_m']:.3f}m")
    
    if not result['pass']:
        print("\n⚠️  Calibration accuracy below threshold")
        confirm = input("  Save anyway? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted — re-run calibration with better points")
            sys.exit(0)

    # Save calibration
    try:
        if output_path:
            cal.save(output_path)
        else:
            cal.save()  # Uses default path from config
    except CalibrationError as e:
        print(f"\n❌ Failed to save calibration: {e}")
        sys.exit(1)

    # Final summary
    print(f"\n✅ Calibration complete!")
    print(f"   Saved to: {CALIBRATION_PATH}")
    print(f"   Pixels per metre: ~{cal.pixels_per_meter:.1f}")
    print(f"   Validated: {cal.validated}")
    print(f"\n🔧 The pipeline will use this calibration automatically.")
    print(f"   To recalibrate: re-run this script with a new frame.")
    
    return cal


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive camera calibration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --image frame.jpg
  %(prog)s --image frame.png --camera-id cam-02
  %(prog)s --image frame.jpg --output /custom/path/cal.json

Tips:
  • Use floor tape or painted markers at known distances
  • Spread points across the frame (corners + centre)
  • Click precisely on marker centres for best accuracy
        """,
    )
    parser.add_argument(
        "--image", "-i",
        required=True,
        help="Path to calibration frame (jpg/png/bmp)",
    )
    parser.add_argument(
        "--camera-id", "-c",
        default="default",
        help="Camera identifier (alphanumeric + dash/underscore)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Optional custom output path for calibration JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if args.verbose else "INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    
    try:
        calibrate(
            image_path=args.image,
            camera_id=args.camera_id,
            output_path=args.output,
        )
    except FileNotFoundError as e:
        logger.error("File not found: {}", e)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Calibration cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        sys.exit(1)


if __name__ == "__main__":
    main()