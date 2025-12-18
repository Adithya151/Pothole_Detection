import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from inference_sdk import InferenceHTTPClient
from report import generate_road_health_report
from flask import send_file
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 🔐 Roboflow Inference Client
client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=os.environ.get("ROBOFLOW_API_KEY")
)

WORKSPACE_NAME = "adi-work"
WORKFLOW_ID = "detect-count-and-visualize"

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

# ---------- DETECTION ----------
@app.route("/detect", methods=["POST"])
def detect():
    try:
        # 1️⃣ Read inputs
        image = request.files["image"]
        lat = float(request.form.get("latitude", 0))
        lon = float(request.form.get("longitude", 0))

        image_path = os.path.join(UPLOAD_FOLDER, "capture.jpg")
        image.save(image_path)

        # 2️⃣ Run Roboflow workflow (EXACTLY as docs say)
        result = client.run_workflow(
            workspace_name="adi-work",
            workflow_id="detect-count-and-visualize",
            images={"image": image_path},
            use_cache=True
        )

        # 3️⃣ SAFE parsing
        outputs = result.get("outputs")
        if not outputs:
            return jsonify({
                "status": "error",
                "message": "No outputs from Roboflow"
            }), 500

        predictions = outputs[0].get("predictions", [])

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

        # 4️⃣ Return clean response to frontend
        return jsonify({
            "status": "success",
            "count": len(detections),
            "detections": detections,
            "fps": "Roboflow API"
        })

    except Exception as e:
        print("❌ Roboflow Inference Error:", e)
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
        SELECT latitude, longitude, severity FROM potholes
    """).fetchall()
    conn.close()

    return jsonify([
        {"lat": r[0], "lon": r[1], "severity": r[2]} for r in rows
    ])
    
    
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
