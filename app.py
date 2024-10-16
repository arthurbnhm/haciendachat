import os
import json
import logging
import datetime
from typing import Dict, Optional, List

from supabase import create_client, Client
from dotenv import load_dotenv
import chainlit as cl
import openai
from datetime import datetime as dt

import starters

# Charger les variables d'environnement
load_dotenv()

# Configuration de logging
logging.basicConfig(level=logging.DEBUG)

# Configuration des variables d'environnement
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OAUTH_GOOGLE_CLIENT_ID = os.getenv("OAUTH_GOOGLE_CLIENT_ID")
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")
OAUTH_GOOGLE_CLIENT_SECRET = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET")
CHAINLIT_URL = os.getenv("CHAINLIT_URL")

# Vérifier que toutes les variables d'environnement requises sont définies
def validate_env_vars():
    required_vars = [
        "SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY",
        "OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET",
        "CHAINLIT_URL", "CHAINLIT_AUTH_SECRET"
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Les variables d'environnement suivantes sont manquantes : {', '.join(missing)}")

validate_env_vars()

# Initialiser les clients Supabase et OpenAI
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY
logging.debug("Clients Supabase et OpenAI initialisés.")

# Définir le system prompt global
SYSTEM_PROMPT = (
    "Tu es un assistant dynamique, très pincanté qui récapitule les discussions tech issues de conversations WhatsApp, "
    "en ajoutant du contexte et des détails. Tu formates tes réponses en markdown. Ton style est chaleureux et engageant, "
    "avec un soupçon de piquant et des emojis 🌶️ ou 🔥. Plutôt que de lister les interventions par utilisateur, tu mets "
    "l'accent sur les thèmes abordés et les points de vue partagés, en les intégrant dans un récit fluide. En fonction des "
    "conversations, tu soulignes les moments importants et suggères des pistes pour approfondir. Tu peux également inclure "
    "des liens vers des articles, posts ou outils échangés en markdown. La communauté Whatsapp s'appelle l'Hacienda et "
    "Carlos Diaz est le gringo en chef. Tu peux filtrer les discussions par date ou par plage de dates selon les demandes des utilisateurs."
)

# Définir la taille maximale de l'historique (optionnel)
MAX_HISTORY_LENGTH = 10  # Vous pouvez ajuster ou supprimer cette limite si nécessaire

# Définition des fonctions au format JSON pour le function calling
function_definitions = [
    {
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
    },
    {
        "name": "get_ia_data_between_dates",
        "description": "Récupérer les données d'IA de Supabase entre deux dates spécifiques",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "La date de début au format AAAA-MM-JJ (YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "La date de fin au format AAAA-MM-JJ (YYYY-MM-DD)"
                }
            },
            "required": ["start_date", "end_date"]
        }
    }
]

# Fonction pour valider le format des dates
def validate_date(date_str: str) -> bool:
    try:
        dt.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

# Fonction pour récupérer les données dans la table "IA" pour une date donnée
def get_ia_data_for_date(date_str: str) -> List[Dict]:
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    logging.debug("Données récupérées pour la date %s : %s", date_str, response.data)
    return response.data

# Fonction pour récupérer les données dans la table "IA" entre deux dates données
def get_ia_data_between_dates(start_date_str: str, end_date_str: str) -> List[Dict]:
    response = supabase.table("IA").select("*").gte("Date", start_date_str).lte("Date", end_date_str).execute()
    logging.debug("Données récupérées entre %s et %s : %s", start_date_str, end_date_str, response.data)
    return response.data

# Fonction pour vérifier si un utilisateur existe dans Supabase
def user_exists(email: str) -> bool:
    response = supabase.table("users").select("*").eq("email", email).execute()
    return bool(response.data)

# Fonction pour créer un nouvel utilisateur dans Supabase
def create_user(email: str, name: str):
    supabase.table("users").insert({"email": email, "name": name}).execute()
    logging.info(f"Nouvel utilisateur créé : {email}")

# Fonction de gestion de l'appel de fonction pour OpenAI
def call_function_with_parameters(function_name: str, function_args_json: str) -> str:
    function_args = json.loads(function_args_json)
    
    if function_name == "get_ia_data_for_date":
        date_str = function_args.get("date")
        if date_str and validate_date(date_str):
            logging.info(f"Date fournie par l'IA : {date_str}")
            data = get_ia_data_for_date(date_str)
            if not data:
                return "Aucune information trouvée pour la date spécifiée."
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            return f"Voici les données pour la date {date_str} :\n{data_str}"
        else:
            return "Format de date invalide ou date non spécifiée."
    
    elif function_name == "get_ia_data_between_dates":
        start_date_str = function_args.get("start_date")
        end_date_str = function_args.get("end_date")
        if start_date_str and end_date_str and validate_date(start_date_str) and validate_date(end_date_str):
            logging.info(f"Plage de dates fournie par l'IA : {start_date_str} à {end_date_str}")
            data = get_ia_data_between_dates(start_date_str, end_date_str)
            if not data:
                return "Aucune information trouvée pour la plage de dates spécifiée."
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            return f"Voici les données entre le {start_date_str} et le {end_date_str} :\n{data_str}"
        else:
            return "Format de date invalide ou dates de début et/ou de fin non spécifiées."
    
    return "Aucune fonction correspondante trouvée."

# Fonction pour envoyer la requête à OpenAI avec streaming et function calling
async def get_openai_response(msg: cl.Message) -> str:
    current_date = dt.now()
    system_message = f"{SYSTEM_PROMPT}\nNous sommes le {current_date.day}/{current_date.month}/{current_date.year}."
    
    # Obtenir les messages du contexte de chat au format OpenAI
    chat_messages = cl.chat_context.to_openai()
    
    # Optionnel : Limiter la taille de l'historique
    if MAX_HISTORY_LENGTH:
        # Inclure uniquement les derniers messages selon la limite définie
        chat_messages = chat_messages[-MAX_HISTORY_LENGTH:]
    
    # Préparer le message complet à envoyer à OpenAI
    messages = [{"role": "system", "content": system_message}] + chat_messages

    assistant_response = ""
    function_call = None
    function_args = ""

    # Appel à OpenAI avec toutes les définitions de fonctions incluses
    completion = await openai.ChatCompletion.acreate(
        model="gpt-4o-mini-2024-07-18",  # Assurez-vous d'utiliser le modèle correct
        messages=messages,
        functions=function_definitions,
        function_call="auto",
        stream=True,
        max_tokens=1500,
        temperature=0.8
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
        cl.chat_context.append(function_message)  # Ajout au contexte de chat

        # Mettre à jour les messages avec le résultat de la fonction
        messages = [{"role": "system", "content": system_message}] + cl.chat_context.to_openai()

        # Appel final pour donner la réponse à l'utilisateur
        assistant_response = ""

        completion = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini-2024-07-18",  # Assurez-vous d'utiliser le modèle correct
            messages=messages,
            stream=True,
            max_tokens=1500,
            temperature=0.8
        )

        async for part in completion:
            delta = part.choices[0].delta
            if hasattr(delta, 'content') and delta.content is not None:
                token = delta.content
                assistant_response += token
                await msg.stream_token(token)

        cl.chat_context.append({"role": "assistant", "content": assistant_response})
        logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)
        return assistant_response
    else:
        cl.chat_context.append({"role": "assistant", "content": assistant_response})
        logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)
        return assistant_response

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

        if email and name:
            if not user_exists(email):
                create_user(email, name)
            else:
                logging.info(f"Utilisateur existant : {email}")
            return default_user
        else:
            logging.warning("Données utilisateur incomplètes reçues.")
            return None
    return None

# Gestion des messages dans Chainlit avec ajout du loader
@cl.on_message
async def handle_message(message: cl.Message):
    user_message = message.content

    # Les messages sont automatiquement ajoutés au contexte de chat par Chainlit
    cl.chat_context.append({"role": "user", "content": user_message})

    # Envoyer un message de chargement
    loader_msg = cl.Message(content="Laisse moi ajouter un peu de 🌶️")
    await loader_msg.send()

    try:
        # Obtenir la réponse de l'IA et streamer les tokens
        response_text = await get_openai_response(loader_msg)
    except Exception as e:
        logging.error("Erreur lors de l'obtention de la réponse : %s", e)
        response_text = "🌶️ Une erreur s'est produite lors du traitement de votre demande."

    # Mettre à jour le message de chargement avec la réponse finale
    loader_msg.content = response_text
    await loader_msg.update()
