import os
from supabase import create_client, Client
from dotenv import load_dotenv
import chainlit as cl
import openai
import json
import datetime
import logging
from typing import Dict, Optional
import starters

# Charger les variables d'environnement
load_dotenv()

# Configuration de Supabase, OpenAI et Chainlit
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OAUTH_GOOGLE_CLIENT_ID = os.getenv("OAUTH_GOOGLE_CLIENT_ID")
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
OAUTH_GOOGLE_CLIENT_SECRET = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET")
CHAINLIT_URL = os.getenv("CHAINLIT_URL")

# Vérifier que toutes les variables d'environnement requises sont définies
missing_env_vars = []
required_vars = [
    "SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY",
    "OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET",
    "CHAINLIT_URL", "CHAINLIT_AUTH_SECRET"
]
for var in required_vars:
    if not os.getenv(var):
        missing_env_vars.append(var)

if missing_env_vars:
    raise ValueError(f"Les variables d'environnement suivantes sont manquantes : {', '.join(missing_env_vars)}")

# Configurer le logger avec le niveau DEBUG
logging.basicConfig(level=logging.DEBUG)

# Initialiser les clients Supabase et OpenAI
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY

# Obtenir la date actuelle
current_date = datetime.datetime.now()
current_day = current_date.day
current_month = current_date.month
current_year = current_date.year

# Définir le system prompt global
SYSTEM_PROMPT = """Tu es un assistant dynamique, très pincanté qui récapitule les discussions tech issues de conversations WhatsApp, en ajoutant du contexte et des détails. Tu formates tes réponses en markdown. Ton style est chaleureux et engageant, avec un soupçon de piquant et des emojis 🌶️ ou 🔥. Plutôt que de lister les interventions par utilisateur, tu mets l'accent sur les thèmes abordés et les points de vue partagés, en les intégrant dans un récit fluide. En fonction des conversations, tu soulignes les moments importants et suggères des pistes pour approfondir. Tu peux également inclure des liens vers des articles, posts ou outils échangés en markdown. La communauté Whatsapp s'appelle l'Hacienda et Carlos Diaz est le gringo en chef."""

# Fonction pour récupérer les données dans la table "IA" pour une date donnée
def get_ia_data_for_date(date_str):
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    logging.debug("Données récupérées : %s", response.data)
    return response.data

# Définition de la fonction au format JSON pour le function calling
function_definition = {
    "name": "get_ia_data_for_date",
    "description": "Récupérer les données d'IA de Supabase pour une date spécifique",
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

# Fonction de gestion de l'appel de fonction pour OpenAI
def call_function_with_parameters(function_name, function_args_json):
    function_args = json.loads(function_args_json)
    if function_name == "get_ia_data_for_date":
        date_str = function_args.get("date")
        if date_str:
            logging.info(f"Date fournie par l'IA : {date_str}")
            function_response = get_ia_data_for_date(date_str)
            # Convertir les données en une chaîne lisible
            if not function_response:
                return "Aucune information trouvée pour la date spécifiée."
            data_str = json.dumps(function_response, ensure_ascii=False, indent=2)
            return f"Voici les données pour la date {date_str} :\n{data_str}"
        else:
            return "Date non spécifiée."
    return "Aucune fonction correspondante trouvée."

# Fonction pour envoyer la requête à OpenAI avec streaming et function calling
async def get_openai_response(conversation_history, msg):
    system_message = f"{SYSTEM_PROMPT}\nNous sommes le {current_day}/{current_month}/{current_year}."

    messages = [{"role": "system", "content": system_message}] + conversation_history

    assistant_response = ""
    function_call = None
    function_name = None
    function_args = ""

    # Appel à OpenAI avec la définition de la fonction incluse
    completion = await openai.ChatCompletion.acreate(
        model="gpt-4o-mini-2024-07-18",  # Correction du nom du modèle
        messages=messages,
        functions=[function_definition],
        function_call="auto",
        stream=True,
        max_tokens=1500,  # Ajustement pour des réponses plus détaillées
        temperature=0.8   # Température pour ajuster la créativité
    )

    async for part in completion:
        delta = part.choices[0].delta

        if hasattr(delta, 'content') and delta.content is not None:
            token = delta.content
            assistant_response += token
            await msg.stream_token(token)
        elif hasattr(delta, 'function_call') and delta.function_call is not None:
            if function_call is None:
                function_call = delta.function_call
                function_name = function_call.get("name")
                function_args += function_call.get("arguments", "")
            else:
                function_args += delta.function_call.get("arguments", "")
        else:
            pass

    # Si une fonction est appelée, exécuter la fonction correspondante
    if function_call:
        logging.info(f"Appel de fonction détecté : {function_name}")
        logging.info(f"Arguments de la fonction : {function_args}")

        function_response = call_function_with_parameters(function_name, function_args)

        function_message = {"role": "function", "name": function_name, "content": function_response}
        conversation_history.append(function_message)

        # Mettre à jour les messages avec le résultat de la fonction
        messages = [{"role": "system", "content": system_message}] + conversation_history

        # Appel final pour donner la réponse à l'utilisateur
        assistant_response = ""

        completion = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini-2024-07-18",  # Correction du nom du modèle
            messages=messages,
            stream=True,
            max_tokens=1500,  # Ajustement pour des réponses plus détaillées
            temperature=0.8    # Température pour ajuster la créativité
        )

        async for part in completion:
            delta = part.choices[0].delta
            if hasattr(delta, 'content') and delta.content is not None:
                token = delta.content
                assistant_response += token
                await msg.stream_token(token)

        conversation_history.append({"role": "assistant", "content": assistant_response})

        logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)
        return assistant_response
    else:
        conversation_history.append({"role": "assistant", "content": assistant_response})

        logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)
        return assistant_response

# Définir la taille maximale de l'historique
MAX_HISTORY_LENGTH = 10

# Gestion des messages dans Chainlit avec ajout du loader
@cl.on_message
async def main(message: cl.Message):
    user_message = message.content

    # Initialiser l'historique de conversation si nécessaire
    if cl.user_session.get('conversation_history') is None:
        cl.user_session.set('conversation_history', [])

    conversation_history = cl.user_session.get('conversation_history')

    conversation_history.append({"role": "user", "content": user_message})

    if len(conversation_history) > MAX_HISTORY_LENGTH:
        conversation_history = conversation_history[-MAX_HISTORY_LENGTH:]

    cl.user_session.set('conversation_history', conversation_history)

    # Envoyer un message de chargement
    loader_msg = cl.Message(content="Laisse moi ajouter un peu de 🌶️")
    await loader_msg.send()

    try:
        # Obtenir la réponse de l'IA et streamer les tokens
        response_text = await get_openai_response(conversation_history, loader_msg)
    except Exception as e:
        logging.error("Erreur lors de l'obtention de la réponse : %s", e)
        response_text = "🌶️ Une erreur s'est produite lors du traitement de votre demande."

    # Mettre à jour le message de chargement avec la réponse finale
    loader_msg.content = response_text
    await loader_msg.update()

    # Mettre à jour l'historique de conversation dans la session utilisateur
    cl.user_session.set('conversation_history', conversation_history)

# Fonction de callback OAuth pour Google (sans gestion manuelle des utilisateurs)
@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: Dict[str, str],
    default_user: cl.User,
)
