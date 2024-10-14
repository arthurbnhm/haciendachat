import os
from supabase import create_client, Client
from dotenv import load_dotenv
import chainlit as cl
import openai
import json
import datetime
import logging
import bcrypt

# Charger les variables d'environnement
load_dotenv()

# Configuration de Supabase et OpenAI
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET")

# **Ajout de cette ligne pour s'assurer que JWT_SECRET est présent dans os.environ**
os.environ["JWT_SECRET"] = JWT_SECRET

# Vérifier que le JWT secret est défini
if not JWT_SECRET:
    raise ValueError("Le secret JWT n'est pas défini. Vérifiez la variable d'environnement JWT_SECRET.")

# Initialiser les clients Supabase et OpenAI
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY

# Configurer le logger
logging.basicConfig(level=logging.INFO)

# Obtenir la date actuelle
current_date = datetime.datetime.now()
current_day = current_date.day
current_month = current_date.month
current_year = current_date.year

# Fonction d'authentification avec Supabase
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Requête à la base Supabase pour récupérer l'utilisateur par son nom d'utilisateur
    user_response = supabase.from_("users").select("*").eq("username", username).single().execute()
    
    # Vérifier si l'utilisateur existe
    if user_response.data:
        # Comparer les mots de passe hachés
        hashed_password = user_response.data["password"]
        if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
            return cl.User(
                identifier=user_response.data["id"],
                metadata={"role": user_response.data["role"], "provider": "credentials"}
            )
    
    return None  # Échec de l'authentification si l'utilisateur ou le mot de passe est incorrect

# Fonction pour récupérer les données dans la table "IA" pour une date donnée
def get_ia_data_for_date(date_str):
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    logging.debug("Données récupérées : %s", response.data)
    return response.data

# Fonction pour générer un résumé détaillé des données
def generate_summary(data):
    if not data:
        return "Aucune information trouvée pour la période spécifiée."
    else:
        data_str = json.dumps(data, ensure_ascii=False)
        messages = [
            {"role": "system", "content": "Vous êtes un assistant qui résume des conversations."},
            {"role": "user", "content": f"Veuillez fournir un résumé détaillé des conversations suivantes :\n\n{data_str}"}
        ]
        
        summary = ""
        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini-2024-07-18",
            messages=messages,
            stream=True
        )

        for part in completion:
            delta = part.choices[0].delta
            if hasattr(delta, 'content') and delta.content is not None:
                summary += delta.content

        return summary

# Fonction de gestion de l'appel de fonction pour OpenAI
def call_function_with_parameters(function_name, function_args_json):
    function_args = json.loads(function_args_json)
    if function_name == "get_ia_data_for_date":
        date_str = function_args.get("date")
        if date_str:
            logging.info(f"Date fournie par l'IA : {date_str}")
            function_response = get_ia_data_for_date(date_str)
            summary = generate_summary(function_response)
            return summary
        else:
            return "Date non spécifiée."
    return "Aucune fonction correspondante trouvée."

# Fonction pour envoyer la requête à OpenAI avec streaming
async def get_openai_response(conversation_history, msg):
    system_message = f"""
    Vous êtes un assistant utile qui aide à récupérer des données d'IA pour une date spécifiée.
    Nous sommes le {current_day}/{current_month}/{current_year}.
    Fournissez toujours la date au format AAAA-MM-JJ (YYYY-MM-DD).
    """

    messages = [{"role": "system", "content": system_message}] + conversation_history

    assistant_response = ""
    function_call = None
    function_name = None
    function_args = ""

    completion = await openai.ChatCompletion.acreate(
        model="gpt-4o-mini-2024-07-18",
        messages=messages,
        functions=[
            {
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
        ],
        function_call="auto",
        stream=True
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

    if function_call:
        logging.info(f"Appel de fonction détecté : {function_name}")
        logging.info(f"Arguments de la fonction : {function_args}")

        assistant_message = {"role": "assistant", "content": None, "function_call": {"name": function_name, "arguments": function_args}}
        conversation_history.append(assistant_message)

        function_response = call_function_with_parameters(function_name, function_args)

        function_message = {"role": "function", "name": function_name, "content": function_response}
        conversation_history.append(function_message)

        messages = [{"role": "system", "content": system_message}] + conversation_history

        completion = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini-2024-07-18",
            messages=messages,
            stream=True
        )

        assistant_response = ""

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

# Gestion des messages dans Chainlit
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

    msg = cl.Message(content="")
    await msg.send()

    response_text = await get_openai_response(conversation_history, msg)

    cl.user_session.set('conversation_history', conversation_history)

    await msg.update()

# Ajouter cette ligne pour récupérer le port de l'environnement
port = int(os.getenv("PORT", 8000))

if __name__ == "__main__":
    cl.run(port=port)
