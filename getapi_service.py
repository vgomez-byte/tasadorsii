import os
import requests
import streamlit as st

API_KEY=st.secrets["GETAPI_API_KEY"]
BASE_URL=st.secrets["GETAPI_BASE_URL"]

def consultar_patente(patente):
    url = f"{BASE_URL}/vehicles/plate/{patente}"
    headers = {
        "X-Api-Key": API_KEY
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()