import datetime
import json
import os
import random
import time
import uuid
from contextlib import closing
from email.message import EmailMessage
from urllib.parse import quote

import qrcode
import requests
import psycopg2
from flask import Flask, jsonify, make_response, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(BASE_DIR, "static", "uploads"))
MEDIA_SOURCE_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true",
    SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY must be configured in the environment.")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured in the environment.")
    return psycopg2.connect(database_url)


def get_payload():
    return request.get_json(silent=True) or request.form


def api_error(message, status=400):
    return jsonify({"error": message}), status


def user_required():
    if "user" not in session:
        return api_error("Authentication required.", 401)
    return None


def admin_required():
    if not session.get("admin"):
        return api_error("Administrator authentication required.", 401)
    return None


def media_url(path):
    if not path:
        return None
    filename = os.path.basename(str(path).replace("\\", "/"))
    return f"/api/media/{quote(filename)}"


def event_json(row):
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "date": row[3],
        "image": media_url(row[4]),
        "type": row[5],
        "price": row[6],
        "contact_email": row[7] if len(row) > 7 else None,
    }


def profile_json(row):
    if not row:
        return None
    return {
        "email": row[1],
        "name": row[4],
        "mobile": row[5],
        "image": media_url(row[8]) if len(row) > 8 else None,
    }


def ticket_qr(unique_id):
    if not FRONTEND_URL:
        raise RuntimeError("FRONTEND_URL must be configured to generate ticket links.")
    qr_data = f"{FRONTEND_URL}/scan/{unique_id}"
    filename = f"{unique_id}.png"
    qr_path = os.path.join(UPLOAD_FOLDER, filename)
    qrcode.make(qr_data).save(qr_path)
    return filename


def send_email(to_email, subject, html_content):
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
            "content-type": "application/json",
        },
        json={
            "sender": {"email": EMAIL_USER},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_content,
        },
        timeout=20,
    )
    response.raise_for_status()


def send_ticket_email(email, name, event_name, unique_id, qr_filename):
    qr_url = f"{request.host_url.rstrip('/')}/api/media/{quote(qr_filename)}"
    content = f"""
    <html>
    <body style="font-family: Arial; background:#0f2027; padding:20px; color:white;">
        <div style="max-width:500px; margin:auto; background:#1e3c72; padding:20px; border-radius:15px; text-align:center;">
            <h2>🎉 Registration Successful</h2>
            <p style="font-size:16px;">Hello <b>{name}</b>,</p>
            <p>You have successfully registered for:</p>
            <h3 style="color:#4ade80;">{event_name}</h3>
            <p><b>Ticket ID:</b> {unique_id}</p>
            <hr style="margin:20px 0;">
            <p>📌 Show your ticket at entry</p>
            <img src="{qr_url}" width="200" style="margin-top:10px; border-radius:10px;">
            <p style="margin-top:20px; font-size:12px; color:#ccc;">
                Thank you for using EventHub 🚀
            </p>
        </div>
    </body>
    </html>
    """
    send_email(email, "🎟 Your Event Ticket", content)


def sync_fixed_events():
    with open(os.path.join(BASE_DIR, "fixed_events.json"), encoding="utf-8") as file:
        fixed_events = json.load(file)

    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            for event in fixed_events:
                cursor.execute("SELECT * FROM event_list WHERE title=%s", (event["title"],))
                if cursor.fetchone():
                    continue
                cursor.execute(
                    """
                    INSERT INTO event_list(title,description,date,image,type,price,contact_email)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        event["title"],
                        event["description"],
                        event["date"],
                        event["image"],
                        event["type"],
                        event["price"],
                        "vijay635037@gmail.com",
                    ),
                )
        conn.commit()


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return make_response("", 204)
    return None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
    return response


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.name}), error.code
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("Unhandled request error", exc_info=error)
    if request.path.startswith("/api/"):
        return jsonify({"error": "The request could not be completed."}), 500
    return jsonify({"error": "The request could not be completed."}), 500


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/session")
def get_session():
    email = session.get("user")
    profile = None
    if email:
        with closing(get_db()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email=%s ORDER BY id DESC", (email,))
                profile = profile_json(cursor.fetchone())
    return jsonify({"user": profile, "admin": bool(session.get("admin"))})


@app.post("/api/auth/send-otp")
def send_otp():
    email = get_payload().get("email", "").strip()
    if not email:
        return api_error("Email is required.")

    otp = str(random.randint(100000, 999999))
    otp_time = time.time()
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
            "content-type": "application/json",
        },
        json={
            "sender": {"email": EMAIL_USER},
            "to": [{"email": email}],
            "subject": "OTP Verification",
            "htmlContent": (
                '<div style="font-family: Arial; padding:20px;">'
                '<h2 style="color:#2563eb;">OTP Verification</h2>'
                '<p>Your OTP is:</p>'
                f'<h1 style="color:#16a34a;">{otp}</h1>'
                '<p>This OTP is valid for limited time.</p></div>'
            ),
        },
        timeout=20,
    )
    response.raise_for_status()

    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users(email,otp,time,verified) VALUES(%s,%s,%s,0)",
                (email, otp, otp_time),
            )
        conn.commit()
    return jsonify({"message": "OTP sent.", "email": email})


@app.post("/api/auth/verify")
def verify_otp():
    payload = get_payload()
    email = payload.get("email", "").strip()
    otp = payload.get("otp", "").strip()
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT otp,time FROM users WHERE email=%s ORDER BY id DESC",
                (email,),
            )
            data = cursor.fetchone()
    if data is None:
        return api_error("No OTP found.", 404)
    if time.time() - data[1] > 300:
        return api_error("OTP expired.", 400)
    if otp != data[0]:
        return api_error("Wrong OTP.", 400)
    return jsonify({"message": "OTP verified.", "email": email})


@app.post("/api/auth/resend-otp")
def resend_otp():
    payload = get_payload()
    email = payload.get("email", "").strip()
    if not email:
        return api_error("Email is required.")

    otp = str(random.randint(100000, 999999))
    otp_time = time.time()
    html_content = f"""
    <div style="font-family: Arial; padding:20px;">
        <h2 style="color:#2563eb;">OTP Verification</h2>
        <p>Your OTP is:</p>
        <h1 style="color:#16a34a;">{otp}</h1>
        <p>This OTP is valid for limited time.</p>
    </div>
    """
    send_email(email, "OTP Verification", html_content)

    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET otp=%s,time=%s WHERE email=%s",
                (otp, otp_time, email),
            )
        conn.commit()
    return jsonify({"message": "OTP resent.", "email": email})


@app.post("/api/auth/signup")
def create_account():
    payload = get_payload()
    email = payload.get("email", "").strip()
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users SET name=%s,mobile=%s,password=%s,verified=1
                WHERE email=%s
                """,
                (
                    payload.get("name", ""),
                    payload.get("mobile", ""),
                    payload.get("password", ""),
                    email,
                ),
            )
        conn.commit()
    return jsonify({"message": "Account created.", "redirect": "/login_page"})


@app.post("/api/auth/login")
def login():
    payload = get_payload()
    email = payload.get("email", "").strip()
    password = payload.get("password", "")
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT name,password FROM users
                WHERE email=%s AND verified=1 ORDER BY id DESC
                """,
                (email,),
            )
            data = cursor.fetchone()
    if not data or data[1] != password:
        return api_error("Invalid Email or Password.", 401)
    session["user"] = email
    return jsonify({"message": "Logged in.", "redirect": "/dashboard"})


@app.post("/api/auth/admin-login")
def admin_login():
    payload = get_payload()
    if payload.get("username") != ADMIN_USER or payload.get("password") != ADMIN_PASS:
        return api_error("Invalid username or password.", 401)
    session["admin"] = True
    return jsonify({"message": "Logged in.", "redirect": "/admin"})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out.", "redirect": "/"})


@app.get("/api/events")
def get_events():
    error = user_required()
    if error:
        return error
    sync_fixed_events()
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM event_list ORDER BY id DESC")
            rows = cursor.fetchall()
            cursor.execute("SELECT * FROM users WHERE email=%s", (session["user"],))
            user = profile_json(cursor.fetchone())
    return jsonify({"events": [event_json(row) for row in rows], "user": user})


@app.get("/api/events/<int:event_id>")
def get_event(event_id):
    error = user_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM event_list WHERE id=%s", (event_id,))
            row = cursor.fetchone()
    if not row:
        return api_error("Event not found.", 404)
    return jsonify({"event": event_json(row)})


@app.post("/api/events/<int:event_id>/registrations")
def submit_registration(event_id):
    error = user_required()
    if error:
        return error
    payload = get_payload()
    email = session["user"]
    current_time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT title,type FROM event_list WHERE id=%s", (event_id,))
            event = cursor.fetchone()
            if not event:
                return api_error("Event not found.", 404)
            event_name, event_type = event
            cursor.execute(
                """
                INSERT INTO registrations(event_id,user_email,name,mobile,age,address,payment_status,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    event_id,
                    email,
                    payload.get("name", ""),
                    payload.get("mobile", ""),
                    payload.get("age", ""),
                    payload.get("address", ""),
                    "pending",
                    current_time,
                ),
            )
            if event_type == "free":
                unique_id = "EVT" + uuid.uuid4().hex[:6].upper()
                qr_filename = ticket_qr(unique_id)
                cursor.execute(
                    """
                    INSERT INTO events(user_email,event_name,event_image,qr_code,unique_id)
                    VALUES(%s,%s,%s,%s,%s)
                    """,
                    (email, event_name, "", os.path.join("static", "uploads", qr_filename), unique_id),
                )
                cursor.execute(
                    "UPDATE registrations SET payment_status='done' WHERE event_id=%s AND user_email=%s",
                    (event_id, email),
                )
        conn.commit()

    if event_type == "free":
        try:
            send_ticket_email(email, payload.get("name", ""), event_name, unique_id, qr_filename)
        except requests.RequestException:
            app.logger.exception("Ticket email delivery failed for %s", email)
        return jsonify({"message": "Registration successful.", "redirect": "/dashboard"})
    return jsonify({"message": "Registration recorded.", "redirect": f"/payment/{event_id}"})


@app.get("/api/events/<int:event_id>/payment")
def get_payment(event_id):
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT title, price FROM event_list WHERE id=%s", (event_id,))
            data = cursor.fetchone()
    if not data:
        return api_error("Event not found.", 404)

    upi_id = os.getenv("UPI_ID")
    if not upi_id:
        return api_error("UPI_ID must be configured on the backend.", 503)
    event_name, price = data
    upi_link = f"upi://pay%spa={upi_id}&pn={event_name}&am={price}"
    qr_filename = "payment_qr.png"
    qrcode.make(upi_link).save(os.path.join(UPLOAD_FOLDER, qr_filename))
    return jsonify(
        {
            "event_name": event_name,
            "price": price,
            "qr": media_url(qr_filename),
            "event_id": event_id,
            "upi_id": upi_id,
        }
    )


@app.post("/api/events/<int:event_id>/payment/confirm")
def confirm_payment(event_id):
    error = user_required()
    if error:
        return error
    email = session["user"]
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE registrations SET payment_status='done' WHERE event_id=%s AND user_email=%s",
                (event_id, email),
            )
            cursor.execute("SELECT title FROM event_list WHERE id=%s", (event_id,))
            event = cursor.fetchone()
            if not event:
                return api_error("Event not found.", 404)
            event_name = event[0]
            cursor.execute("SELECT name FROM users WHERE email=%s", (email,))
            row = cursor.fetchone()
            user_name = row[0] if row else email
            unique_id = "EVT" + uuid.uuid4().hex[:6].upper()
            qr_filename = ticket_qr(unique_id)
            cursor.execute(
                """
                INSERT INTO events(user_email,event_name,event_image,qr_code,unique_id)
                VALUES(%s,%s,%s,%s,%s)
                """,
                (email, event_name, "", os.path.join("static", "uploads", qr_filename), unique_id),
            )
        conn.commit()
    try:
        send_ticket_email(email, user_name, event_name, unique_id, qr_filename)
    except requests.RequestException:
        app.logger.exception("Ticket email delivery failed for %s", email)
    return jsonify({"message": "Payment successful; ticket generated.", "redirect": "/dashboard"})


@app.get("/api/history")
def get_history():
    error = user_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_list.title, event_list.type, event_list.price,
                       registrations.payment_status, registrations.created_at
                FROM registrations
                JOIN event_list ON registrations.event_id = event_list.id
                WHERE registrations.user_email=%s
                """,
                (session["user"],),
            )
            rows = cursor.fetchall()
    return jsonify(
        {
            "history": [
                {
                    "event": row[0],
                    "type": row[1],
                    "price": row[2],
                    "payment_status": row[3],
                    "created_at": row[4],
                }
                for row in rows
            ]
        }
    )


@app.get("/api/profile")
def get_profile():
    error = user_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email=%s", (session["user"],))
            user = cursor.fetchone()
    return jsonify({"user": profile_json(user)})


@app.put("/api/profile")
def update_profile():
    error = user_required()
    if error:
        return error
    payload = get_payload()
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET name=%s,password=%s WHERE email=%s",
                (payload.get("name", ""), payload.get("password", ""), session["user"]),
            )
        conn.commit()
    return jsonify({"message": "Profile updated."})


@app.post("/api/profile/image")
def upload_profile():
    error = user_required()
    if error:
        return error
    image = request.files.get("image")
    if not image or not image.filename:
        return api_error("Choose an image to upload.")
    filename = secure_filename(f"{session['user']}.png")
    image.save(os.path.join(UPLOAD_FOLDER, filename))
    path = os.path.join("static", "uploads", filename)
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET image=%s WHERE email=%s", (path, session["user"]))
        conn.commit()
    return jsonify({"message": "Profile image uploaded.", "image": media_url(filename)})


@app.get("/api/admin")
def get_admin_data():
    error = admin_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            cursor.execute("SELECT * FROM event_list")
            events = cursor.fetchall()
    return jsonify(
        {
            "users": [profile_json(user) for user in users],
            "events": [event_json(event) for event in events],
        }
    )


@app.post("/api/admin/events")
def add_event():
    error = admin_required()
    if error:
        return error
    payload = request.form
    image = request.files.get("image")
    image_path = ""
    if image and image.filename:
        filename = secure_filename(image.filename)
        image.save(os.path.join(UPLOAD_FOLDER, filename))
        image_path = os.path.join("static", "uploads", filename)

    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO event_list(title,description,date,image,type,price,contact_email)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    payload.get("title", ""),
                    payload.get("description", ""),
                    payload.get("date", ""),
                    image_path,
                    payload.get("type", ""),
                    int(payload.get("price") or 0),
                    payload.get("contact_email", ""),
                ),
            )
        conn.commit()
    return jsonify({"message": "Event created.", "redirect": "/admin"}), 201


@app.delete("/api/admin/events/<int:event_id>")
def delete_event(event_id):
    error = admin_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT title FROM event_list WHERE id=%s", (event_id,))
            data = cursor.fetchone()
            if data:
                cursor.execute("DELETE FROM registrations WHERE event_id=%s", (event_id,))
                cursor.execute("DELETE FROM events WHERE event_name=%s", (data[0],))
                cursor.execute("DELETE FROM event_list WHERE id=%s", (event_id,))
        conn.commit()
    return jsonify({"message": "Event deleted.", "redirect": "/admin"})


@app.delete("/api/admin/users/<path:email>")
def delete_user(email):
    error = admin_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE email=%s", (email,))
        conn.commit()
    return jsonify({"message": "User deleted.", "redirect": "/admin"})


@app.get("/api/events/<int:event_id>/registrations")
def get_registrations(event_id):
    error = admin_required()
    if error:
        return error
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT registrations.name, registrations.user_email,
                       registrations.mobile, registrations.age, registrations.address,
                       registrations.payment_status, event_list.title
                FROM registrations
                JOIN event_list ON registrations.event_id = event_list.id
                WHERE registrations.event_id=%s
                """,
                (event_id,),
            )
            rows = cursor.fetchall()
    return jsonify(
        {
            "registrations": [
                {
                    "name": row[0],
                    "email": row[1],
                    "mobile": row[2],
                    "age": row[3],
                    "address": row[4],
                    "payment_status": row[5],
                    "event": row[6],
                }
                for row in rows
            ]
        }
    )


@app.post("/api/register-event")
def register_event():
    error = user_required()
    if error:
        return error
    payload = request.form
    email = session["user"]
    image = request.files.get("image")
    image_path = ""
    if image and image.filename:
        filename = secure_filename(image.filename)
        image.save(os.path.join(UPLOAD_FOLDER, filename))
        image_path = os.path.join("static", "uploads", filename)
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO events(user_email,event_name,event_image,qr_code,unique_id)
                VALUES(%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    email,
                    payload.get("event", ""),
                    image_path,
                    "temp",
                    payload.get("unique_id", ""),
                ),
            )
            event_id = cursor.fetchone()[0]
            unique_id = payload.get("unique_id", "")
            qr_filename = f"event_{event_id}_qr.png"
            if not FRONTEND_URL:
                return api_error("FRONTEND_URL must be configured to generate ticket links.", 503)
            qrcode.make(f"{FRONTEND_URL}/scan/{unique_id}").save(
                os.path.join(UPLOAD_FOLDER, qr_filename)
            )
            cursor.execute(
                "UPDATE events SET qr_code=%s WHERE id=%s",
                (os.path.join("static", "uploads", qr_filename), event_id),
            )
        conn.commit()
    try:
        ticket_email = f"""
        <html>
        <body style="font-family: Arial; background:#0f2027; padding:20px; color:white;">
            <div style="max-width:500px; margin:auto; background:#1e3c72; padding:20px; border-radius:15px; text-align:center;">
                <h2>🎉 Registration Successful</h2>
                <p style="font-size:16px;">Hello <b>{payload.get('user_name', '')}</b>,</p>
                <p>You have successfully registered for:</p>
                <h3 style="color:#4ade80;">{payload.get('event_name', '')}</h3>
                <p><b>Ticket ID:</b> {unique_id}</p>
                <p style="margin-top:20px; font-size:12px; color:#ccc;">
                    Thank you for using EventHub 🚀
                </p>
            </div>
        </body>
        </html>
        """
        send_email(
            email,
            "🎟 Your Event Ticket",
            ticket_email,
        )
    except requests.RequestException:
        app.logger.exception("Ticket email delivery failed for %s", email)
    return jsonify({"message": "Event registered successfully.", "redirect": "/dashboard"})


@app.get("/api/tickets/<unique_id>")
def scan_ticket(unique_id):
    with closing(get_db()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.name,u.email,u.mobile,r.age,r.address,e.event_name
                FROM events e
                JOIN users u ON u.email = e.user_email
                LEFT JOIN registrations r ON r.user_email = u.email
                WHERE e.unique_id=%s
                """,
                (unique_id,),
            )
            data = cursor.fetchone()
    if not data:
        return api_error("Invalid ticket.", 404)
    return jsonify(
        {
            "ticket": {
                "name": data[0],
                "email": data[1],
                "mobile": data[2],
                "age": data[3],
                "address": data[4],
                "event_name": data[5],
                "ticket_id": unique_id,
            }
        }
    )


@app.get("/api/media/<path:filename>")
def get_media(filename):
    normalized_name = os.path.basename(filename.replace("\\", "/"))
    if not normalized_name or normalized_name != filename:
        return api_error("Media not found.", 404)
    for directory in (UPLOAD_FOLDER, MEDIA_SOURCE_FOLDER):
        if os.path.isfile(os.path.join(directory, normalized_name)):
            return send_from_directory(directory, normalized_name)
    return api_error("Media not found.", 404)


@app.post("/api/contact")
def contact():
    payload = get_payload()
    name = payload.get("name", "")
    email = payload.get("email", "")
    message = payload.get("message", "")
    if not all((name, email, message)):
        return api_error("Name, email, and message are required.")
    msg = EmailMessage()
    msg["Subject"] = "New Contact Message"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER
    msg.set_content(f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}")
    send_email(EMAIL_USER, "New Contact Message", msg.get_content())
    return jsonify({"message": "Message sent successfully.", "redirect": "/dashboard"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
