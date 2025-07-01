# from fastapi import FastAPI
# # from app.api.chat_routes import router as chat_router
# import uvicorn
# from app.sockets.handler import sio

# app=FastAPI()
# app.include_router(chat_router,prefix="/chat",tags=["Chat"])
# asgi_app=sio.ASGIApp(sio,app)

# app.get("/")
# def root():
#     return {"message":"Chat Microservice is running"}


from typing import Union
from fastapi import FastAPI,Depends
from sqlalchemy.orm import Session
from app.db.database import metadata, SessionLocal,engine  # ⬅️ import your reflected DB
from sqlalchemy import text
from app.sockets.handler import sio
import socketio
app= FastAPI()
asgi_app = socketio.ASGIApp(sio,other_asgi_app=app)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))  # test query
            print("✅ Database connected successfully")
    except Exception as e:
        print("❌ Database connection failed:", e)


@app.get("/")
async def read_root():
    return {"message": "Socket.IO + Redis is working!"}

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    users_table = metadata.tables["users"]    # access the reflected "users" table
    result = db.execute(users_table.select())# run SELECT * FROM users
    rows = result.fetchall()                  # fetch all rows from result
    return [dict(row._mapping) for row in rows]  # convert to list of dicts and return


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
