# import socketio
# from app.services.chat_strategy import get_chat_response
# from app.db.database import get_db
# from dotenv import load_dotenv
# import os

# load_dotenv()

# sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
# connected_users = {}

# @sio.event
# async def connect(sid, environ):
#     print(f"Client connected: {sid}")

# @sio.event
# async def disconnect(sid):
#     print(f"Client disconnected: {sid}")
#     connected_users.pop(sid, None)

# @sio.event
# async def send_message(sid, data):
#     try:
#         print("Received message:", data)
#         db = get_db()
#         message = data.get("message")
#         preference_id = data.get("preference_id")
#         provider = data.get("provider", "OpenAI")

#         response = await get_chat_response(
#             message, preference_id, db, sio, sid, provider
#         )
#         print("Final response:", response)
#     except Exception as e:
#         print("Error handling chat:", str(e))
#         await sio.emit("receive_message", "Something went wrong", room=sid)



import socketio
import os
# mgr = socketio.AsyncRedisManager("redis://localhost:6379")

sio =socketio.AsyncServer(
    async_mode="asgi",
    # client_manager=mgr,
    cors_allowed_origins="*"
)


@sio.event
async def connect(sid, environ):
    print(f"✅ Client connected: {sid}")
    await sio.emit("message", f"Hello from server!", to=sid)

@sio.event
async def disconnect(sid):
    print(f"❌ Client disconnected: {sid}")

@sio.event
async def message(sid, data):
    print(f"📨 Message from {sid}: {data}")
    await sio.emit("message", f"Echo: {data}", to=sid)