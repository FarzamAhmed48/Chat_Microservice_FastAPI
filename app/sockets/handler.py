import socketio
from socketio.async_server import AsyncServer
from redis import Redis
from socketio.redis_manager import RedisManager  # ✅ Correct import
from app.services.agent import agent
from app.db.database import SessionLocal, metadata
from sqlalchemy import text, select, insert, func, update
import json
from openai import AsyncOpenAI
import os
# Redis connection
redis = Redis(host='213.199.34.84', port=6379)
mgr = RedisManager("redis://213.199.34.84:6379")

# Socket.IO server
sio =AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    client_manager=mgr
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
        chat_id = data.get("chatId")
        user_id = data.get("userId")
        user_question = data.get("userQuestion")
        preference = data.get("selectedInterest", "General")
        provider = data.get("provider", "OpenAI")

        if not chat_id or not user_id or not user_question:
            await sio.emit("chat:error", {"message": "Missing required fields"}, to=sid)
            return

        history_table = metadata.tables["chat_history"]

        result = db.execute(
            select(func.max(history_table.c.sequence)).where(history_table.c.chat_id == chat_id)
        ).first()

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
        chat_id = data.get("chatId")
        interest = data.get("selectedInterest")

        if not user_id:
            await sio.emit("chat:error", {"message": "User ID required"}, to=sid)
            return

        if chat_id:
            history_table = metadata.tables["chat_history"]
            query = select([
                history_table.c.id,
                history_table.c.content,
                history_table.c.role,
                history_table.c.sequence,
                history_table.c.preference,
                history_table.c.created_at,
                history_table.c.metadata
            ]).where(history_table.c.chat_id == chat_id)

            if interest:
                query = query.where(history_table.c.preference == interest)

            result = db.execute(query.order_by(history_table.c.sequence.asc()))
            history = [dict(row._mapping) for row in result.fetchall()]
            await sio.emit("get:chat:history", {"chatHistory": history}, to=sid)
        else:
            chats_table = metadata.tables["chats"]
            result = db.execute(
                select([
                    chats_table.c.id,
                    chats_table.c.title,
                    chats_table.c.created_at,
                    chats_table.c.updated_at
                ]).where(chats_table.c.user_id == user_id)
                .order_by(chats_table.c.updated_at.desc())
            )
            chats = [dict(row._mapping) for row in result.fetchall()]
            await sio.emit("get:chat:history", {"chats": chats}, to=sid)

    except Exception as e:
        print("❌ Error in get:chat:history", e)
        await sio.emit("chat:error", {"message": "Failed to fetch chat history"}, to=sid)
    finally:
        db.close()


@sio.event
async def connect(sid, environ):
    print(f"✅ Client connected: {sid}")
    await sio.emit("message", "Hello from server!", to=sid)
    return True  # Explicitly allow the connection

@sio.event
async def disconnect(sid):
    print(f"❌ Client disconnected: {sid}")
