from gpiozero import LED, Button, Buzzer
from threading import Thread
from pathlib import Path
from datetime import datetime
import time
import cv2
import requests

GREEN_LED_PIN = 17
RED_LED_PIN   = 27
BUZZER_PIN    = 22
BUTTON_PIN    = 23

green = LED(GREEN_LED_PIN)
red   = LED(RED_LED_PIN)
buzzer = Buzzer(BUZZER_PIN)
button = Button(BUTTON_PIN, pull_up=True)

BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "door_snapshot.jpg"

CAM_INDEX = 0
ANALYZE_URL = "http://127.0.0.1:5001/analyze"  # Flask + Rekognition endpoint

def capture_image():
    print("GPIO: capturing image from webcam...")
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera index {CAM_INDEX}")
        return False, None
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("ERROR: Failed to read frame")
        return False, None

    # Save snapshot
    cv2.imwrite(str(IMAGE_PATH), frame)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"GPIO: Snapshot saved at {IMAGE_PATH} ({ts})")

    return True, frame

def compute_demo_box(frame):
    """
    Compute a simple demo bounding box around the center of the frame.
    This is just to visualize the overlay in the Flask UI.
    """
    if frame is None:
        return None

    h, w, _ = frame.shape
    box_w = int(w * 0.5)
    box_h = int(h * 0.5)
    x = (w - box_w) // 2
    y = (h - box_h) // 2
    return x, y, box_w, box_h

def handle_button():
    print("GPIO: doorbell button pressed")
    buzzer.on()
    time.sleep(0.5)
    buzzer.off()

    ok, frame = capture_image()
    if not ok:
        green.off()
        red.on()
        return

    # Demo bounding box (center of image); replace with real face box if you wish
    box = compute_demo_box(frame)
    form_data = {}
    if box is not None:
        x, y, w, h = box
        form_data = {
            "box_x": str(x),
            "box_y": str(y),
            "box_w": str(w),
            "box_h": str(h),
        }

    try:
        with open(IMAGE_PATH, "rb") as f:
            files = {"img": f}
            resp = requests.post(ANALYZE_URL, files=files, data=form_data, timeout=15)

        print("GPIO: HTTP status", resp.status_code, "body:", resp.text)

        data = resp.json()
        recognized = data.get("recognized", False)
        person = data.get("person")

        if recognized:
            green.on()
            red.off()
            print(f"GPIO: Recognized {person} → GREEN ON, RED OFF")
        else:
            green.off()
            red.on()
            print("GPIO: Not recognized → GREEN OFF, RED ON")
    except Exception as e:
        green.off()
        red.on()
        print("GPIO: Error calling Rekognition server:", e, "→ RED ON (fail-safe)")

button.when_pressed = lambda: Thread(target=handle_button, daemon=True).start()

if __name__ == "__main__":
    try:
        print("GPIO controller running (sudo). Waiting for button presses...")
        while True:
            time.sleep(1)
    finally:
        green.off()
        red.off()
        buzzer.off()