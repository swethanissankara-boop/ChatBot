from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, emit
import sqlite3
from database import init_db
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import request, jsonify
import io
import base64
import os
import uuid
from openai import OpenAI

emotion_process = None

stress_map = {
    "Low": 1,
    "Medium": 2,
    "High": 3
}




client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


app = Flask(__name__)
app.secret_key = "supersecretkey"
socketio = SocketIO(app, cors_allowed_origins="*")
init_db()


# ---------------- STRESS CLASSIFIER (AI UPGRADE) ----------------
def classify_stress(message):
    try:
        # We ask OpenAI to act strictly as an analyzer, not a chatbot.
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert psychological text analyzer. Read the student's message and determine their current exam stress level. You must respond with EXACTLY ONE WORD from this list: 'Low', 'Medium', or 'High'. Consider burnout, exhaustion, and avoidance as High stress. Do not add any punctuation or extra text."
                },
                {"role": "user", "content": message}
            ],
            temperature=0.0,  # We set this to 0 so the AI acts like a strict calculator, not a creative writer
            max_tokens=10
        )
        
        # Clean up the response to ensure it perfectly matches our database needs
        level = response.choices[0].message.content.strip().capitalize()
        
        # Double-check that the AI followed the rules
        if level in ["Low", "Medium", "High"]:
            return level
        else:
            return "Medium" # Fallback if the AI says something weird
            
    except Exception as e:
        print(f"Error classifying stress: {e}")
        return "Medium" # Safe fallback if the internet disconnects

def categorize_student(student_id):
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT study_hours, sleep_hours, confidence_level
        FROM student_profile
        WHERE student_id=?
    """, (student_id,))

    study, sleep, confidence = cursor.fetchone()

    if int(study) < 2 or int(sleep) < 5:
        category = "High Risk"
    elif confidence.lower() == "low":
        category = "Anxious"
    else:
        category = "Stable"

    cursor.execute("""
        UPDATE student_profile
        SET category=?
        WHERE student_id=?
    """, (category, student_id))

    conn.commit()
    conn.close()


def save_bot_message(student_id, message):
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (student_id, role, message) VALUES (?, ?, ?)",
            (student_id, "assistant", message)
        )
        conn.commit()


def get_latest_emotion(student_id):

    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT emotion
        FROM emotion_logs
        WHERE student_id=?
        ORDER BY timestamp DESC
        LIMIT 1
        """, (student_id,))

        result = cursor.fetchone()

    if result:
        return result[0]

    return "Neutral"


# ---------------- HOME PAGE ----------------
@app.route("/")
def home():
    return render_template("home.html")




# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        academic_level = request.form["academic_level"]
        password = request.form["password"]

        conn = sqlite3.connect("students.db")
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO students (name, email, academic_level, password)
                VALUES (?, ?, ?, ?)
            """, (name, email, academic_level, password))
            conn.commit()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return "Email already exists!"
        finally:
            conn.close()

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("students.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, name, academic_level FROM students WHERE email=? AND password=?",
            (email, password)
        )
        student = cursor.fetchone()
        conn.close()

        if student:
            session["student_id"] = student[0]
            session["student_name"] = student[1]
            session["academic_level"] = student[2]
            return redirect(url_for("chat"))
        else:
            return "Invalid credentials!"

    return render_template("login.html")


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    # -------- STEP 0: Get Latest Emotion --------

    latest_emotion = get_latest_emotion(student_id)


    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # ---------------- GET STUDENT STAGE ----------------
    cursor.execute("SELECT stage FROM students WHERE id=?", (student_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return redirect(url_for("login"))

    stage = result[0]

    if stage != "onboarding":
        conn.close()
        return redirect(url_for("chat"))

    # ---------------- SAVE ANSWER ----------------
    if request.method == "POST":
        answer = request.form["answer"]
        question_id = request.form["question_id"]

        cursor.execute("""
            INSERT INTO student_answers (student_id, question_id, answer)
            VALUES (?, ?, ?)
        """, (student_id, question_id, answer))

        conn.commit()
        conn.close()
        return redirect(url_for("onboarding"))

    # ---------------- GET FIRST UNANSWERED QUESTION ----------------
    cursor.execute("""
        SELECT id, question_text 
        FROM onboarding_questions
        WHERE id NOT IN (
            SELECT question_id FROM student_answers WHERE student_id=?
        )
        ORDER BY id ASC
        LIMIT 1
    """, (student_id,))

    question = cursor.fetchone()

    # ---------------- CALCULATE PROGRESS ----------------
    cursor.execute("SELECT COUNT(*) FROM onboarding_questions")
    total_questions = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM student_answers
        WHERE student_id=?
    """, (student_id,))
    answered_count = cursor.fetchone()[0]

    progress_percent = 0
    if total_questions > 0:
        progress_percent = int((answered_count / total_questions) * 100)

    # ---------------- IF ALL QUESTIONS COMPLETED ----------------
    if not question:

        # Fetch all answers
        cursor.execute("""
            SELECT oq.question_key, sa.answer
            FROM student_answers sa
            JOIN onboarding_questions oq ON sa.question_id = oq.id
            WHERE sa.student_id=?
        """, (student_id,))

        answers = dict(cursor.fetchall())

        exam_name = answers.get("exam_name")
        exam_date = answers.get("exam_date")
        study_hours = int(answers.get("study_hours", 0))
        sleep_hours = int(answers.get("sleep_hours", 0))
        confidence = answers.get("confidence_level", "Low")

        # Insert or update student_profile
        cursor.execute("""
            INSERT OR REPLACE INTO student_profile
            (student_id, exam_name, exam_date, study_hours, sleep_hours, confidence_level)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            exam_name,
            exam_date,
            study_hours,
            sleep_hours,
            confidence
        ))

        # -------- Categorization Logic --------
        if study_hours < 2 and confidence.lower() == "low":
            category = "High Risk"
        elif confidence.lower() == "low":
            category = "Anxious"
        else:
            category = "Stable"

        # Update category
        cursor.execute("""
            UPDATE student_profile
            SET category=?
            WHERE student_id=?
        """, (category, student_id))

        # Change stage to active_chat
        cursor.execute("""
            UPDATE students
            SET stage='active_chat'
            WHERE id=?
        """, (student_id,))

        conn.commit()
        conn.close()

        return redirect(url_for("chat"))

    conn.close()

    return render_template(
        "onboarding.html",
        question_id=question[0],
        question_text=question[1],
        progress_percent=progress_percent
    )

# ---------------- CHAT PAGE ----------------
@app.route("/chat")
def chat():

    # 🔹 Step 1: Check if user is logged in
    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    # 🔹 Step 2: Connect to database
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # 🔹 Step 3: Check student's onboarding stage
    cursor.execute(
        "SELECT stage FROM students WHERE id=?",
        (student_id,)
    )
    result = cursor.fetchone()

    # If still onboarding → redirect
    if result and result[0] == "onboarding":
        conn.close()
        return redirect(url_for("onboarding"))

    # 🔹 Step 4: Load chat history
    cursor.execute("""
        SELECT id,role, message
        FROM chat_history
        WHERE student_id=?
        ORDER BY timestamp ASC
    """, (student_id,))

    chats = cursor.fetchall()

    # 🔹 Step 5: Get latest emotion
    cursor.execute("""
        SELECT emotion
        FROM emotion_logs
        WHERE student_id=?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (student_id,))

    emotion_result = cursor.fetchone()

    # Normalize emotion
    emotion_map = {
        "happy": "Happy",
        "sad": "Sad",
        "angry": "Angry",
        "fear": "Stressed",
        "disgust": "Stressed",
        "surprise": "Neutral",
        "neutral": "Neutral"
    }

    if emotion_result:
        latest_emotion = emotion_map.get(emotion_result[0].lower(), "Neutral")
    else:
        latest_emotion = "Neutral"

    # 🔹 Step 6: Close database
    conn.close()

    # 🔹 Step 7: Check risk alert
    risk_alert = session.pop("risk_alert", False)

    # 🔹 Step 8: Render chat page
    return render_template(
        "chat.html",
        name=session.get("student_name"),
        level=session.get("academic_level"),
        chats=chats,
        risk_alert=risk_alert,
        emotion=latest_emotion
   # ⭐ IMPORTANT ADDITION
    )
   

# ---------------- SEND MESSAGE ----------------
@app.route("/send", methods=["POST"])
def send():
    if "student_id" not in session:
        return redirect(url_for("login"))

    import datetime
    import json

    student_id = session["student_id"]
    user_message = request.form["message"]

    # -------- STEP 0: Get Emotion --------
    latest_emotion = get_latest_emotion(student_id)

    # -------- Normalize Emotion --------
    emotion_map = {
        "happy": "Happy",
        "sad": "Sad",
        "angry": "Angry",
        "fear": "Stressed",
        "disgust": "Stressed",
        "surprise": "Neutral",
        "neutral": "Neutral"
    }

    latest_emotion = emotion_map.get(str(latest_emotion).lower(), "Neutral")

    # -------- Detect Study Plan Request --------
    if "study plan" in user_message.lower():
        session["plan_mode"] = True

    # -------- STEP 1: Save user message --------
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (student_id, role, message) VALUES (?, ?, ?)",
            (student_id, "user", user_message)
        )
        conn.commit()

    # -------- STEP 2: Classify Stress --------
    stress_level = classify_stress(user_message)

    # -------- Emotion + Stress Fusion --------
    if latest_emotion in ["Sad", "Stressed", "Angry"]:
        if stress_level == "Low":
            stress_level = "Medium"
        elif stress_level == "Medium":
            stress_level = "High"

    # -------- Save stress --------
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO stress_tracking (student_id, stress_level) VALUES (?, ?)",
            (student_id, stress_level)
        )
        conn.commit()

    # -------- STEP 3: Fetch Chat History --------
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, message
            FROM chat_history
            WHERE student_id=?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (student_id,))
        history = cursor.fetchall()

    history.reverse()

    # -------- STEP 4: Fetch Profile --------
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT exam_name, exam_date, study_hours, sleep_hours,
                   confidence_level, category
            FROM student_profile
            WHERE student_id=?
        """, (student_id,))
        profile = cursor.fetchone()

    if profile:
        exam_name, exam_date, study_hours, sleep_hours, confidence, category = profile
    else:
        exam_name = exam_date = confidence = category = "Unknown"
        study_hours = sleep_hours = 0

    # -------- Days Left --------
    try:
        exam_dt = datetime.datetime.strptime(exam_date, "%Y-%m-%d")
        days_left = (exam_dt - datetime.datetime.now()).days
        if days_left < 0:
            days_left = 0
    except:
        days_left = 0

    # -------- STEP 5: Stress History --------
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT stress_level
            FROM stress_tracking
            WHERE student_id=?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (student_id,))
        recent_stress = cursor.fetchall()

    current_stress = recent_stress[0][0] if recent_stress else "Low"

    # -------- Risk Detection --------
    risk_alert = False

    if len(recent_stress) >= 3:
        if all(s[0] == "High" for s in recent_stress[:3]):
            risk_alert = True

    if latest_emotion in ["Sad", "Stressed", "Angry"] and current_stress == "High":
        risk_alert = True

    # -------- Stress Trend --------
    if len(recent_stress) >= 2:
        if recent_stress[0][0] == "High" and recent_stress[1][0] != "High":
            stress_trend_direction = "Increasing"
        elif recent_stress[0][0] == "Low" and recent_stress[1][0] != "Low":
            stress_trend_direction = "Decreasing"
        else:
            stress_trend_direction = "Stable"
    else:
        stress_trend_direction = "Stable"

    # -------- Coping Strategy --------
    if risk_alert:
        coping_instruction = """
Student is at high risk.
Guide them through 4-7-8 breathing.
Use calming tone.
"""
    elif latest_emotion == "Sad":
        coping_instruction = """
Student appears sad.
Encourage gently and provide emotional support.
"""
    elif latest_emotion == "Stressed":
        coping_instruction = """
Student looks stressed.
Suggest breathing exercise and short break.
"""
    elif latest_emotion == "Angry":
        coping_instruction = """
Student seems frustrated.
Suggest taking a short break or a walk.
"""
    elif latest_emotion == "Happy":
        coping_instruction = """
Student is in a positive mood.
Encourage productive study.
"""
    elif stress_trend_direction == "Increasing":
        coping_instruction = """
Stress increasing.
Suggest slowing down and taking breaks.
"""
    elif current_stress == "Medium":
        coping_instruction = """
Suggest Pomodoro technique.
"""
    else:
        coping_instruction = """
Encourage maintaining routine.
"""

    # -------- STUDY PLAN MODE --------
    study_plan_instruction = ""

    if session.get("plan_mode"):

        if "subjects_count" not in session:
            try:
                session["subjects_count"] = int(user_message)
                save_bot_message(student_id, "Got it 👍 What are the subjects you are preparing for?")
                return redirect(url_for("chat"))
            except:
                save_bot_message(student_id, "How much time you have for preparation?")
                return redirect(url_for("chat"))

                save_bot_message(student_id, "Which subject you are weak in?")
                return redirect(url_for("chat"))

        if "weak_subject" not in session:
            session["weak_subject"] = user_message
            save_bot_message(
                student_id,
                f"Great! Preparing plan considering {user_message} as weak subject."
            )
            return redirect(url_for("chat"))

        subjects_count = session.get("subjects_count")
        weak_subject = session.get("weak_subject")

        study_plan_instruction = f"""
Create a structured study plan.

Days left: {days_left}
Study hours per day: {study_hours}
Subjects: {subjects_count}
Weak subject: {weak_subject}

Return ONLY JSON.
"""

        session["plan_mode"] = False
        session.pop("subjects_count", None)
        session.pop("weak_subject", None)

# -------- FETCH LATEST BRAIN DUMP --------
    latest_dump = "None"
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        # Check if the table exists first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='brain_dumps'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT thought FROM brain_dumps
                WHERE student_id=? ORDER BY timestamp DESC LIMIT 1
            """, (student_id,))
            dump_result = cursor.fetchone()
            if dump_result:
                latest_dump = dump_result[0]


 # -------- SYSTEM PROMPT --------
    system_prompt = f"""
You are a warm, highly empathetic AI helping students manage exam stress.

IMPORTANT RESPONSE RULES:
1. ACTIVE LISTENING FIRST: Before giving any advice, your first sentence MUST validate the user's specific feeling (e.g., "Staring at a blank page for hours sounds incredibly frustrating...").
2. ANTI-VAGUENESS: If the user's message is shorter than 5 words or is vague (e.g., "I'm done", "tired"), DO NOT offer advice. Instead, ask a gentle clarifying question (e.g., "Do you mean you finished your tasks, or are you feeling burnt out?").
3. EXTREME CLARITY: Speak in simple, everyday English (like talking to a 14-year-old). NEVER write paragraphs longer than 3 sentences. 
4. VISUAL FORMATTING: Heavily use bullet points (•) and **bold text** for key ideas so it is easy to read.
5. THE "ONE ACTION" RULE: If you suggest a coping strategy, give exactly ONE simple, actionable step. Do not overwhelm them with multiple options.
6. SCAFFOLDING ("DO IT WITH ME"): Never just tell the student to go do something alone. Ask them to do the FIRST tiny step right now in the chat with you. Always end your response with a highly specific, low-effort question. (e.g., "What is the very first heading in your textbook chapter? Type it here and we'll start.")
7. KEEP IT SHORT: Absolute maximum of 4-6 lines of text total.



🧠 THE STRATEGY PLAYBOOK (Analyze the user's core problem and apply EXACTLY ONE of these tools):
- IF THEY ARE STUDYING INEFFICIENTLY (rereading, losing focus, forgetting): Use **Tactical Strategies**. Suggest the Pomodoro technique (25 mins focus, 5 min break) or the Feynman Technique (ask them to explain the concept to you simply in the chat).
- IF THEY ARE PANICKING ABOUT FAILING (doomsday thinking, overwhelming anxiety): Use **Cognitive Reframing**. Guide them through De-catastrophizing (asking what the actual worst-case scenario is) or Micro-Stepping (hiding the syllabus and picking the single easiest 10-minute task).
- IF THEY ARE EXHAUSTED (low sleep, burning out): Use **Biological Triage**. Aggressively prioritize sleep over cramming. Explain that the brain cannot physically store new memories without sleep. Suggest a 90-minute nap.

⏳ TIMELINE AWARENESS (Check the 'Days Left' variable):
- IF DAYS LEFT == 1 (The Night Before): REFUSE to give new study advice. Tell them cramming now will hurt their memory. Focus strictly on wind-down routines, packing their bag, and confidence-building.
- IF DAYS LEFT <= 0 (Exam Day / Post-Exam): The exam is here or done. Tell them "The pen is down, you cannot change the answers now." Suggest they use the Brain Dump to let go of their worries or play a game to decompress.


Student Context:
Exam: {exam_name}
Days Left: {days_left}
Study Hours: {study_hours}
Sleep Hours: {sleep_hours}

Current Stress Level: {current_stress}
Stress Trend: {stress_trend_direction}
Detected Emotion: {latest_emotion}

Secret Context (The user recently vented this feeling. Do NOT explicitly say "I read your brain dump", but use this context to be deeply empathetic):
Recent feeling: "{latest_dump}"

Coping Strategy to apply (if appropriate):
{coping_instruction}

{study_plan_instruction}

SPECIAL CASE:
If study_plan_instruction exists → respond ONLY in JSON
"""

    # -------- BUILD MESSAGES --------
    messages = [{"role": "system", "content": system_prompt}]

    for role, msg in history:
        messages.append({"role": role, "content": msg})

    # -------- OPENAI CALL --------
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7
    )

    bot_response = response.choices[0].message.content.strip()

    # -------- JSON → HTML --------
    if study_plan_instruction:
        try:
            cleaned = bot_response.replace("```json", "").replace("```", "").strip()

            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            json_string = cleaned[start:end]

            json_data = json.loads(json_string)

            html = "<h3>📅 Weekday Study Plan</h3>"
            html += "<table class='plan-table'><tr><th>Time</th><th>Task</th></tr>"

            for row in json_data["weekday_plan"]:
                html += f"<tr><td>{row['time']}</td><td>{row['task']}</td></tr>"

            html += "</table>"

            html += "<h3>📅 Weekend Plan</h3>"
            html += "<table class='plan-table'><tr><th>Time</th><th>Task</th></tr>"

            for row in json_data["weekend_plan"]:
                html += f"<tr><td>{row['time']}</td><td>{row['task']}</td></tr>"

            html += "</table>"

            html += f"<p><b>📝 Weekly Mock:</b> {json_data['weekly_mock']}</p>"
            html += f"<p><b>🔁 Revision Strategy:</b> {json_data['revision_strategy']}</p>"

            bot_response = html

        except Exception as e:
            print("JSON ERROR:", e)

    # -------- SAVE BOT MESSAGE --------
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (student_id, role, message) VALUES (?, ?, ?)",
            (student_id, "assistant", bot_response)
        )
        conn.commit()

    session["risk_alert"] = risk_alert

    return redirect(url_for("chat"))

# ========================================================
# 🎮 REAL-TIME MULTIPLAYER & PEER CHAT LOGIC
# ========================================================
import uuid

waiting_players = [] 

@socketio.on("find_match")
def handle_find_match():
    global waiting_players
    student_name = session.get("student_name", "Student")
    player_sid = request.sid

    # Prevent matching with yourself if you double-click
    waiting_players = [p for p in waiting_players if p["sid"] != player_sid]

    if len(waiting_players) > 0:
        opponent = waiting_players.pop(0)
        room_id = str(uuid.uuid4())
        
        # 🚨 FIX 1: The Server securely forces BOTH players into the room right now!
        join_room(room_id, sid=player_sid)       # Puts Player 2 in
        join_room(room_id, sid=opponent['sid'])  # Puts Player 1 in
        
        emit("match_found", {
            "room": room_id, 
            "message": f"Match found! You are playing against {opponent['name']}.",
            "role": "⭕" 
        }, to=player_sid)
        
        emit("match_found", {
            "room": room_id, 
            "message": f"Match found! You are playing against {student_name}.",
            "role": "❌" 
        }, to=opponent['sid'])

    else:
        waiting_players.append({"sid": player_sid, "name": student_name})
        emit("waiting", {"message": "Waiting for another student to join..."})

@socketio.on("play_move")
def handle_play_move(data):
    room = data["room"]
    emit("receive_move", data, to=room, include_self=False)

@socketio.on("send_peer_message")
def handle_peer_message(data):
    room = data["room"]
    # 🚨 FIX 2: We get the exact name from the frontend to stop session mix-ups
    sender_name = data.get("sender", "Student") 
    
    emit("receive_peer_message", {
        "sender": sender_name,
        "text": data["text"]
    }, to=room, include_self=False)

# ---------------- DIGITAL BRAIN DUMP (SHREDDER) ----------------
@app.route("/shred", methods=["POST"])
def shred_thought():
    if "student_id" not in session:
        return {"status": "error"}, 401

    data = request.get_json()
    thought = data.get("thought", "").strip()
    student_id = session["student_id"]

    if thought:
        with sqlite3.connect("students.db") as conn:
            cursor = conn.cursor()
            # 1. Create the table safely if this is the first time running it
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brain_dumps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER,
                    thought TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 2. Save the stressful thought
            cursor.execute(
                "INSERT INTO brain_dumps (student_id, thought) VALUES (?, ?)",
                (student_id, thought)
            )
            conn.commit()

    return {"status": "success"}

@app.route("/dashboard")
def dashboard():
    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # -------- PART 1: Stress Distribution --------
    cursor.execute("""
        SELECT stress_level, COUNT(*) 
        FROM stress_tracking 
        WHERE student_id=? 
        GROUP BY stress_level
    """, (student_id,))

    data = cursor.fetchall()
    stress_counts = {"Low": 0, "Medium": 0, "High": 0}
    for level, count in data:
        stress_counts[level] = count

    # Create distribution graph
    plt.figure()
    plt.bar(stress_counts.keys(), stress_counts.values(), color=['#2ecc71', '#f39c12', '#e74c3c'])
    plt.xlabel("Stress Level")
    plt.ylabel("Count")
    plt.title("Stress Level Distribution")

    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()

    # -------- PART 2: Fetch Stress Trend Data --------
    cursor.execute("""
        SELECT stress_level
        FROM stress_tracking
        WHERE student_id=?
        ORDER BY timestamp ASC
        LIMIT 10
    """, (student_id,))
    stress_data = cursor.fetchall()

    # -------- PART 3: Convert Stress Levels to Scores --------
    stress_map = {"Low": 1, "Medium": 2, "High": 3}
    stress_scores = [stress_map.get(s[0], 1) for s in stress_data]

    # Determine dominant stress level for insights
    if any(stress_counts.values()):
        dominant_stress = max(stress_counts, key=stress_counts.get)
    else:
        dominant_stress = "Low"

    if dominant_stress == "High":
        insight_message = "You’ve been under high stress recently. Try short breaks and deep breathing exercises."
    elif dominant_stress == "Medium":
        insight_message = "Stress is moderate. Keep a balanced schedule and maintain focus."
    else:
        insight_message = "Stress is low. Keep up your good habits!"

    # -------- PART 4: Fetch Brain Dump History --------
    recent_dumps = []
    try:
        cursor.execute("""
            SELECT thought, timestamp 
            FROM brain_dumps 
            WHERE student_id=? 
            ORDER BY timestamp DESC 
            LIMIT 5
        """, (student_id,))
        recent_dumps = cursor.fetchall()
    except sqlite3.OperationalError:
        # Table might not exist yet if no thoughts were shredded
        recent_dumps = []

    # Close connection ONLY after all queries are done
    conn.close()

    # -------- PART 5: Final Single Return --------
    return render_template(
        "dashboard.html",
        stress_counts=stress_counts,
        graph_url=graph_url,
        stress_scores=stress_scores,
        insight_message=insight_message,
        recent_dumps=recent_dumps
    )
@app.route("/update_emotion", methods=["POST"])
def update_emotion():
    if "student_id" not in session:
        return {"status": "error"}

    data = request.get_json()

    student_id = session["student_id"]   # ✅ FIXED
    emotion = data.get("emotion")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO emotion_logs (student_id, emotion) VALUES (?, ?)",
        (student_id, emotion)
    )

    conn.commit()
    conn.close()

    return {"status": "success"}

import subprocess
@app.route("/start_emotion", methods=["POST"])
def start_emotion():
    global emotion_process

    if emotion_process is None:
        emotion_process = subprocess.Popen([
            r"C:\Users\SWETHA SUSHMA\majorproject\venv\Scripts\python.exe",
            "camera_emotion.py"
        ])

    return {"status": "started"}

@app.route("/stop_emotion", methods=["POST"])
def stop_emotion():
    global emotion_process

    if emotion_process:
        emotion_process.terminate()
        emotion_process = None

    return {"status": "stopped"}

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- EDIT PROMPT (REWIND TIMELINE) ----------------
@app.route("/delete_from_message", methods=["POST"])
def delete_from_message():
    if "student_id" not in session:
        return {"status": "error"}, 401
        
    data = request.get_json()
    message_id = data.get("message_id")
    student_id = session["student_id"]
    
    with sqlite3.connect("students.db") as conn:
        cursor = conn.cursor()
        # Delete the edited message AND everything that came after it
        cursor.execute(
            "DELETE FROM chat_history WHERE id >= ? AND student_id=?",
            (message_id, student_id)
        )
        conn.commit()
        
    return {"status": "success"}



# ---------------- CLEAR CHAT ----------------
@app.route("/clear_chat")
def clear_chat():
    if "student_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM chat_history WHERE student_id=?",
        (session["student_id"],)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("chat"))


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
