# app.py

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
import plotly.graph_objects as go  # Import nécessaire pour reconstruire les figures

# Importer les définitions de fonctions et les gestionnaires depuis tools.py
from tools import FUNCTION_DEFINITIONS, call_function_with_parameters

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

# Définir le system prompt global dans app.py
SYSTEM_PROMPT = """Tu es un assistant dynamique, très pincanté qui récapitule les discussions tech issues de conversations WhatsApp, en ajoutant du contexte et des détails. Tu formates tes réponses en markdown. Ton style est chaleureux et engageant, avec un soupçon de piquant et des emojis 🌶️ ou 🔥. Plutôt que de lister les interventions par utilisateur, tu mets l'accent sur les thèmes abordés et les points de vue partagés, en les intégrant dans un récit fluide. En fonction des conversations, tu soulignes les moments importants et suggères des pistes pour approfondir. Tu peux également inclure des liens vers des articles, posts ou outils échangés en markdown. La communauté Whatsapp s'appelle l'Hacienda et Carlos Diaz est le gringo en chef."""

# Fonction pour envoyer la requête à OpenAI avec streaming et function calling
async def get_openai_response(conversation_history, msg):
    system_message = f"{SYSTEM_PROMPT}\nNous sommes le {current_day}/{current_month}/{current_year}."

    messages = [{"role": "system", "content": system_message}] + conversation_history

    assistant_response = ""
    plotly_elements = []  # Liste pour stocker les éléments Plotly à afficher

    # Appel à OpenAI avec la définition de la fonction incluse
    try:
        completion = await openai.ChatCompletion.acreate(
            model="gpt-4",  # Assurez-vous que le nom du modèle est correct
            messages=messages,
            functions=FUNCTION_DEFINITIONS,
            function_call="auto",
            stream=True,
            max_tokens=1500,  # Ajustement pour des réponses plus détaillées
            temperature=0.8   # Température pour ajuster la créativité
        )
    except Exception as e:
        logging.error("Erreur lors de l'appel à OpenAI : %s", e)
        return "🌶️ Une erreur s'est produite lors de l'appel à OpenAI."

    try:
        async for part in completion:
            delta = part.choices[0].delta

            if hasattr(delta, 'content') and delta.content is not None:
                token = delta.content
                assistant_response += token
                await msg.stream_token(token)
            elif hasattr(delta, 'function_call') and delta.function_call is not None:
                function_call = delta.function_call
                function_name = function_call.get("name")
                function_args = function_call.get("arguments", "")

                logging.info(f"Appel de fonction détecté : {function_name}")
                logging.info(f"Arguments de la fonction : {function_args}")

                # Appeler la fonction depuis le module séparé
                function_response = call_function_with_parameters(supabase, function_name, function_args)

                try:
                    response_json = json.loads(function_response)
                except json.JSONDecodeError as e:
                    logging.error("Erreur lors du parsing des arguments JSON : %s", e)
                    response_json = {"text": "Erreur de format des données."}

                # Si la réponse inclut un graphique Plotly
                if "plotly_figure" in response_json:
                    plotly_json = response_json.get("plotly_figure")
                    plotly_text = response_json.get("text", "")
                    try:
                        plotly_fig = go.Figure.from_json(plotly_json)
                        plotly_element = cl.Plotly(name=response_json.get("title", "Chart"), figure=plotly_fig, display="inline")
                        plotly_elements.append((plotly_text, plotly_element))
                    except Exception as e:
                        logging.error("Erreur lors de la reconstruction du graphique Plotly : %s", e)
                        plotly_elements.append((plotly_text + "\nErreur lors de la génération du graphique.", None))
                else:
                    plotly_elements.append((response_json.get("text", ""), None))

                # Ajouter le message de fonction à l'historique
                function_message = {"role": "function", "name": function_name, "content": function_response}
                conversation_history.append(function_message)
                messages = [{"role": "system", "content": system_message}] + conversation_history

    except Exception as e:
        logging.error("Erreur lors de la lecture du flux de complétion : %s", e)
        return "🌶️ Une erreur s'est produite lors du traitement de la réponse de l'IA."

    # Après avoir traité tous les appels de fonctions, générer la réponse finale
    assistant_message = {"role": "assistant", "content": assistant_response}
    conversation_history.append(assistant_message)

    logging.info("Réponse finale envoyée à l'utilisateur : %s", assistant_response)

    # Envoyer les graphiques Plotly si présents
    for text, plotly_element in plotly_elements:
        if plotly_element:
            plot_msg = cl.Message(content=text, elements=[plotly_element])
            await plot_msg.send()
        else:
            # Envoyer uniquement le texte si le graphique n'a pas pu être généré
            if text:
                plot_msg = cl.Message(content=text)
                await plot_msg.send()

    # Mettre à jour le message de chargement avec la réponse finale
    try:
        msg.text = assistant_response  # Correction ici : utiliser 'text' au lieu de 'content'
        await msg.update()
    except Exception as e:
        logging.error("Erreur lors de la mise à jour du message : %s", e)

    # Mettre à jour l'historique de conversation dans la session utilisateur
    cl.user_session.set('conversation_history', conversation_history)

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
    try:
        loader_msg.text = response_text  # Correction ici : utiliser 'text' au lieu de 'content'
        await loader_msg.update()
    except Exception as e:
        logging.error("Erreur lors de la mise à jour du message de chargement : %s", e)

    # Mettre à jour l'historique de conversation dans la session utilisateur
    cl.user_session.set('conversation_history', conversation_history)

# Fonction de callback OAuth pour Google
@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: Dict[str, str],
    default_user: cl.User,
) -> Optional[cl.User]:
    if provider_id == "google":
        # Récupérer les informations de l'utilisateur
        email = raw_user_data.get("email")
        name = raw_user_data.get("name")

        # Vérifier si l'utilisateur existe déjà dans Supabase
        response = supabase.table("users").select("*").eq("email", email).execute()
        user_data = response.data

        if not user_data:
            # Créer un nouvel utilisateur
            supabase.table("users").insert({"email": email, "name": name}).execute()
            logging.info(f"Nouvel utilisateur créé : {email}")
        else:
            logging.info(f"Utilisateur existant : {email}")

        return default_user
    return None
