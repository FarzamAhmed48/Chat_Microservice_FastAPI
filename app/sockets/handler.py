import socketio
from socketio.async_server import AsyncServer
from redis import Redis
from socketio.redis_manager import RedisManager
from app.services.agent import agent
from app.db.database import SessionLocal, metadata
from sqlalchemy import text, select, insert, func, update
import json
import orjson
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
    print("data is this",data)
    try:
        chat_id = data.get("chatId")
        user_id = data.get("userId")
        user_question = data.get("userQuestion")
        preference = data.get("selectedInterest", "General")
        provider = data.get("provider", "OpenAI")
        print("CHATID USERID USERQUES",chat_id,user_id,user_question,preference,provider)
        if not chat_id or not user_id or not user_question:
            await sio.emit("chat:error", {"message": "Missing required fields"}, to=sid)
            return

        history_table = metadata.tables["messages"]
        print("history is this",history_table)
        result = db.execute(
            select(func.max(history_table.c.sequence)).where(history_table.c.session_id == chat_id)
        ).first()
        print("result is this",result)   
        max_seq = result[0] or 0

        db.execute(insert(history_table).values(
            chat_id=chat_id,
            user_id=user_id,
            content=user_question,
            role="user",
            sequence=max_seq + 1,
            preference=preference,
            created_at=func.now()
        ))

        db.commit()

        # Context + AI Response
        deps = {"db": db, "preference_id": preference}
        result = await agent.run(user_question, deps=deps, tools=["get_context"])
        ai_reply = str(result.data)

        db.execute(insert(history_table).values(
            chat_id=chat_id,
            user_id=user_id,
            content=ai_reply,
            role="assistant",
            sequence=max_seq + 2,
            preference=preference,
            created_at=func.now()
        ))

        # Title Generation
        if max_seq == 0:
            completion = await openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Generate a 2-4 word title summarizing this chat."},
                    {"role": "user", "content": user_question}
                ]
            )
            new_title = completion.choices[0].message.content.strip()
            chats_table = metadata.tables["chats"]
            db.execute(
                update(chats_table)
                .where(chats_table.c.id == chat_id)
                .values(title=new_title, updated_at=func.now())
            )

        db.commit()

        await sio.emit("chat:response", {
            "chatId": chat_id,
            "userQuestion": user_question,
            "response": ai_reply
        }, room=chat_id)

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