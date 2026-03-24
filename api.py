import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from groq import Groq
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# ================= INIT =================
app = FastAPI()

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change later to your Netlify URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= GROQ =================
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise Exception("GROQ_API_KEY not set")

client = Groq(api_key=api_key)

# ================= FIREBASE (FIXED) =================
if not firebase_admin._apps:
    firebase_key = os.getenv("FIREBASE_KEY")

    if not firebase_key:
        raise Exception("FIREBASE_KEY not set")

    try:
        cred_dict = json.loads(firebase_key)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        raise Exception(f"Firebase init failed: {str(e)}")

db = firestore.client()

# ================= MODEL =================
class ChatRequest(BaseModel):
    message: str
    userId: str
    clientId: str

# ================= HEALTH =================
@app.get("/")
def home():
    return {"status": "ok"}

# ================= CHAT =================
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant."}
        ]

        # 🔥 LOAD LAST 3 MESSAGES
        chats = db.collection("clients") \
            .document(req.clientId) \
            .collection("users") \
            .document(req.userId) \
            .collection("chats") \
            .order_by("timestamp", direction=firestore.Query.DESCENDING) \
            .limit(3) \
            .stream()

        history = [c.to_dict() for c in chats]
        history.reverse()

        for h in history:
            messages.append({"role": "user", "content": h.get("message", "")})
            messages.append({"role": "assistant", "content": h.get("response", "")})

        messages.append({"role": "user", "content": req.message})

        # 🔥 AI CALL
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages
        )

        reply = completion.choices[0].message.content

        # 🔥 SAVE CHAT
        db.collection("clients") \
            .document(req.clientId) \
            .collection("users") \
            .document(req.userId) \
            .collection("chats") \
            .add({
                "message": req.message,
                "response": reply,
                "timestamp": datetime.utcnow()
            })

        return {"reply": reply}

    except Exception as e:
        print("ERROR:", str(e))
        return {"reply": str(e)}
