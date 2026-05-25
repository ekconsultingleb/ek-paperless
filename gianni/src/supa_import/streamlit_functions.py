from datetime import datetime
import streamlit as st
import pandas as pd


def get_client_list(supabase):
    try:
        response = supabase.table("branches").select("outlet").execute()
        return [row["outlet"] for row in response.data]
    except Exception as e:
        st.error(f"Error fetching clients: {e}")
        return []

def get_period_options():
    return pd.period_range(
        start=datetime.now() - pd.DateOffset(years=2), 
        end=datetime.now(), 
        freq='M'
    ).strftime('%Y-%m').tolist()[::-1]