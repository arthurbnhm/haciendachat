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

# Configuration de Supabase, OpenAI et Chainlit
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAINLIT_AUTH_SECRET = os.getenv("CHAINLIT_AUTH_SECRET")

# Vérifier que toutes les variables d'environnement requises sont définies
missing_env_vars = []
if not SUPABASE_URL:
    missing_env_vars.append("SUPABASE_URL")
if not SUPABASE_KEY:
    missing_env_vars.append("SUPABASE_KEY")
if not OPENAI_API_KEY:
    missing_env_vars.append("OPENAI_API_KEY")
if not CHAINLIT_AUTH_SECRET:
    missing_env_vars.append("CHAINLIT_AUTH_SECRET")

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
            model="gpt-4",
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
        model="gpt-4",
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
            model="gpt-4",
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

# Fonction d'authentification utilisant la table "credentials" de Supabase
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    logging.info(f"Tentative de connexion pour l'utilisateur : {username}")
    response = supabase.table("credentials").select("*").eq("email", username).execute()
    logging.debug(f"Réponse de Supabase : {response.data}")
    user_data = response.data

    if user_data and len(user_data) > 0:
        user = user_data[0]
        stored_hashed_password = user['password']

        # Vérifier que le mot de passe haché n'est pas vide ou None
        if not stored_hashed_password:
            logging.error("Le mot de passe haché est vide ou None.")
            return None

        # Vérifier le mot de passe en utilisant bcrypt
        try:
            if bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password.encode('utf-8')):
                logging.info(f"Authentification réussie pour l'utilisateur : {username}")
                return cl.User(
                    identifier=username,
                    metadata={"provider": "credentials"}
                )
            else:
                logging.warning(f"Mot de passe incorrect pour l'utilisateur : {username}")
        except ValueError as e:
            logging.error(f"Erreur lors de la vérification du mot de passe : {e}")
            return None
    else:
        logging.warning(f"Utilisateur non trouvé : {username}")

    # Authentification échouée
    logging.error("Authentification échouée")
    return None

# Ajouter des actions personnalisées
@cl.action_callback("action_tools_shared")
async def on_action_tools_shared(action):
    await cl.Message(content=f"Action exécutée : {action.name} - Quels outils ont été partagés sur l'IA cette semaine ?").send()
    await action.remove()

@cl.action_callback("action_summary_yesterday")
async def on_action_summary_yesterday(action):
    await cl.Message(content=f"Action exécutée : {action.name} - Peux-tu me résumer les conversations d'hier dans le channel café ?").send()
    await action.remove()

# Gestion de démarrage du chat pour afficher les actions
@cl.on_chat_start
async def start():
    # Envoi des actions disponibles dans un message
    actions = [
        cl.Action(name="action_tools_shared", value="tools", description="Quels outils ont été partagés sur l'IA cette semaine ?", label="Outils IA"),
        cl.Action(name="action_summary_yesterday", value="summary", description="Peux-tu me résumer les conversations d'hier dans le channel café ?", label="Résumé Café")
    ]

    await cl.Message(content="Choisissez une action ci-dessous :", actions=actions).send()

# Récupérer le port de l'environnement
port = int(os.getenv("PORT", 8000))

# Lancer Chainlit en utilisant ce port et le secret d'authentification
if __name__ == "__main__":
    cl.run(
        port=port,
        host="0.0.0.0",
        auth_secret=CHAINLIT_AUTH_SECRET
    )
