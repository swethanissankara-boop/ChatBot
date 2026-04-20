import sqlite3

def init_db():
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # ---------------- STUDENTS TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        academic_level TEXT,
        stage TEXT DEFAULT 'onboarding',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ---------------- STUDENT ANSWERS TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        question_id INTEGER,
        answer TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(question_id) REFERENCES onboarding_questions(id)
    )
    """)

    # ---------------- STUDENT PROFILE TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER UNIQUE,
        exam_name TEXT,
        exam_date TEXT,
        study_hours INTEGER,
        sleep_hours INTEGER,
        confidence_level TEXT,
        category TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )
    """)

    # ---------------- ONBOARDING QUESTIONS TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS onboarding_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_text TEXT NOT NULL,
        question_key TEXT NOT NULL,
        question_order INTEGER NOT NULL
    )
    """)

    # Insert default onboarding questions only if empty
    cursor.execute("SELECT COUNT(*) FROM onboarding_questions")
    count = cursor.fetchone()[0]

    if count == 0:
        questions = [
            ("What exam are you preparing for?", "exam_name", 1),
            ("When is your exam date?", "exam_date", 2),
            ("How many hours do you study daily?", "study_hours", 3),
            ("How many hours do you sleep daily?", "sleep_hours", 4),
            ("How confident are you about this exam? (Low/Medium/High)", "confidence_level", 5)
        ]

        cursor.executemany("""
        INSERT INTO onboarding_questions (question_text, question_key, question_order)
        VALUES (?, ?, ?)
        """, questions)

    # ---------------- CHAT HISTORY TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        role TEXT CHECK(role IN ('user','assistant')),
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )
    """)

    # ---------------- STRESS TRACKING TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stress_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        stress_level TEXT CHECK(stress_level IN ('Low','Medium','High')),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )
    """)

    # ---------------- EMOTION LOGS TABLE ----------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emotion_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        emotion TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id)
    )
    """)

    conn.commit()
    conn.close()