import os
from dotenv import load_dotenv
from supabase import create_client as supabase_init
import psycopg2

load_dotenv()

def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("host"),
        dbname=os.getenv("dbname", "postgres"),
        user=os.getenv("user", "postgres"),
        password=os.getenv("password"),
        port=os.getenv("port", "5432"),
        sslmode="require"
    )


def init_supabase():
    url: str = os.getenv("url")
    key: str = os.getenv("key")
    return supabase_init(url, key)


def get_client_id(client_name, supabase):

    try:
        response = (
            supabase
            .table("clients")
            .select("id, client_name")
            .eq("client_name", client_name)
            .execute()
        )
    except Exception as e:
        msg = f"⚠️ Failed to fetch client '{client_name}' from clients table: {e}"
        return {
            "status": "error",
            "message": msg,
            "client_id": None
        }

    rows = response.data if response and hasattr(response, "data") else []

    if not rows:
        msg = f"⚠️ Client '{client_name}' was not found in the clients table"
        return {
            "status": "error",
            "message": msg,
            "client_id": None
        }

    if len(rows) > 1:
        msg = f"⚠️ Multiple clients found for '{client_name}' in the clients table"
        return {
            "status": "error",
            "message": msg,
            "client_id": None
        }

    return {
            "status": "ok",
            "client_id": rows[0]["id"]
        }