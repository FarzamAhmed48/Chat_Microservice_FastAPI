import socketio
from socketio.async_server import AsyncServer
from redis import Redis
from socketio.redis_manager import RedisManager
from app.services.agent import agent
from app.db.database import SessionLocal, metadata
from sqlalchemy import text, select, insert, func, update
import json
import orjson
from app.services.get_chat_response import get_chat_response
from openai import AsyncOpenAI
import os

def clean_keys(obj):
    if isinstance(obj, list):
        return [clean_keys(item) for item in obj]
    elif isinstance(obj, dict):
        return {str(k): clean_keys(v) for k, v in obj.items()}
    else:
        return obj

def orjson_serialize(obj):
    return orjson.loads(orjson.dumps(clean_keys(obj)))
# Redis connection
redis = Redis(host='213.199.34.84', port=6379)
mgr = RedisManager("redis://213.199.34.84:6379")

# Socket.IO server with proper CORS configuration
sio = AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",  # Allow all origins for testing
    # client_manager=mgr,
    logger=True,  # Enable logging for debugging
    engineio_logger=True
)

# OpenAI for title generation
openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@sio.on("join_chat")
async def join_chat(sid, session_id):
    await sio.enter_room(sid, session_id)
    print(f"✅ {sid} joined room {session_id}")


@sio.on("chat:new_session")
async def new_session(sid, data):
    db = SessionLocal()
    try:
        user_id = data.get("userId")
        if not user_id:
            await sio.emit("chat:error", {"message": "User ID required"}, to=sid)
            return

        chats_table = metadata.tables["chats"]
        stmt = insert(chats_table).values(
            user_id=user_id,
            title="New Chat",
            created_at=func.now(),
            updated_at=func.now()
        ).returning(chats_table.c.id, chats_table.c.title)

        result = db.execute(stmt)
        db.commit()
        new_chat = result.fetchone()
        await sio.emit("chat:new_session", dict(new_chat._mapping), to=sid)

    except Exception as e:
        print("❌ Error in chat:new_session", e)
        await sio.emit("chat:error", {"message": "Failed to create session"}, to=sid)
    finally:
        db.close()


@sio.on("chat:message")
async def send_message(sid, data):
    db = SessionLocal()
    try:
        session_id = data.get("chatId") or data.get("sessionId")
        user_id = data.get("userId")
        user_question = data.get("userQuestion") or data.get("message")
        preference = data.get("selectedInterest") or data.get("preference_id", "General")
        images = data.get("images", [])
        
        if not session_id or not user_id:
            await sio.emit("chat:error", {"message": "Missing session ID or user ID"}, to=sid)
            return

        messages_table = metadata.tables["messages"]

        # ✅ Insert image messages
        if images and isinstance(images, list):
            for img in images:
                url = img.get("url")
                if url:
                    db.execute(insert(messages_table).values(
                        content=url,
                        sender="user",
                        session_id=session_id,
                        created_at=func.now()
                    ))

        # ✅ Insert user text message
        if user_question:
            db.execute(insert(messages_table).values(
                content=user_question,
                sender="user",
                session_id=session_id,
                created_at=func.now()
            ))

        db.commit()

        # ✅ Get all messages for AI
        all_msgs_result = db.execute(
            select(messages_table).where(messages_table.c.session_id == session_id).order_by(messages_table.c.created_at.asc())
        )
        all_messages = [dict(row._mapping) for row in all_msgs_result.fetchall()]
        messages_str = orjson_serialize(all_messages)
        print("These are the printed messages",messages_str)
        # ✅ AI response
        ai_reply = await get_chat_response(user_question,messages_str, preference, session_id)

        db.execute(insert(messages_table).values(
            content=ai_reply,
            sender="ai",
            session_id=session_id,
            created_at=func.now()
        ))

        # ✅ Count messages
        count_result = db.execute(
            select(func.count()).select_from(messages_table).where(messages_table.c.session_id == session_id)
        ).scalar()

        # ✅ Generate title if first interaction (like in Node.js)
        if count_result == 2:
            completion = await openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Generate a very brief 2-4 word title summarizing this chat conversation. Return only the title text."
                    },
                    {
                        "role": "user",
                        "content": user_question
                    }
                ]
            )
            new_title = completion.choices[0].message.content.strip()
            chats_table = metadata.tables["chat_sessions"]
            db.execute(
                update(chats_table)
                .where(chats_table.c.id == session_id)
                .values(title=new_title, updated_at=func.now())
            )

        db.commit()

        # ✅ Emit the AI response back to the client
        await sio.emit("chat:response", {
            "chatId": session_id,
            "userQuestion": user_question,
            "response": ai_reply
        }, room=session_id)

    except Exception as e:
        print("❌ Error in chat:message", e)
        await sio.emit("chat:error", {"message": "Failed to process message"}, to=sid)
    finally:
        db.close()
@sio.on("get:chat:history")
async def get_chat_history(sid, data):
    db = SessionLocal()
    try:
        user_id = data.get("userId")
        # chat_id = data.get("chatId")
        interest = data.get("selectedInterest")
        print("Print the received data in get_chat_history",user_id,interest)
        if not user_id:
            await sio.emit("chat:error", {"message": "User ID required"}, to=sid)
            return

        else:
            chats_table = metadata.tables["chat_sessions"]
            result = db.execute(
                select(
                    chats_table.c.id,
                    chats_table.c.title,
                    chats_table.c.preference_id,
                    chats_table.c.updated_at
                ).where(chats_table.c.user_id == user_id)
                .order_by(chats_table.c.updated_at.desc())
            )
            chats = [dict(row._mapping) for row in result.fetchall()]
            await sio.emit("get:chat:history", {"chats": orjson_serialize(chats)}, to=sid)

    except Exception as e:
        print("❌ Error in get:chat:history", e)
        await sio.emit("chat:error", {"message": "Failed to fetch chat history"}, to=sid)
    finally:
        db.close()


# Add handlers for client events (matching client-side event names)
@sio.on("send_message")
async def handle_send_message(sid, data):
    """Handle send_message event from client"""
    print(f"📨 Received send_message from {sid}: {data}")
    
    # Transform client data to match your existing chat:message handler
    transformed_data = {
        "chatId": data.get("sessionId"),  # Map sessionId to chatId
        "userId": data.get("userId", "default_user"),  # Add default if missing
        "userQuestion": data.get("message"),
        "selectedInterest": data.get("preference_id", "General")
    }
    
    # Call your existing handler
    await send_message(sid, transformed_data)


@sio.on("receive_session")
async def handle_receive_session(sid, data):
    """Handle receive_session event from client"""
    print(f"📋 Received receive_session from {sid}: {data}")
    print("data this is the data",data)
    # Transform client data to match your existing get:chat:history handler
    transformed_data = {
        "userId": data.get("user_id"),
        "selectedInterest": data.get("preference_id")
    }
    
    # Call your existing handler
    await get_chat_history(sid, transformed_data)


@sio.event
async def connect(sid, environ):
    print(f"✅ Client connected: {sid}")
    await sio.emit("message", "Hello from server!", to=sid)
    return True


@sio.event
async def disconnect(sid):
    print(f"❌ Client disconnected: {sid}")