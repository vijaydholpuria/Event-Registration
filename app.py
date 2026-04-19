from http import server

from flask import flash
from flask import Flask,render_template,request,session,redirect,url_for
import random
import smtplib
import time
from lxml import html
import qrcode
import os
import datetime
from email.message import EmailMessage
import psycopg2

# from dotenv import load_dotenv
# load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")

app = Flask(__name__)
app.secret_key="secret123"
current_time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

UPLOAD_FOLDER="static/uploads"
os.makedirs(UPLOAD_FOLDER,exist_ok=True)

# --------DATABASE CONNECTION--------
def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


# send email function
import requests
import os

def send_email(to_email, subject, html_content):

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json"
    }

    data = {
        "sender": {"email": os.getenv("EMAIL_USER")},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }

    response = requests.post(url, json=data, headers=headers)
    print("EMAIL RESPONSE:", response.text)

# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login_page")
def login_page():
    return render_template("login.html")

# ---------------- ADMIN LOGIN ----------------

@app.route("/admin_login",methods=["GET","POST"])
def admin_login():

    if request.method=="POST":

        username=request.form["username"]
        password=request.form["password"]

        if username == ADMIN_USER and password == ADMIN_PASS:
            session["admin"]=True
            return redirect("/admin")

    return render_template("admin_login.html")

# ---------------- ADMIN PANEL ----------------

@app.route("/admin")
def admin():

    if "admin" not in session:
        return redirect("/admin_login")
    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("SELECT * FROM users")
    users=cursor.fetchall()

    cursor.execute("SELECT * FROM event_list")
    events = cursor.fetchall()

    conn.close()

    return render_template("admin.html",users=users,events=events)

# ---------------- ADD EVENT ----------------
@app.route("/add_event",methods=["POST"])
def add_event():

    title=request.form["title"]
    description=request.form["description"]
    date=request.form["date"]
    type=request.form["type"]
    price=request.form["price"]
    contact_email=request.form["contact_email"]

    image=request.files["image"]

    path="static/uploads/"+image.filename
    image.save(path)
    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("""
    INSERT INTO event_list(title,description,date,image,type,price,contact_email)
    VALUES(%s,%s,%s,%s,%s,%s,%s)
    """,(title,description,date,path,type,price,contact_email))
    conn.commit()
    conn.close()

    return redirect("/admin")


# ---------------- VIEW REGISTRATIONS ----------------
@app.route("/view_registrations/<int:event_id>")
def view_registrations(event_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT registrations.name,
           registrations.user_email,
           registrations.mobile,
           registrations.age,
           registrations.address,
           registrations.payment_status,
           event_list.title
    FROM registrations
    JOIN event_list ON registrations.event_id = event_list.id
    WHERE registrations.event_id=%s
    """, (event_id,))

    data = cursor.fetchall()
    conn.close()

    return render_template("registrations.html", data=data)
# ---------------- SUBMIT REGISTRATION ----------------
@app.route("/submit_registration/<int:event_id>", methods=["POST"])
def submit_registration(event_id):

    if "user" not in session:
        return redirect("/")

    name = request.form["name"]
    mobile = request.form["mobile"]
    age = request.form["age"]
    address = request.form["address"]
    email = session["user"]
    current_time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

    conn = get_db()
    cursor = conn.cursor()

    # get event type
    cursor.execute("SELECT title,type FROM event_list WHERE id=%s", (event_id,))
    event_data = cursor.fetchone()

    if not event_data:
        conn.close()
        return "Event not found"

    event_name, event_type = event_data

    # insert registration
    cursor.execute("""
    INSERT INTO registrations(event_id,user_email,name,mobile,age,address,payment_status,created_at)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
    """,(event_id,email,name,mobile,age,address,"pending",current_time))

    conn.commit()

    # -------- FREE EVENT --------
    if event_type == "free":

        import uuid

        unique_id = "EVT" + uuid.uuid4().hex[:6].upper()

        # QR data (IMPORTANT)
        qr_data = request.host_url + "scan/" + unique_id

        qr = qrcode.make(qr_data)

        qr_path = UPLOAD_FOLDER + "/" + unique_id + ".png"
        qr.save(qr_path)
        qr_url = request.host_url + qr_path

        # save in events table
        cursor.execute("""
        INSERT INTO events(user_email,event_name,event_image,qr_code,unique_id)
        VALUES(%s,%s,%s,%s,%s)
        """,(email,event_name,"",qr_path,unique_id))

        # mark as paid/done
        cursor.execute("""
        UPDATE registrations SET payment_status='done'
        WHERE event_id=%s AND user_email=%s
        """,(event_id,email))

        conn.commit()
        conn.close()

        # -------- EMAIL --------
        try:
            html = f"""
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
            
            send_email(email, "🎟 Your Event Ticket", html)
            

            flash("Registration Successful 🎉")
            conn.close()
            return redirect("/dashboard")
    
        except Exception as e:
            print("SENDING EMAIL TO:", email)
            print("EMAIL_USER:", EMAIL_USER)
            print("EMAIL ERROR:", e)
            flash("Registration Successful (email failed) 🎉")
            conn.close()
            return redirect("/dashboard")

    else:
        conn.close()
        return redirect("/payment/" + str(event_id))
# ---------------- REGISTER FORM ----------------
@app.route("/register_form/<int:event_id>")
def register_form(event_id):

    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM event_list WHERE id=%s", (event_id,))
    event = cursor.fetchone()

    conn.close()

    if not event:
        return "Event not found"

    return render_template("register_form.html", event=event, event_id=event_id)
    

# ---------------- GENERATE PAYMENT QR ----------------
@app.route("/payment/<int:event_id>")
def payment(event_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT title, price FROM event_list WHERE id=%s", (event_id,))
    data = cursor.fetchone()

    if not data:
        conn.close()
        return "Event not found"

    event_name, price = data

    # QR generate
    upi_link = f"upi://pay%spa=7851894027@ybl&pn={event_name}&am={price}"

    qr = qrcode.make(upi_link)

    qr_path = "static/uploads/payment_qr.png"
    qr.save(qr_path)

    conn.close()

    return render_template("payment.html",
                           event_name=event_name,
                           price=price,
                           qr_path=qr_path,
                           event_id=event_id
                           )

# ---------------- CONFIRM PAYMENT ----------------
@app.route("/confirm_payment/<int:event_id>")
def confirm_payment(event_id):

    if "user" not in session:
        return redirect("/")

    email = session["user"]

    conn = get_db()
    cursor = conn.cursor()

    # mark payment done
    cursor.execute("""
    UPDATE registrations SET payment_status='done'
    WHERE event_id=%s AND user_email=%s
    """,(event_id,email))

    # get event name
    cursor.execute("SELECT title FROM event_list WHERE id=%s", (event_id,))
    event_name = cursor.fetchone()[0]

    import uuid
    unique_id = "EVT" + uuid.uuid4().hex[:6].upper()

    qr_data = request.host_url + "scan/" + unique_id
    qr = qrcode.make(qr_data)

    qr_path = UPLOAD_FOLDER + "/" + unique_id + ".png"
    qr.save(qr_path)
    qr_url = request.host_url + qr_path

    # save ticket
    cursor.execute("""
    INSERT INTO events(user_email,event_name,event_image,qr_code,unique_id)
    VALUES(%s,%s,%s,%s,%s)
    """,(email,event_name,"",qr_path,unique_id))

    conn.commit()
    conn.close()

    # EMAIL
    try:
        # fetch user name to avoid undefined variable in email template
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE email=%s", (email,))
        row = cursor.fetchone()
        conn.close()
        user_name = row[0] if row else email

        html = f"""
        <html>
        <body style="font-family: Arial; background:#0f2027; padding:20px; color:white;">
        
            <div style="max-width:500px; margin:auto; background:#1e3c72; padding:20px; border-radius:15px; text-align:center;">
        
                <h2>🎉 Registration Successful</h2>
        
                <p style="font-size:16px;">Hello <b>{user_name}</b>,</p>
        
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
        
        send_email(email, "🎟 Your Event Ticket", html)

    except Exception as e:
        print("SENDING EMAIL TO:", email)
        print("EMAIL_USER:", EMAIL_USER)
        print("EMAIL ERROR:", e)

    flash("Payment Successful & Ticket Generated 🎉")
    return redirect("/dashboard")
# ---------------- REGISTRATION HISTORY ----------------
@app.route("/history")
def history():

    if "user" not in session:
        return redirect("/")

    email = session["user"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT event_list.title, event_list.type, event_list.price,
           registrations.payment_status, registrations.created_at
    FROM registrations
    JOIN event_list ON registrations.event_id = event_list.id
    WHERE registrations.user_email=%s
    """,(email,))

    data = cursor.fetchall()
    conn.close()

    return render_template("history.html", data=data)
# ---------------- DELETE USER ----------------

@app.route("/delete/<email>")
def delete(email):

    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("DELETE FROM users WHERE email=%s",(email,))

    conn.commit()
    conn.close()

    return redirect("/admin")

# ---------------- DELETE EVENT ----------------
@app.route("/delete_event/<int:id>")
def delete_event(id):

    conn = get_db()
    cursor = conn.cursor()

    # pehle event ka name lo
    cursor.execute("SELECT title FROM event_list WHERE id=%s", (id,))
    data = cursor.fetchone()

    if data:
        event_name = data[0]

        # sab tables se delete karo
        cursor.execute("DELETE FROM registrations WHERE event_id=%s", (id,))
        cursor.execute("DELETE FROM events WHERE event_name=%s", (event_name,))
        cursor.execute("DELETE FROM event_list WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")
# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- SEND OTP ----------------

@app.route("/send_otp", methods=["POST"])
def send_otp():

    email = request.form["email"]

    otp = str(random.randint(100000, 999999))
    otp_time = time.time()

    import requests

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json"
    }

    data = {
        "sender": {"email": os.getenv("EMAIL_USER")},
        "to": [{"email": email}],
        "subject": "OTP Verification",
        "htmlContent": f"""
        <div style="font-family: Arial; padding:20px;">
            <h2 style="color:#2563eb;">OTP Verification</h2>
            <p>Your OTP is:</p>
            <h1 style="color:#16a34a;">{otp}</h1>
            <p>This OTP is valid for limited time.</p>
        </div>
        """
    }

    response = requests.post(url, json=data, headers=headers)
    print("EMAIL RESPONSE:", response.text)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO users(email,otp,time,verified)
    VALUES(%s,%s,%s,0)
    """, (email, otp, otp_time))

    conn.commit()
    conn.close()

    return render_template("verify.html", email=email)

# ---------------- VERIFY OTP ----------------

@app.route("/verify",methods=["POST"])
def verify():

    email=request.form["email"]
    otp=request.form["otp"]
    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("""
    SELECT otp,time FROM users
    WHERE email=%s
    ORDER BY id DESC
    """,(email,))

    data=cursor.fetchone()
    conn.close()

    if data is None:
        return "No OTP found"

    db_otp,db_time=data

    if time.time()-db_time>300:
        return "OTP Expired"

    if otp==db_otp:
        return render_template("signup.html",email=email)

    return "Wrong OTP"

# ---------------- RESEND OTP ----------------

@app.route("/resend_otp",methods=["POST"])
def resend_otp():

    email=request.form["email"]

    otp=str(random.randint(100000,999999))
    otp_time=time.time()

    import requests

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json"
    }

    data = {
        "sender": {"email": os.getenv("EMAIL_USER")},
        "to": [{"email": email}],
        "subject": "OTP Verification",
        "htmlContent": f"""
        <div style="font-family: Arial; padding:20px;">
            <h2 style="color:#2563eb;">OTP Verification</h2>
            <p>Your OTP is:</p>
            <h1 style="color:#16a34a;">{otp}</h1>
            <p>This OTP is valid for limited time.</p>
        </div>
        """
    }
    message="Your new OTP is "+otp
    server.sendmail(os.getenv("EMAIL_USER"), email, message)

    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("""
    UPDATE users
    SET otp=%s,time=%s
    WHERE email=%s
    """,(otp,otp_time,email))

    conn.commit()
    conn.close()

    return render_template("verify.html",email=email)

# ---------------- CREATE ACCOUNT ----------------

@app.route("/create_account",methods=["POST"])
def create_account():

    email=request.form["email"]
    name=request.form["name"]
    mobile=request.form["mobile"]
    password=request.form["password"]

    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("""
    UPDATE users
    SET name=%s,mobile=%s,password=%s,verified=1
    WHERE email=%s
    """,(name,mobile,password,email))

    conn.commit()
    conn.close()

    return redirect("/login_page")

# ---------------- LOGIN ----------------

@app.route("/login",methods=["POST"])
def login():

    email=request.form["email"]
    password=request.form["password"]
    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("""
    SELECT name,password FROM users
    WHERE email=%s AND verified=1
    ORDER BY id DESC
    """,(email,))

    data=cursor.fetchone()
    conn.close()

    if data and data[1]==password:

        session["user"]=email

        return redirect("/dashboard")

    return "Invalid Email or Password"

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM event_list")
    events = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE email=%s", (session["user"],))
    user = cursor.fetchone()

    conn.close()

    return render_template("dashboard.html",
                           name=user[4],   # name
                           events=events,
                           user=user)      

# ---------------- REGISTER EVENT ----------------

@app.route("/register_event",methods=["POST"])
def register_event():

    if "user" not in session:
        return redirect("/")

    email=request.form["email"]
    event=request.form["event"]
    image=request.files.get("image")
    user_name=request.form["user_name"]
    unique_id=request.form["unique_id"]
    event_name=request.form["event_name"]

    if image and image.filename!="":
        path=UPLOAD_FOLDER+"/"+image.filename
        image.save(path)
    else:
        path=""

    conn=get_db()
    cursor=conn.cursor()

    cursor.execute("""
    INSERT INTO events(user_email,event_name,event_image,qr_code,unique_id)
    VALUES(%s,%s,%s,%s,%s) RETURNING id
    """,(email,event,path,"temp",unique_id))

    event_id = cursor.fetchone()[0]

    qr_data = request.host_url + "scan/" + unique_id
    qr=qrcode.make(qr_data)

    qr_path=UPLOAD_FOLDER+"/event_"+str(event_id)+"_qr.png"
    qr.save(qr_path)

    cursor.execute("""
    UPDATE events SET qr_code=%s WHERE id=%s
    """,(qr_path,event_id))

    conn.commit()
    conn.close()

    try:

        html = f"""
        <html>
        <body style="font-family: Arial; background:#0f2027; padding:20px; color:white;">
        
            <div style="max-width:500px; margin:auto; background:#1e3c72; padding:20px; border-radius:15px; text-align:center;">
        
                <h2>🎉 Registration Successful</h2>
        
                <p style="font-size:16px;">Hello <b>{user_name}</b>,</p>
        
                <p>You have successfully registered for:</p>
        
                <h3 style="color:#4ade80;">{event_name}</h3>
        
                <p><b>Ticket ID:</b> {unique_id}</p>
        
                <hr style="margin:20px 0;">
        
                <p>📌 Show your ticket at entry</p>
        
                <p style="margin-top:20px; font-size:12px; color:#ccc;">
                    Thank you for using EventHub 🚀
                </p>
        
            </div>
        
        </body>
        </html>
        """
        
        send_email(email, "🎟 Your Event Ticket", html)

    except Exception as e:
        print("EMAIL ERROR:",e)

    flash("Event Registered Successfully")
    return redirect("/dashboard")

# ---------------- QR SCAN ----------------

@app.route("/scan/<unique_id>")
def scan(unique_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT u.name,u.email,u.mobile,r.age,r.address,e.event_name
    FROM events e
    JOIN users u ON u.email = e.user_email
    LEFT JOIN registrations r ON r.user_email = u.email
    WHERE e.unique_id=%s
    """,(unique_id,))

    data = cursor.fetchone()
    conn.close()

    if not data:
        return "Invalid Ticket ❌"

    name,email,mobile,age,address,event_name = data

    return render_template("scan_result.html",
        name=name,
        email=email,
        mobile=mobile,
        age=age,
        address=address,
        event_name=event_name,
        ticket_id=unique_id
    )

# ---------------- PROFILE ----------------

@app.route("/profile")
def profile():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=%s", (session["user"],))
    user = cursor.fetchone()

    conn.close()

    return render_template("profile.html", 
                           name=user[4],
                           user=user)

# ---------------- UPDATE PROFILE ----------------
@app.route("/update_profile", methods=["POST"])
def update_profile():

    name = request.form["name"]
    password = request.form["password"]

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE users SET name=%s, password=%s
    WHERE email=%s
    """, (name, password, session["user"]))

    conn.commit()
    conn.close()

    return redirect("/profile")

# ---------------- UPLOAD PROFILE IMAGE ----------------

@app.route("/upload_profile", methods=["POST"])
def upload_profile():
    if "user" not in session:
        return redirect("/")

    image = request.files["image"]
    filename = session["user"] + ".png"
    path = "static/uploads/" + filename
    image.save(path)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET image=%s WHERE email=%s",
                   (path, session["user"]))

    conn.commit()
    conn.close()

    return redirect("/profile")
#--------contact------------------------
@app.route("/contact", methods=["GET","POST"])
def contact():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        message = request.form["message"]

        try:
            msg = EmailMessage()
            msg["Subject"] = "New Contact Message"
            msg["From"] = EMAIL_USER
            msg["To"] = EMAIL_USER

            msg.set_content(f"""
        Name: {name}
        Email: {email}
        
        Message:
        {message}
        """)

            send_email(EMAIL_USER, "New Contact Message", msg.get_content())

        except Exception as e:
            print("CONTACT ERROR:", e)

        flash("Message Sent Successfully 👍")
        return redirect("/dashboard")

    return render_template("contact.html")
# ---------------- RUN ----------------

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
