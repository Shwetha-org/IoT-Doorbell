import boto3
from pathlib import Path

COLLECTION_ID = "door-collection"
PERSON_ID = "shwetha"   # must match ALLOWED_IDS in ex1.py

rekog = boto3.client("rekognition")

# Image is in the same directory as this script
BASE_DIR = Path(__file__).resolve().parent
img_path = BASE_DIR / "shwetha.jpeg"

if not img_path.exists():
    raise FileNotFoundError(f"Image not found: {img_path}")

with img_path.open("rb") as f:
    bytes_ = f.read()

resp = rekog.index_faces(
    CollectionId=COLLECTION_ID,
    Image={"Bytes": bytes_},
    ExternalImageId=PERSON_ID,
    DetectionAttributes=[],
    MaxFaces=1,
    QualityFilter="AUTO",
)

print(img_path.name, "→ indexed", len(resp.get("FaceRecords", [])), "faces")