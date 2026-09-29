import requests
import streamlit as st


class GetAPIConfigError(RuntimeError):
    """Faltan credenciales de GetAPI en .streamlit/secrets.toml."""


def _config():
    try:
        return st.secrets["GETAPI_BASE_URL"], st.secrets["GETAPI_API_KEY"]
    except (KeyError, FileNotFoundError) as e:
        raise GetAPIConfigError(
            "Faltan GETAPI_BASE_URL y/o GETAPI_API_KEY en .streamlit/secrets.toml"
        ) from e


def consultar_patente(patente: str) -> dict:
    base_url, api_key = _config()
    url = f"{base_url.rstrip('/')}/vehicles/plate/{patente}"
    response = requests.get(url, headers={"X-Api-Key": api_key}, timeout=20)
    response.raise_for_status()
    return response.json()
