from flask import Flask, render_template_string, redirect, url_for, send_file, jsonify
from gpiozero import LED, Button, Buzzer
from threading import Thread
from datetime import datetime
from pathlib import Path
import time
import cv2
import os

# ---------- GPIO setup (BCM) ----------
GREEN_LED_PIN = 17   # physical pin 11
RED_LED_PIN   = 27   # physical pin 13
BUZZER_PIN    = 22   # physical pin 15
BUTTON_PIN    = 23   # physical pin 16

green = LED(GREEN_LED_PIN)
red   = LED(RED_LED_PIN)
buzzer = Buzzer(BUZZER_PIN)
button = Button(BUTTON_PIN, pull_up=True)   # button between GPIO23 and GND

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "door_snapshot.jpg"

# ---------- Flask app ----------
app = Flask(__name__)

PAGE = """
<!doctype html>
<html>
  <head>
    <title>Door Camera</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <style>
      body { font-family: Arial, sans-serif; margin: 30px; }
      img { max-width: 480px; display: block; margin-bottom: 20px; }
      button { font-size: 1.1rem; padding: 8px 18px; margin-right: 10px; }
      .allow { background-color: #4CAF50; color: white; }
      .deny  { background-color: #f44336; color: white; }
    </style>
  </head>
  <body>
    <h1>Door Camera</h1>
    <p>Latest snapshot taken at: {{ ts or 'n/a' }}</p>
    {% if has_image %}
      <img id="snapshot" src="{{ url_for('snapshot') }}?t={{ ts or '' }}" alt="Door snapshot">
    {% else %}
      <p>No snapshot yet. Press the physical button on the Pi to simulate doorbell.</p>
    {% endif %}

    <form action="{{ url_for('allow') }}" method="post" style="display:inline;">
      <button type="submit" class="allow">Allow (Green LED)</button>
    </form>
    <form action="{{ url_for('deny') }}" method="post" style="display:inline;">
      <button type="submit" class="deny">Deny (Red LED)</button>
    </form>

    <p>Status: {{ status }}</p>

    <script>
      let lastTs = "{{ ts or '' }}";

      async function checkForNewSnapshot() {
        try {
          const resp = await fetch("{{ url_for('snapshot_metadata') }}", {
            cache: "no-store"
          });
          const data = await resp.json();
          const newTs = data.ts || "";
          if (newTs && newTs !== lastTs) {
            // New picture taken -> reload once to update image and text
            window.location.reload();
          }
        } catch (e) {
          console.log("Error checking snapshot:", e);
        }
      }

      // Poll every 2 seconds but only reload when timestamp changes
      setInterval(checkForNewSnapshot, 2000);
    </script>
  </body>
</html>
"""

last_ts = None
status_msg = ""
CAM_INDEX = 0   # change to 1 if your webcam is /dev/video1


# ---------- Camera capture ----------
def capture_image():
    """Capture one frame and save to IMAGE_PATH."""
    global last_ts, status_msg
    print("Capturing image from webcam...")
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        status_msg = f"ERROR: Could not open camera index {CAM_INDEX}"
        print(status_msg)
        return
    ret, frame = cap.read()
    cap.release()
    if not ret:
        status_msg = "ERROR: Failed to read frame"
        print(status_msg)
        return
    cv2.imwrite(str(IMAGE_PATH), frame)
    last_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_msg = f"Snapshot taken at {last_ts}"
    print(status_msg)


# ---------- Button event: buzzer + capture ----------
def on_button_pressed():
    global status_msg
    print("Doorbell button pressed")
    status_msg = "Doorbell pressed: buzzing and taking picture..."
    buzzer.on()
    time.sleep(0.5)
    buzzer.off()
    capture_image()

button.when_pressed = lambda: Thread(target=on_button_pressed, daemon=True).start()


# ---------- Routes ----------
@app.route("/", methods=["GET"])
def index():
    has_image = IMAGE_PATH.exists()
    return render_template_string(
        PAGE,
        ts=last_ts,
        has_image=has_image,
        status=status_msg,
    )

@app.route("/snapshot")
def snapshot():
    if IMAGE_PATH.exists():
        return send_file(IMAGE_PATH, mimetype="image/jpeg")
    return ("No image", 404)

@app.route("/snapshot-metadata")
def snapshot_metadata():
    # Used by JS to detect when a new snapshot is taken
    return jsonify({"ts": last_ts})

@app.route("/allow", methods=["POST"])
def allow():
    global status_msg
    green.on()
    red.off()
    status_msg = "Door OPEN: Green LED ON"
    print(status_msg)
    return redirect(url_for("index"))

@app.route("/deny", methods=["POST"])
def deny():
    global status_msg
    green.off()
    red.on()
    status_msg = "Door CLOSED: Red LED ON"
    print(status_msg)
    return redirect(url_for("index"))


# ---------- Main ----------
if __name__ == "__main__":
    try:
        print("Door camera server at http://<pi-ip>:5001/")
        app.run(host="0.0.0.0", port=5001, debug=False)
    finally:
        green.off()
        red.off()
        buzzer.off()