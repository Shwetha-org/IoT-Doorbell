from flask import Flask, request, jsonify, render_template_string, send_file
from pathlib import Path
from datetime import datetime
from io import BytesIO
import boto3
import os

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ---------- AWS Rekognition ----------
COLLECTION_ID = os.environ.get("REKOG_COLLECTION_ID", "door-collection")
rekog = boto3.client("rekognition")  # uses region/creds from aws configure

ALLOWED_IDS = set(
    x.strip() for x in os.environ.get("DOORBELL_ALLOWED_IDS", "saksham,shwetha").split(",")
    if x.strip()
)

app = Flask(__name__)

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "door_snapshot.jpg"          # written by GPIO script (sudo)
BOXED_IMAGE_PATH = BASE_DIR / "door_snapshot_box.jpg"  # with overlay (optional)

last_status = "Idle"
last_faces = 0
last_person = None
last_similarity = None
last_allowed = False
last_box = None  # (x, y, w, h) in image pixels if provided

PAGE = """
<!doctype html>
<html>
  <head>
    <title>Secure Door Camera</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <style>
      body { font-family: Arial, sans-serif; margin: 30px; background-color: #0b1020; color: #e0e0e0; }
      h1 { color: #00d4ff; }
      img { max-width: 480px; display: block; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 0 16px rgba(0,0,0,0.6); }
      .panel { display: flex; gap: 20px; align-items: center; margin-bottom: 20px; }
      .icon { font-size: 40px; }
      .status-box {
        background: #141a33;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 0 10px rgba(0,0,0,0.5);
        min-width: 260px;
      }
      .label { color: #9fa8da; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
      .value { font-size: 14px; margin-bottom: 4px; }
      .allowed { color: #4caf50; }
      .denied  { color: #ff5252; }
      .neutral { color: #ffd740; }
      .meta { font-size: 12px; color: #b0bec5; margin-top: 4px; }
      a { color: #80d8ff; }
    </style>
  </head>
  <body>
    <h1>Secure Door Camera (Local)</h1>

    <div class="panel">
      <div class="icon">
        {% if allowed is none %}
          🛡️
        {% elif allowed %}
          ✅
        {% else %}
          ⚠️
        {% endif %}
      </div>
      <div class="status-box">
        <div class="label">Decision</div>
        {% if allowed is none %}
          <div class="value neutral">Waiting for snapshot...</div>
        {% elif allowed %}
          <div class="value allowed">Access granted</div>
        {% else %}
          <div class="value denied">Access denied</div>
        {% endif %}

        <div class="label" style="margin-top:8px;">Details</div>
        <div class="value">
          Person: {{ person or 'Unknown' }}<br>
          Similarity: {{ similarity if similarity is not none else 'n/a' }}{% if similarity is not none %}%{% endif %}
        </div>
        <div class="meta">
          Status: {{ status }}<br>
          Last snapshot: {{ ts or 'n/a' }}
        </div>
      </div>
    </div>

    {% if has_image %}
      <img id="snapshot" src="{{ url_for('snapshot_boxed') }}?t={{ ts or '' }}" alt="Door snapshot">
    {% else %}
      <p>No snapshot yet. Press the physical button on the Pi.</p>
    {% endif %}

    <p class="meta">This interface is intended to be reachable only on your local network (no internet exposure).</p>

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

def get_ts_from_file():
    if not IMAGE_PATH.exists():
        return None
    mtime = IMAGE_PATH.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

def generate_boxed_image():
    """
    If we have a last_box and Pillow is available, draw a rectangle
    around the face on a copy of IMAGE_PATH and save to BOXED_IMAGE_PATH.
    If anything fails, just copy the original.
    """
    if not IMAGE_PATH.exists():
        return

    if not PIL_AVAILABLE or last_box is None:
        # Just mirror original to boxed path
        try:
            with IMAGE_PATH.open("rb") as src, BOXED_IMAGE_PATH.open("wb") as dst:
                dst.write(src.read())
        except Exception as e:
            print("Error copying image for boxed view:", e)
        return

    try:
        with Image.open(IMAGE_PATH) as im:
            draw = ImageDraw.Draw(im)
            x, y, w, h = last_box
            # Draw semi‑transparent rectangle outline
            draw.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=3)
            im.save(BOXED_IMAGE_PATH, format="JPEG")
    except Exception as e:
        print("Error drawing bounding box:", e)
        # Fallback: copy original
        try:
            with IMAGE_PATH.open("rb") as src, BOXED_IMAGE_PATH.open("wb") as dst:
                dst.write(src.read())
        except Exception as e2:
            print("Error copying fallback image:", e2)

# ---------- Web UI ----------
@app.route("/", methods=["GET"])
def index():
    ts = get_ts_from_file()
    has_image = IMAGE_PATH.exists()
    return render_template_string(
        PAGE,
        ts=ts,
        has_image=has_image,
        status=last_status,
        person=last_person,
        similarity=round(last_similarity, 1) if last_similarity is not None else None,
        allowed=last_allowed if last_faces else None,
    )

@app.route("/snapshot")
def snapshot():
    if IMAGE_PATH.exists():
        return send_file(IMAGE_PATH, mimetype="image/jpeg")
    return ("No image", 404)

@app.route("/snapshot_boxed")
def snapshot_boxed():
    if not IMAGE_PATH.exists():
        return ("No image", 404)
    # Ensure BOXED_IMAGE_PATH exists/updated
    generate_boxed_image()
    if BOXED_IMAGE_PATH.exists():
        return send_file(BOXED_IMAGE_PATH, mimetype="image/jpeg")
    # Fallback to plain image
    return send_file(IMAGE_PATH, mimetype="image/jpeg")

@app.route("/snapshot_metadata")
def snapshot_metadata():
    ts = get_ts_from_file()
    return jsonify({"ts": ts})

# ---------- Rekognition analyze endpoint (called by GPIO script) ----------
@app.route("/analyze", methods=["POST"])
def analyze():
    global last_status, last_faces, last_person, last_similarity, last_allowed, last_box

    file = request.files.get("img")
    if not file:
        last_status = "No file uploaded"
        last_faces = 0
        last_person = None
        last_similarity = None
        last_allowed = False
        last_box = None
        return jsonify({"recognized": False, "error": "no_file"}), 400

    file_bytes = file.read()

    # Optional bounding box coordinates from GPIO (pixels)
    # e.g. send in a JSON field 'meta' or simple form fields
    try:
        box_x = request.form.get("box_x", type=int)
        box_y = request.form.get("box_y", type=int)
        box_w = request.form.get("box_w", type=int)
        box_h = request.form.get("box_h", type=int)
        if box_x is not None and box_y is not None and box_w is not None and box_h is not None:
            last_box = (box_x, box_y, box_w, box_h)
        else:
            last_box = None
    except Exception:
        last_box = None

    try:
        resp = rekog.search_faces_by_image(
            CollectionId=COLLECTION_ID,
            Image={"Bytes": file_bytes},
            MaxFaces=1,
            FaceMatchThreshold=90.0,
        )
        matches = resp.get("FaceMatches", [])
        if not matches:
            last_status = "No matching face in collection"
            last_faces = 0
            last_person = None
            last_similarity = None
            last_allowed = False
            print("Rekognition: no matches")
            return jsonify({"recognized": False})

        m = matches[0]
        label = m["Face"]["ExternalImageId"]
        similarity = float(m["Similarity"])

        last_faces = 1
        last_person = label
        last_similarity = similarity

        if label in ALLOWED_IDS:
            last_allowed = True
            last_status = f"Recognized {label} (similarity {similarity:.1f}%)"
            print(last_status)
            return jsonify({
                "recognized": True,
                "person": label,
                "similarity": similarity,
            })
        else:
            last_allowed = False
            last_status = f"Matched unknown person {label} (similarity {similarity:.1f}%)"
            print(last_status)
            return jsonify({
                "recognized": False,
                "person": label,
                "similarity": similarity,
            })

    except Exception as e:
        last_faces = 0
        last_person = None
        last_similarity = None
        last_allowed = False
        last_box = None
        last_status = f"Rekognition error: {e}"
        print("Rekognition error:", e)
        return jsonify({"recognized": False, "error": str(e)}), 500

if __name__ == "__main__":
    print("Rekognition Flask server at http://0.0.0.0:5001/")
    app.run(host="0.0.0.0", port=5001, debug=False)