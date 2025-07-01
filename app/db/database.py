import os
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL=os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    raise ValueError("POSTGRES_URL not found in environment")
# DATABASE_URL = "postgresql://postgres:yourpassword@localhost:5432/yourdb"

# Create engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Reflect metadata
metadata = MetaData()
metadata.reflect(bind=engine)  # Load all tables dynamically

# Access tables dynamically like this:
# table = metadata.tables['your_table_name']
