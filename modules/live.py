import streamlit as st
from supabase import Client


def render_live(supabase: Client, user: str, role: str, client: str, outlet: str, location: str):
    st.markdown("### 📡 Live")
    st.info("Live module — coming soon.")
