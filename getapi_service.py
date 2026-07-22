import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GETAPI_API_KEY")
BASE_URL = os.getenv("GETAPI_BASE_URL")

def consultar_patente(patente):
    url = f"{BASE_URL}/vehicles/plate/{patente}"
    headers = {
        "X-Api-Key": API_KEY
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()