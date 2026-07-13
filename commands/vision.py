"""
commands/vision.py — Computer vision commands for J.A.R.V.I.S.

Provides camera and screen vision capabilities:
- Camera capture (photo/video)
- Object detection (YOLO)
- OCR text extraction (Tesseract)
- QR / barcode detection
- Screenshot OCR

All backends are optional — graceful fallback when libraries
are not installed.
"""
import os
import time
from typing import Optional

from core.logger import get_logger

log = get_logger("commands.vision")


# ─── Backend Availability ────────────────────────────────

def _check_opencv() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _check_tesseract() -> bool:
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def _check_yolo() -> bool:
    try:
        from ultralytics import YOLO  # noqa: F401
        return True
    except ImportError:
        return False


def _check_pyzbar() -> bool:
    try:
        from pyzbar import pyzbar  # noqa: F401
        return True
    except ImportError:
        return False


# ─── Camera Operations ──────────────────────────────────

def capture_photo(filename: str = None) -> tuple[bool, str]:
    """Capture a photo from the default camera."""
    if not _check_opencv():
        return False, "OpenCV not installed. Install with: pip install opencv-python"

    import cv2
    from config.config import DATA_DIR

    if filename is None:
        filename = f"photo_{int(time.time())}.jpg"
    filepath = os.path.join(DATA_DIR, "captures", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False, "Could not access camera"

        # Warm up camera
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return False, "Could not capture image"

        cv2.imwrite(filepath, frame)
        log.info("Photo captured: %s", filepath)
        return True, f"Photo saved: {filename}"
    except Exception as e:
        log.error("Camera error: %s", e)
        return False, f"Camera error: {e}"


# ─── Object Detection ───────────────────────────────────

_yolo_model = None


def _get_yolo_model():
    """Get or load the YOLO model (lazy singleton)."""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO("yolov8n.pt")  # Nano model — fast, ~6MB
        log.info("YOLO model loaded")
    return _yolo_model


def detect_objects(image_path: str = None) -> tuple[bool, str]:
    """
    Detect objects in an image or from camera.

    Args:
        image_path: Path to image file. If None, captures from camera.
    """
    if not _check_yolo():
        return False, "YOLO not installed. Install with: pip install ultralytics"

    if not _check_opencv():
        return False, "OpenCV required for object detection"

    import cv2

    try:
        if image_path and os.path.exists(image_path):
            frame = cv2.imread(image_path)
        else:
            # Capture from camera
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return False, "Could not access camera"
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return False, "Could not capture image"

        model = _get_yolo_model()
        results = model(frame, verbose=False)

        # Parse detections
        detections = []
        for result in results:
            for box in result.boxes:
                cls_name = model.names[int(box.cls[0])]
                confidence = float(box.conf[0])
                if confidence > 0.4:
                    detections.append(f"{cls_name} ({confidence:.0%})")

        if not detections:
            return True, "I don't see any recognizable objects."

        unique = list(dict.fromkeys(detections))  # Deduplicate, preserve order
        log.info("Detected objects: %s", unique)
        return True, f"I can see: {', '.join(unique[:10])}"
    except Exception as e:
        log.error("Object detection error: %s", e)
        return False, f"Detection error: {e}"


# ─── OCR ─────────────────────────────────────────────────

def ocr_image(image_path: str = None) -> tuple[bool, str]:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image_path: Path to image. If None, takes a screenshot.
    """
    if not _check_tesseract():
        return False, "Tesseract OCR not installed. Install pytesseract and Tesseract-OCR engine."

    try:
        import pytesseract
        from PIL import Image

        if image_path and os.path.exists(image_path):
            img = Image.open(image_path)
        else:
            # Take screenshot
            import pyautogui
            img = pyautogui.screenshot()

        text = pytesseract.image_to_string(img).strip()

        if not text:
            return True, "I couldn't read any text from the image."

        # Truncate for speech
        if len(text) > 500:
            text = text[:500] + "..."

        log.info("OCR extracted %d chars", len(text))
        return True, f"I read: {text}"
    except Exception as e:
        log.error("OCR error: %s", e)
        return False, f"OCR error: {e}"


def ocr_screenshot() -> tuple[bool, str]:
    """Take a screenshot and run OCR on it."""
    return ocr_image(image_path=None)


# ─── QR / Barcode Detection ─────────────────────────────

def scan_qr(image_path: str = None) -> tuple[bool, str]:
    """
    Scan QR codes and barcodes from an image or camera.
    """
    if not _check_pyzbar():
        return False, "pyzbar not installed. Install with: pip install pyzbar"

    if not _check_opencv():
        return False, "OpenCV required for QR scanning"

    import cv2
    from pyzbar import pyzbar

    try:
        if image_path and os.path.exists(image_path):
            frame = cv2.imread(image_path)
        else:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return False, "Could not access camera"
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return False, "Could not capture image"

        codes = pyzbar.decode(frame)

        if not codes:
            return True, "No QR codes or barcodes detected."

        results = []
        for code in codes:
            data = code.data.decode("utf-8", errors="ignore")
            code_type = code.type
            results.append(f"{code_type}: {data}")

        log.info("Scanned codes: %s", results)
        return True, "Found: " + "; ".join(results)
    except Exception as e:
        log.error("QR scan error: %s", e)
        return False, f"QR scan error: {e}"


# ─── Command Router ─────────────────────────────────────

def handle_vision_command(command: str) -> tuple[bool, bool, str]:
    """
    Route vision-related commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # Camera commands
    if cmd in ("take a photo", "take photo", "capture photo", "take a picture", "take picture"):
        ok, msg = capture_photo()
        return True, ok, msg

    # Object detection
    if cmd in ("what do you see", "what can you see", "detect objects",
               "look around", "identify objects", "what is in front of you"):
        ok, msg = detect_objects()
        return True, ok, msg

    if cmd.startswith("detect objects in "):
        path = cmd.replace("detect objects in ", "").strip()
        ok, msg = detect_objects(path)
        return True, ok, msg

    # OCR
    if cmd in ("read this", "read screen", "ocr screen", "read my screen",
               "what does this say", "read text"):
        ok, msg = ocr_screenshot()
        return True, ok, msg

    if cmd.startswith("read text from ") or cmd.startswith("ocr "):
        path = cmd.replace("read text from ", "").replace("ocr ", "").strip()
        ok, msg = ocr_image(path)
        return True, ok, msg

    # QR/Barcode
    if cmd in ("scan qr", "scan qr code", "read qr code", "scan barcode",
               "read barcode", "scan code"):
        ok, msg = scan_qr()
        return True, ok, msg

    if cmd.startswith("scan qr from "):
        path = cmd.replace("scan qr from ", "").strip()
        ok, msg = scan_qr(path)
        return True, ok, msg

    return False, False, ""
