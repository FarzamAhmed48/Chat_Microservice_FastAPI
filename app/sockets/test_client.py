import asyncio
import socketio

sio1 = socketio.AsyncClient()
sio2 = socketio.AsyncClient()

@sio1.event
async def connect():
    print("✅ [Client 1] Connected to server")
    await sio1.emit("message", "Hello from Python Client 1")

@sio1.event
async def message(data):
    print("📨 [Client 1] Received:", data)

@sio1.event
async def disconnect():
    print("❌ [Client 1] Disconnected")


@sio2.event
async def connect():
    print("✅ [Client 2] Connected to server")
    await sio2.emit("message", "Hello from Python Client 2")

@sio2.event
async def message(data):
    print("📨 [Client 2] Received:", data)

@sio2.event
async def disconnect():
    print("❌ [Client 2] Disconnected")


async def main():
    try:
        await sio1.connect("http://localhost:8000")
        print("✅ [Client 1] Connected")
    except Exception as e:
        print("❌ [Client 1] Connection failed:", e)

    try:
        await sio2.connect("http://localhost:8001")
        print("✅ [Client 2] Connected")
    except Exception as e:
        print("❌ [Client 2] Connection failed:", e)

    await asyncio.gather(sio1.wait(), sio2.wait())


asyncio.run(main())
