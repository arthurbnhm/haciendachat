import os
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv
import chainlit as cl
import openai
import json
import datetime
import logging
from typing import Dict, Optional

# Charger les variables d'environnement
load_dotenv()

# Configuration des variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OAUTH_GOOGLE_CLIENT_ID = os.getenv("OAUTH_GOOGLE_CLIENT_ID")
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
OAUTH_GOOGLE_CLIENT_SECRET = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET")
CHAINLIT_URL = os.getenv("CHAINLIT_URL")
PORT = int(os.getenv("PORT", 8000))

# Vérifier les variables d'environnement
required_vars = [
    "SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY",
    "OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET",
    "CHAINLIT_URL", "CHAINLIT_AUTH_SECRET", "PORT"
]
missing_env_vars = [var for var in required_vars if not os.getenv(var)]
if missing_env_vars:
    raise ValueError(f"Les variables d'environnement suivantes sont manquantes : {', '.join(missing_env_vars)}")

# Configurer le logger
logging.basicConfig(level=logging.DEBUG)

# Initialiser les clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY

# Obtenir la date actuelle
current_date = datetime.datetime.now()
current_day = current_date.day
current_month = current_date.month
current_year = current_date.year

# Fonction pour récupérer les données dans la table "IA" pour une date donnée
def get_ia_data_for_date(date_str):
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    logging.debug("Données récupérées : %s", response.data)
    return response.data

# Fonction pour générer un résumé détaillé des données
def generate_summary(data):
    if not data:
        return "Aucune information trouvée pour la période spécifiée."
    data_str = json.dumps(data, ensure_ascii=False)
    messages = [
        {"role": "system", "content": "Vous êtes un assistant qui résume des conversations."},
        {"role": "user", "content": f"Veuillez fournir un résumé détaillé des conversations suivantes :\n\n{data_str}"}
    ]
    summary = ""

    completion = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages,
        stream=True
    )

    for part in completion:
        delta = part.choices[0].delta
        if hasattr(delta, 'content') and delta.content is not None:
            summary += delta.content

    return summary

# Définir les outils
query_ia_data_def = {
    "name": "get_ia_data_for_date",
    "description": "Récupérer et résumer les données d'IA de Supabase pour une date spécifique",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "La date au format AAAA-MM-JJ (YYYY-MM-DD)"
            }
        },
        "required": ["date"]
    }
}

async def query_ia_data_handler(date: str):
    data = get_ia_data_for_date(date)
    summary = generate_summary(data)
    return summary

tools = [(query_ia_data_def, query_ia_data_handler)]

# Gestion des messages dans Chainlit
MAX_HISTORY_LENGTH = 10

@cl.on_chat_start
async def start():
    await cl.Message(content="Bienvenue sur l'assistant IA !").send()
    await setup_openai_realtime()

@cl.on_message
async def main(message: cl.Message):
    user_message = message.content

    if cl.user_session.get('conversation_history') is None:
        cl.user_session.set('conversation_history', [])

    conversation_history = cl.user_session.get('conversation_history')

    conversation_history.append({"role": "user", "content": user_message})

    if len(conversation_history) > MAX_HISTORY_LENGTH:
        conversation_history = conversation_history[-MAX_HISTORY_LENGTH:]

    cl.user_session.set('conversation_history', conversation_history)

    response_text = await get_openai_response(conversation_history)

    cl.user_session.set('conversation_history', conversation_history)

    await cl.Message(content=response_text).send()

# Fonction de callback OAuth pour Google
@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: Dict[str, str],
    default_user: cl.User,
) -> Optional[cl.User]:
    if provider_id == "google":
        email = raw_user_data.get("email")
        name = raw_user_data.get("name")

        response = supabase.table("users").select("*").eq("email", email).execute()
        user_data = response.data

        if not user_data:
            supabase.table("users").insert({"email": email, "name": name}).execute()
            logging.info(f"Nouvel utilisateur créé : {email}")
        else:
            logging.info(f"Utilisateur existant : {email}")

        return default_user
    return None

# Récupérer le port de l'environnement
port = PORT

# Lancer Chainlit en utilisant ce port et le secret d'authentification
if __name__ == "__main__":
    cl.run(
        port=port,
        host="0.0.0.0"
    )
