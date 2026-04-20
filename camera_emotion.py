from fer.fer import FER
import cv2
import requests
import time

detector = FER(mtcnn=True)
cap = cv2.VideoCapture(0)

last_sent = 0   # to control request frequency

while True:
    ret, frame = cap.read()
    if not ret:
        break

    result = detector.top_emotion(frame)

    if result:
        emotion, score = result
    else:
        emotion = "neutral"

    # Show emotion on screen (for demo)
    cv2.putText(frame, emotion, (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # Send to Flask every 3 seconds (IMPORTANT FIX)
    current_time = time.time()
    if current_time - last_sent > 3:
        try:
            requests.post(
                "http://127.0.0.1:5000/update_emotion",
                json={"emotion": emotion, "student_id": 1}
            )
            print("Sent:", emotion)
        except:
            print("Server not reachable")

        last_sent = current_time

    cv2.imshow("Emotion Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()