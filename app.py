import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv
from report import generate_road_health_report

load_dotenv()

app = Flask(__name__)

# ---------- CONFIG ----------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ROBOFLOW_API_KEY = os.environ.get("ROBOFLOW_API_KEY")

# ✅ YOUR ACTUAL MODEL DETAILS (FROM ROBOFLOW)
ROBOFLOW_MODEL = "pothole-detection-orxff-ak0bb"
ROBOFLOW_VERSION = "1"

ROBOFLOW_URL = f"https://detect.roboflow.com/{ROBOFLOW_MODEL}/{ROBOFLOW_VERSION}"

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect("potholes.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS potholes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL,
            longitude REAL,
            severity TEXT,
            confidence REAL,
            depth REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- ROUTES ----------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/detect-page")
def detect_page():
    return render_template("detect.html")

# ---------- DETECTION (ROBLOWFLOW REST API) ----------
@app.route("/detect", methods=["POST"])
def detect():
    try:
        image = request.files["image"]
        lat = float(request.form.get("latitude", 0))
        lon = float(request.form.get("longitude", 0))

        image_path = os.path.join(UPLOAD_FOLDER, "capture.jpg")
        image.save(image_path)

        # 🔁 CALL ROBOFLOW REST API
        with open(image_path, "rb") as img:
            response = requests.post(
                ROBOFLOW_URL,
                params={"api_key": ROBOFLOW_API_KEY},
                files={"file": img}
            )

        result = response.json()
        predictions = result.get("predictions", [])

        detections = []

        conn = sqlite3.connect("potholes.db")
        c = conn.cursor()

        for p in predictions:
            width = p["width"]
            height = p["height"]
            confidence = round(p["confidence"], 2)

            area = width * height

            if area < 3000:
                severity = "Low"
            elif area < 8000:
                severity = "Medium"
            else:
                severity = "High"

            depth = round(10000 / (area + 1), 2)

            detections.append({
                "severity": severity,
                "confidence": confidence,
                "depth": depth
            })

            c.execute("""
                INSERT INTO potholes VALUES (NULL, ?, ?, ?, ?, ?, ?)
            """, (lat, lon, severity, confidence, depth, datetime.now()))

        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "count": len(detections),
            "detections": detections,
            "fps": "Roboflow REST API"
        })

    except Exception as e:
        print("❌ DETECTION ERROR:", e)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# ---------- MAP DATA ----------
@app.route("/api/potholes")
def get_potholes():
    conn = sqlite3.connect("potholes.db")
    c = conn.cursor()
    rows = c.execute("""
        SELECT latitude, longitude, severity
        FROM potholes
    """).fetchall()
    conn.close()

    return jsonify([
        {"lat": r[0], "lon": r[1], "severity": r[2]} for r in rows
    ])

# ---------- REPORT ----------
@app.route("/report")
def report_form():
    return render_template("report_form.html")

@app.route("/generate-report", methods=["POST"])
def generate_report():
    source = request.form["source"]
    destination = request.form["destination"]

    conn = sqlite3.connect("potholes.db")
    c = conn.cursor()
    rows = c.execute("""
        SELECT latitude, longitude, severity, confidence, timestamp
        FROM potholes
    """).fetchall()
    conn.close()

    potholes = []
    for r in rows:
        potholes.append({
            "lat": r[0],
            "lon": r[1],
            "severity": r[2],
            "confidence": r[3],
            "time": r[4]
        })

    output_path = "road_health_complaint_report.pdf"
    generate_road_health_report(source, destination, potholes, output_path)

    return send_file(output_path, as_attachment=True)

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
