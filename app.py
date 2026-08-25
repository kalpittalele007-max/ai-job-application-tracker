import os
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")
applications = []

STATUSES = ["Applied", "Interview", "Offer", "Reject"]

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.get("/api/applications")
def list_applications():
    return jsonify(applications)

@app.post("/api/applications")
def create_application():
    data = request.get_json(silent=True) or {}
    required = ["company", "role", "applicationDate", "status"]
    if any(not data.get(k) for k in required):
        return jsonify({"error": "company, role, applicationDate and status are required"}), 400
    if data["status"] not in STATUSES:
        return jsonify({"error": "invalid status"}), 400

    item = {
        "id": str(len(applications) + 1),
        "company": data["company"].strip(),
        "role": data["role"].strip(),
        "applicationDate": data["applicationDate"],
        "jobType": data.get("jobType", "full-time"),
        "description": data.get("description", "").strip(),
        "status": data["status"],
        "createdAt": datetime.utcnow().isoformat() + "Z"
    }
    applications.append(item)
    return jsonify(item), 201

@app.patch("/api/applications/<app_id>")
def update_application(app_id):
    item = next((x for x in applications if x["id"] == app_id), None)
    if not item:
        return jsonify({"error": "application not found"}), 404
    data = request.get_json(silent=True) or {}
    if "status" in data and data["status"] not in STATUSES:
        return jsonify({"error": "invalid status"}), 400
    for key in ["company", "role", "applicationDate", "jobType", "description", "status"]:
        if key in data:
            item[key] = data[key]
    return jsonify(item)

@app.delete("/api/applications/<app_id>")
def delete_application(app_id):
    global applications
    before = len(applications)
    applications = [x for x in applications if x["id"] != app_id]
    return jsonify({"deleted": len(applications) != before})

@app.post("/api/import")
def import_jobs():
    payload = request.get_json(silent=True) or []
    if not isinstance(payload, list):
        return jsonify({"error": "Expected an array of job postings"}), 400

    added = 0
    for job in payload:
        if not all(k in job for k in ("id", "from", "to", "type", "description")):
            continue
        jid = str(job["id"])
        if any(x["id"] == jid for x in applications):
            continue
        applications.append({
            "id": jid,
            "company": job.get("company", "Imported Company"),
            "role": job["description"],
            "applicationDate": job["from"],
            "jobType": job["type"],
            "description": job["description"],
            "status": "Applied",
            "createdAt": datetime.utcnow().isoformat() + "Z"
        })
        added += 1
    return jsonify({"added": added, "total": len(applications)})

@app.post("/api/generate")
def generate_draft():
    """Demo-safe generation endpoint.

    In production, replace this deterministic fallback with Vertex AI Gemini.
    The README contains the GCP integration plan.
    """
    data = request.get_json(silent=True) or {}
    role = data.get("role", "the position")
    company = data.get("company", "your company")
    kind = data.get("type", "cover_letter")
    if kind == "follow_up_email":
        text = (
            f"Subject: Follow-up on my {role} application\n\n"
            f"Dear Hiring Manager,\n\n"
            f"I am following up regarding my application for {role} at {company}. "
            "I remain very interested in the opportunity and would be glad to provide "
            "any additional information required.\n\nBest regards"
        )
    else:
        text = (
            f"Dear Hiring Manager,\n\n"
            f"I am writing to express my interest in the {role} position at {company}. "
            "My experience and technical interests align closely with the requirements "
            "of this role. I would welcome the opportunity to discuss how I can contribute "
            "to your team.\n\nBest regards"
        )
    return jsonify({"draft": text, "provider": "demo-fallback", "next": "Vertex AI Gemini"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
