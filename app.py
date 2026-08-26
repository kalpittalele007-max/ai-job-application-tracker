import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory

# Optional Gemini integration.
# The application still works without a Gemini API key.
try:
    from google import genai
except ImportError:
    genai = None


app = Flask(__name__)

DATABASE = os.getenv("DATABASE_PATH", "applications.db")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

STATUSES = ["Applied", "Interview", "Offer", "Reject"]
DRAFT_TYPES = ["cover_letter", "follow_up_email"]


# ---------------------------------------------------------
# Database
# ---------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            application_date TEXT NOT NULL,
            job_type TEXT NOT NULL DEFAULT 'full-time',
            description TEXT DEFAULT '',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            type TEXT NOT NULL,
            contents TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES applications(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES applications(id)
        )
    """)

    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def row_to_application(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "company": row["company"],
        "role": row["role"],
        "applicationDate": row["application_date"],
        "jobType": row["job_type"],
        "description": row["description"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_application(app_id):
    conn = get_db()

    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?",
        (str(app_id),)
    ).fetchone()

    conn.close()

    return row_to_application(row)


# ---------------------------------------------------------
# Gemini
# ---------------------------------------------------------

def get_gemini_client():
    """
    Creates a Gemini client only when GEMINI_API_KEY exists.

    Never put the API key directly in this source file.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return None

    if genai is None:
        return None

    return genai.Client(api_key=api_key)


def fallback_draft(application, draft_type):
    """
    Keeps the application functional when Gemini is unavailable.
    """

    company = application["company"]
    role = application["role"]

    if draft_type == "follow_up_email":
        return (
            f"Subject: Follow-up on my {role} application\n\n"
            f"Dear Hiring Manager,\n\n"
            f"I am following up regarding my application for the "
            f"{role} position at {company}. I remain very interested "
            f"in the opportunity and would be happy to provide any "
            f"additional information required.\n\n"
            f"Best regards"
        )

    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my interest in the {role} "
        f"position at {company}. My skills and interests align "
        f"with the requirements of this opportunity, and I would "
        f"welcome the opportunity to contribute to your team.\n\n"
        f"Best regards"
    )


def generate_with_gemini(application, draft_type, previous_drafts):
    client = get_gemini_client()

    if client is None:
        return fallback_draft(application, draft_type), "fallback"

    history = "\n\n".join(
        f"Previous {d['type']}:\n{d['contents']}"
        for d in previous_drafts
    )

    if not history:
        history = "No previous drafts are available."

    if draft_type == "cover_letter":
        task = """
Create a highly tailored professional cover letter for this job.

Requirements:
- Use the job description as the primary source.
- Do not invent qualifications, employers, degrees, or achievements.
- Avoid generic filler.
- Connect the candidate's stated information to the role.
- Keep it concise and professional.
- Return only the letter.
"""
    else:
        task = """
Create a concise professional follow-up email for this job application.

Requirements:
- Mention the role and company.
- Be polite and proactive.
- Do not make up interview dates or recruiter names.
- Do not claim that an email was previously sent unless the history says so.
- Return the subject line followed by the email.
"""

    prompt = f"""
You are an AI career assistant inside an application-tracking system.

{task}

APPLICATION:
Company: {application["company"]}
Role: {application["role"]}
Application date: {application["applicationDate"]}
Job type: {application["jobType"]}
Current status: {application["status"]}

JOB DESCRIPTION:
{application["description"]}

HISTORICAL DRAFTS:
{history}
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        text = getattr(response, "text", None)

        if not text:
            raise RuntimeError("Gemini returned an empty response.")

        return text.strip(), "gemini"

    except Exception as exc:
        app.logger.warning("Gemini generation failed: %s", exc)

        # Graceful degradation.
        return fallback_draft(application, draft_type), "fallback"


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(".", "index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "database": "sqlite",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY"))
    })


@app.get("/api/applications")
def list_applications():
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM applications
        ORDER BY application_date DESC, created_at DESC
    """).fetchall()

    conn.close()

    return jsonify([row_to_application(row) for row in rows])


@app.post("/api/applications")
def create_application():
    data = request.get_json(silent=True) or {}

    required = [
        "company",
        "role",
        "applicationDate",
        "status"
    ]

    if any(not data.get(field) for field in required):
        return jsonify({
            "error": "company, role, applicationDate and status are required"
        }), 400

    if data["status"] not in STATUSES:
        return jsonify({"error": "invalid status"}), 400

    app_id = str(data.get("id") or int(datetime.now().timestamp() * 1000))
    timestamp = now()

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO applications (
                id,
                company,
                role,
                application_date,
                job_type,
                description,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            app_id,
            data["company"].strip(),
            data["role"].strip(),
            data["applicationDate"],
            data.get("jobType", "full-time"),
            data.get("description", "").strip(),
            data["status"],
            timestamp,
            timestamp
        ))

        conn.execute("""
            INSERT INTO status_history (
                job_id,
                old_status,
                new_status,
                changed_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            app_id,
            None,
            data["status"],
            timestamp
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()

        return jsonify({
            "error": "An application with this ID already exists."
        }), 409

    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?",
        (app_id,)
    ).fetchone()

    conn.close()

    return jsonify(row_to_application(row)), 201


@app.patch("/api/applications/<app_id>")
def update_application(app_id):
    conn = get_db()

    current = conn.execute(
        "SELECT * FROM applications WHERE id = ?",
        (str(app_id),)
    ).fetchone()

    if current is None:
        conn.close()

        return jsonify({
            "error": "application not found"
        }), 404

    data = request.get_json(silent=True) or {}

    if "status" in data and data["status"] not in STATUSES:
        conn.close()

        return jsonify({
            "error": "invalid status"
        }), 400

    old_status = current["status"]
    new_status = data.get("status", old_status)

    allowed_fields = {
        "company": "company",
        "role": "role",
        "applicationDate": "application_date",
        "jobType": "job_type",
        "description": "description",
        "status": "status"
    }

    updates = []
    values = []

    for incoming, database_field in allowed_fields.items():
        if incoming in data:
            updates.append(f"{database_field} = ?")
            values.append(data[incoming])

    if not updates:
        conn.close()

        return jsonify(row_to_application(current))

    updates.append("updated_at = ?")
    values.append(now())
    values.append(str(app_id))

    conn.execute(
        f"""
        UPDATE applications
        SET {", ".join(updates)}
        WHERE id = ?
        """,
        values
    )

    if old_status != new_status:
        conn.execute("""
            INSERT INTO status_history (
                job_id,
                old_status,
                new_status,
                changed_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            str(app_id),
            old_status,
            new_status,
            now()
        ))

    conn.commit()

    updated = conn.execute(
        "SELECT * FROM applications WHERE id = ?",
        (str(app_id),)
    ).fetchone()

    conn.close()

    return jsonify(row_to_application(updated))


@app.delete("/api/applications/<app_id>")
def delete_application(app_id):
    conn = get_db()

    exists = conn.execute(
        "SELECT id FROM applications WHERE id = ?",
        (str(app_id),)
    ).fetchone()

    if exists is None:
        conn.close()

        return jsonify({
            "error": "application not found"
        }), 404

    conn.execute(
        "DELETE FROM drafts WHERE job_id = ?",
        (str(app_id),)
    )

    conn.execute(
        "DELETE FROM status_history WHERE job_id = ?",
        (str(app_id),)
    )

    conn.execute(
        "DELETE FROM applications WHERE id = ?",
        (str(app_id),)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "deleted": True,
        "id": str(app_id)
    })


# ---------------------------------------------------------
# Import evaluator dataset
# ---------------------------------------------------------

@app.post("/api/import")
def import_jobs():
    payload = request.get_json(silent=True) or []

    if not isinstance(payload, list):
        return jsonify({
            "error": "Expected an array of job postings"
        }), 400

    conn = get_db()

    added = 0
    skipped = 0

    for job in payload:

        required = [
            "id",
            "from",
            "to",
            "type",
            "description"
        ]

        if not all(field in job for field in required):
            skipped += 1
            continue

        job_id = str(job["id"])

        existing = conn.execute(
            "SELECT id FROM applications WHERE id = ?",
            (job_id,)
        ).fetchone()

        if existing:
            skipped += 1
            continue

        timestamp = now()

        conn.execute("""
            INSERT INTO applications (
                id,
                company,
                role,
                application_date,
                job_type,
                description,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            job.get("company", "Imported Company"),
            job["description"],
            job["from"],
            job["type"],
            job["description"],
            "Applied",
            timestamp,
            timestamp
        ))

        conn.execute("""
            INSERT INTO status_history (
                job_id,
                old_status,
                new_status,
                changed_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            job_id,
            None,
            "Applied",
            timestamp
        ))

        added += 1

    conn.commit()
    conn.close()

    return jsonify({
        "added": added,
        "skipped": skipped
    })


# ---------------------------------------------------------
# Draft generation
# ---------------------------------------------------------

@app.post("/api/generate")
def generate_draft():
    data = request.get_json(silent=True) or {}

    job_id = str(data.get("jobId", ""))

    if not job_id:
        return jsonify({
            "error": "jobId is required"
        }), 400

    draft_type = data.get
