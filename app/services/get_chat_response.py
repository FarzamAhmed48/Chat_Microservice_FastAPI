from sqlalchemy import select
from openai import AsyncOpenAI
import os
from sqlalchemy import and_
from app.db.database import metadata,SessionLocal
# Initialize OpenAI / DeepSeek based on your need
openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Main function
async def get_chat_response(user_question,context_msg, preference_id, session_id,provider="OpenAI"):
    db=SessionLocal()
    try:
        messages_table = metadata.tables["messages"]
        prompts_table = metadata.tables["prompts"]

        # 1. Fetch context messages
        result = db.execute(
            select(
                messages_table.c.content,
                messages_table.c.sender,
                messages_table.c.created_at
            ).where(messages_table.c.session_id == session_id)
            .order_by(messages_table.c.created_at.asc())
        )
        context_messages = [dict(row._mapping) for row in result.fetchall()]


        # print("These are the messages of the context in get_chat_rtepsonse",context_messages)
        # 2. Convert DB messages to OpenAI-style format
        formatted_messages = [
            {"role": "user" if m["sender"] == "user" else "assistant", "content": m["content"]}
            for m in context_messages
        ]

        # 3. Get dynamic prompt from DB using preference_id
        result = db.execute(
            select(prompts_table) .where(and_(
            prompts_table.c.preference_id == preference_id,
            prompts_table.c.provider == provider
        )).order_by(prompts_table.c.created_at.asc())
        )
        prompt_rows = [dict(row._mapping) for row in result.fetchall()]


        if not prompt_rows:
            raise Exception(f"No prompts found for preference ID: {preference_id}")
        
        # Pick one randomly (like Node)
        import random
        prompt_template = random.choice(prompt_rows)["prompt"]

        print("THis is the selected prompt",prompt_template)
        final_prompt = prompt_template.replace("{message}", user_question)

        print("THis is the final user message",final_prompt)
        # 4. Append final user message
        formatted_messages.append({"role": "user", "content": final_prompt})

        # 5. Generate AI response (RAG-style context + prompt)
        response = await openai.chat.completions.create(
            model="gpt-4",
            messages=formatted_messages,
            temperature=0.7
        )

        answer = response.choices[0].message.content.strip()
        # print("This is the answer",answer)
        return answer

    except Exception as e:
        print("❌ Error in get_chat_response:", e)
        return "Something went wrong!"
