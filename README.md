# 🧠 AI-Based Exam Stress Support Chatbot

> An AI-powered study companion that uses real-time emotion detection to help students conquer exam anxiety, build personalized study plans, and prevent academic burnout.

## 🚀 Overview
Exam season shouldn't mean sacrificing mental health. This application is a multimodal AI study buddy that seamlessly blends academic coaching with mental health triage. It doesn't just tell you *what* to study; it actively monitors your well-being through your webcam and steps in with interactive coping mechanisms when you are on the verge of burnout.

## ✨ Features
* **Context-Aware AI Chat:** A conversational agent powered by the GPT API that provides tutoring, comfort, and study strategies based on your unique academic profile.
* **📸 Real-Time Emotion Detection:** Uses the user's webcam to analyze facial expressions. The AI combines this visual data with text input to deliver deeply empathetic, emotionally intelligent responses.
* **📅 Smart Study Plan Generator:** Automatically builds personalized, actionable study schedules in clean Markdown tables based on exam dates and weak subjects.
* **🎮 Interactive Coping Tools:** Features physics-based relaxation tools like a "Worry Jar" for chaotic thoughts, a "Brain Dump Shredder" to destroy anxieties, and mini-games like Tic-Tac-Toe for cognitive breaks.
* **🤝 Peer Break Room:** A real-time, anonymous matchmaking system (via WebSockets) that pairs stressed students together for mutual support and quick game sessions.

## 🛠️ Tech Stack
* **Backend:** Python, Flask
* **Frontend:** Vanilla JavaScript, HTML5, CSS3
* **Database:** SQLite
* **APIs & Libraries:** OpenAI API, Socket.IO (WebSockets), Marked.js

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/yourusername/exam-stress-chatbot.git](https://github.com/yourusername/exam-stress-chatbot.git)
   cd exam-stress-chatbo
   
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate

3. **Install dependencies:**
   ````bash
   pip install -r requirements.txt

4. **Environment Variables:**
    ```bash
   OPENAI_API_KEY=your_api_key_here
Create a .env file in the root directory and add your OpenAI API key:

5. **Run the application:**
   ```bash
   python app.py
The app will be available at http://127.0.0.1:5000

