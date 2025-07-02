import socketio
import os
from redis import Redis

try:
    redis = Redis(host='213.199.34.84', port=6379)
    redis.ping()
    print("✅ Redis is connected and responding to ping")
except Exception as e:
    print("❌ Redis connection failed:", e)

mgr = socketio.AsyncRedisManager("redis://213.199.34.84:6379")

sio =socketio.AsyncServer(
    async_mode="asgi",
    client_manager=mgr,
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
    await sio.emit("message", f"Broadcast: {data}")  # remove `to=sid` to make it broadcast
