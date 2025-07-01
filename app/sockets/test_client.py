import socketio

sio = socketio.AsyncClient()

@sio.event
async def connect():
    print("✅ Connected to server")
    await sio.emit("message", "Hello from Python client")

@sio.event
async def message(data):
    print("📨 Received:", data)

@sio.event
async def disconnect():
    print("❌ Disconnected")

import asyncio

async def main():
    await sio.connect("http://localhost:8000")
    await sio.wait()

asyncio.run(main())
