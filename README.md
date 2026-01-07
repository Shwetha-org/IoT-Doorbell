# IoT Doorbell

Smart doorbell built on a Raspberry Pi with a camera, physical button, LEDs, buzzer, and AWS Rekognition–based access control.

## Overview

When someone presses the doorbell button on the Raspberry Pi, the system captures a snapshot, briefly buzzes, and updates the LEDs and a web UI based on whether the visitor is recognized and allowed by AWS Rekognition. The project is structured into a GPIO controller, a Rekognition-backed Flask server, and a small enrollment tool.

## Features

- Physical doorbell button triggers:
  - Camera snapshot saved on the Pi.
  - Short buzzer feedback.
  - LED updates for “allowed” (green) or “denied” (red).
- Local web UIs:
  - Simple door camera UI showing the latest snapshot and door status.
  - Secure door camera UI that auto-refreshes when new snapshots are taken.
- AWS Rekognition integration:
  - Sends door snapshots to Rekognition for face search.
  - Displays recognized person name and similarity score.
  - Grants/denies access based on a configurable allow-list of person IDs.
- Face enrollment helper:
  - Simple script to index family-member images into a Rekognition collection.

## Project structure

```text
IoT Doorbell/
├── src/
│   ├── door_camera_local.py          # Local door camera UI, button + LEDs + buzzer
│   ├── doorbell_gpio_client.py       # GPIO button controller that posts snapshots
│   └── rekognition_access_server.py  # Flask server + Rekognition + secure door UI
└── tools/
    └── rekognition_enroll_face.py    # Helper to enroll faces into Rekognition
```

## Components

### `src/door_camera_local.py`

Local Flask app running on the Pi that:

- Listens to a physical button using `gpiozero.Button` and drives LEDs and a buzzer.
- Captures a frame from the camera with OpenCV and saves it as `doorsnapshot.jpg` when the button is pressed.
- Serves a web page that shows the latest snapshot and basic door-open/door-closed actions, with auto-refresh when a new snapshot is taken.

### `src/doorbell_gpio_client.py`

Headless GPIO controller that:

- Waits for a doorbell button press on the Pi.
- Captures a snapshot via OpenCV and writes it to disk.
- Optionally computes a simple demo bounding box and POSTs the image (and box metadata) to the Rekognition server’s `/analyze` endpoint.
- Sets the green/red LEDs based on whether the server reports the visitor as recognized/allowed.

### `src/rekognition_access_server.py`

Flask server that:

- Hosts a “Secure Door Camera” UI showing the latest snapshot, decision (granted/denied), person label, and similarity.
- Receives images from the GPIO client on `/analyze`, calls Amazon Rekognition `search_faces_by_image`, and decides access based on an allow-list (for example, family members).
- Optionally overlays a bounding box around the detected face in a copy of the snapshot for visualization.

### `tools/rekognition_enroll_face.py`

Helper script that:

- Reads a local JPEG (for example, `alice.jpeg`) from the `tools/` folder.
- Calls `rekognition.index_faces` to add that face into the configured collection with a specific `ExternalImageId` that matches the allow-list used by the server.

## Prerequisites

- Raspberry Pi with:
  - Camera (USB or CSI).
  - Button, buzzer, green LED, red LED wired to the GPIO pins used in the scripts (defaults are GPIO 17/27 for LEDs, 22 for buzzer, 23 for button).
- Python 3 and `pip` installed on the Pi.
- AWS account with:
  - Amazon Rekognition enabled in your region.
  - IAM credentials configured on the Pi (for example, via `aws configure`).

## Installation

From the project root:

```bash
# (optional) create and activate a virtualenv
python3 -m venv venv
source venv/bin/activate

# install dependencies
pip install flask gpiozero opencv-python boto3 pillow requests

```

## Configuration

Set the following environment variables on the Pi before running the Rekognition server:

```bash
export REKOG_COLLECTION_ID="door-collection"   # your Rekognition collection ID
export DOORBELL_ALLOWED_IDS="alice,bob"        # comma-separated allowed ExternalImageIds
```

## Usage

### 1. Enroll faces (one-time per person)

Place a JPEG (for example, `alice.jpeg`) in `tools/` and update `rekognition_enroll_face.py` to use the correct filename and `PERSONID`.

```bash
cd tools
python rekognition_enroll_face.py
```
### 2. Run the Rekognition access server

```bash
cd src
python rekognition_access_server.py
```
Open the server in a browser on the same network, for example:

```bash
http://<pi-ip>:5001/
```

### 3. Run the GPIO doorbell client (on the Pi)

This usually needs root for GPIO and camera access:

```bash
cd src
sudo python doorbell_gpio_client.py
```
Now, pressing the doorbell button should:

- Buzz briefly.
- Capture and upload a snapshot to the Rekognition server.
- Update LEDs and the web UI with the recognition/access result.

### 4. Optional: run the local door camera UI

```bash
cd src
python door_camera_local.py
```

This provides an alternative simple snapshot UI focused on the local camera and manual open/close actions.


## Notes

- This project is intended to run on a trusted local network; the Flask servers are not hardened for direct internet exposure.
- The Rekognition integration demonstrates an edge → cloud → edge control loop: the Pi sends images to AWS and uses the decision to directly drive local actuators (LEDs and buzzer).
- For production-like setups, you can use `systemd` services on the Pi to start the GPIO client and Flask server at boot.
