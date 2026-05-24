import streamlit as st
from modules.sales_purchase import push_sales_purchase

st.set_page_config(page_title="Push to Sales and Purchase", layout="wide")

st.title("Sales and Purchase")

user = "Gianni" 
push_sales_purchase(user)