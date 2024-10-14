import os
from supabase import create_client, Client
from dotenv import load_dotenv
import chainlit as cl
import openai
import json
import datetime
import logging
import bcrypt  # Ajout pour le hachage des mots de passe

# Charger les variables d'environnement
load_dotenv()

# Configuration de Supabase et OpenAI
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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

# Fonction pour récupérer les données dans la table "IA" pour une date donnée
def get_ia_data_for_date(date_str):
    # Requête Supabase avec la bonne structure : d'abord select("*"), puis eq()
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    
    # Afficher les données dans la console pour vérifier ce qui est récupéré
    logging.debug("Données récupérées : %s", response.data)
    
    return response.data

# Fonction pour générer un résumé détaillé des données
def generate_summary(data):
    if not data:
        return "Aucune information trouvée pour la période spécifiée."
    else:
        # Convertir les données en une chaîne JSON
        data_str = json.dumps(data, ensure_ascii=False)
        
        # Créer un message pour l'IA avec les données et une instruction pour résumer
        messages = [
            {"role": "system", "content": "Vous êtes un assistant qui résume des conversations."},
            {"role": "user", "content": f"Veuillez fournir un résumé détaillé des conversations suivantes :\n\n{data_str}"}
        ]
        
        # Appel à l'API OpenAI pour générer le résumé avec streaming
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
            # Utiliser la date fournie par l'IA
            logging.info(f"Date fournie par l'IA : {date_str}")
            function_response = get_ia_data_for_date(date_str)
            # Générer un résumé détaillé des données
            summary = generate_summary(function_response)
            return summary
        else:
            return "Date non spécifiée."
    return "Aucune fonction correspondante trouvée."

# Fonction pour envoyer la requête à OpenAI avec streaming
async def get_openai_response(conversation_history, msg):
    # Inclure la date actuelle dans le message système
    system_message = f"""
    Vous êtes un assistant utile qui aide à récupérer des données d'IA pour une date spécifiée.
    Nous sommes le {current_day}/{current_month}/{current_year}.
    Fournissez toujours la date au format AAAA-MM-JJ (YYYY-MM-DD).
    """

    # Préparer les messages pour l'API OpenAI
    messages = [{"role": "system", "content": system_message}] + conversation_history

    # Initialiser les variables
    assistant_response = ""
    function_call = None
    function_name = None
    function_args = ""

    # Appel à l'API OpenAI avec streaming
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

    # Traitement de la réponse en streaming
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
            # Gérer les autres cas si nécessaire
            pass

    # Vérifier s'il y a un appel de fonction
    if function_call:
        # Afficher dans la console la fonction appelée et ses arguments
        logging.info(f"Appel de fonction détecté : {function_name}")
        logging.info(f"Arguments de la fonction : {function_args}")

        # Ajouter l'appel de fonction de l'assistant à l'historique de la conversation
        assistant_message = {"role": "assistant", "content": None, "function_call": {"name": function_name, "arguments": function_args}}
        conversation_history.append(assistant_message)

        # Appeler la fonction avec les paramètres
        function_response = call_function_with_parameters(function_name, function_args)

        # Ajouter la réponse de la fonction à l'historique de la conversation
        function_message = {"role": "function", "name": function_name, "content": function_response}
        conversation_history.append(function_message)

        # Préparer les messages pour l'API OpenAI
        messages = [{"role": "system", "content": system_message}] + conversation_history

        # Appel à l'API OpenAI pour obtenir la réponse finale avec streaming
        completion = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini-2024-07-18",
            messages=messages,
            stream=True
        )

        # Réinitialiser la réponse de l'assistant
        assistant_response = ""

        async for part in completion:
            delta = part.choices[0].delta
            if hasattr(delta, 'content') and delta.content is not None:
                token = delta.content
                assistant_response += token
                await msg.stream_token(token)

        # Ajouter la réponse finale de l'assistant à l'historique de la conversation
        conversation_history.append({"role": "assistant", "content": assistant_response})

        # Afficher la réponse finale
        logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)
        return assistant_response
    else:
        # Pas d'appel de fonction
        # Ajouter la réponse de l'assistant à l'historique de la conversation
        conversation_history.append({"role": "assistant", "content": assistant_response})

        # Afficher la réponse finale
        logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)
        return assistant_response

# Définir la taille maximale de l'historique
MAX_HISTORY_LENGTH = 10  # Nombre maximum de messages à conserver dans l'historique

# Gestion des messages dans Chainlit
@cl.on_message
async def main(message: cl.Message):
    user_message = message.content

    # Vérifier si 'conversation_history' existe dans la session utilisateur
    if cl.user_session.get('conversation_history') is None:
        cl.user_session.set('conversation_history', [])

    # Récupérer l'historique de la conversation
    conversation_history = cl.user_session.get('conversation_history')

    # Ajouter le message de l'utilisateur à l'historique de la conversation
    conversation_history.append({"role": "user", "content": user_message})

    # Limiter la taille de l'historique si nécessaire
    if len(conversation_history) > MAX_HISTORY_LENGTH:
        conversation_history = conversation_history[-MAX_HISTORY_LENGTH:]

    # Mettre à jour l'historique dans la session utilisateur
    cl.user_session.set('conversation_history', conversation_history)

    # Créer un objet de message Chainlit avec contenu vide et l'envoyer (affiche un loader)
    msg = cl.Message(content="")
    await msg.send()

    # Appel à OpenAI pour gérer la réponse avec streaming
    response_text = await get_openai_response(conversation_history, msg)

    # Mettre à jour l'historique de la conversation avec les modifications faites dans get_openai_response
    cl.user_session.set('conversation_history', conversation_history)

    # Mettre à jour le message final
    await msg.update()

# Fonction d'authentification utilisant la table "Credentials" de Supabase
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    # Rechercher l'utilisateur correspondant à l'email (username)
    response = supabase.table("Credentials").select("*").eq("email", username).execute()
    user_data = response.data

    if user_data and len(user_data) > 0:
        user = user_data[0]
        stored_hashed_password = user['password']

        # Vérifier le mot de passe en utilisant bcrypt
        if bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password.encode('utf-8')):
            # Authentification réussie, retourner un objet cl.User
            return cl.User(
                identifier=username,
                # Vous pouvez ajouter des métadonnées supplémentaires ici si nécessaire
                metadata={"provider": "credentials"}
            )
    # Authentification échouée
    return None

# Ajouter cette ligne pour récupérer le port de l'environnement
port = int(os.getenv("PORT", 8000))

# Lancer Chainlit en utilisant ce port
if __name__ == "__main__":
    cl.run(port=port)
