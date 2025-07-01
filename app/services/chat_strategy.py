from app.utils.session import update_user_chat_history, get_user_chat_history
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

async def openai_strategy(message, preference_id, db, sio, sid):
    user_id = preference_id
    updated_history = update_user_chat_history(user_id, {"role": "user", "content": message})

    response = ""
    completion = await openai.ChatCompletion.acreate(
        model="gpt-4",
        messages=updated_history,
        stream=True
    )

    async for chunk in completion:
        delta = chunk.choices[0].delta.get("content")
        if delta:
            response += delta
            await sio.emit("receive_message", delta, room=sid)

    update_user_chat_history(user_id, {"role": "assistant", "content": response})
    return response

def get_strategy(provider):
    strategies = {
        "OpenAI": openai_strategy,
        # Add Gemini, DeepSeek here
    }
    return strategies.get(provider, openai_strategy)

async def get_chat_response(message, preference_id, db, sio, sid, provider="OpenAI"):
    strategy = get_strategy(provider)
    return await strategy(message, preference_id, db, sio, sid)
