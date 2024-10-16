import json
import logging
from supabase import Client

# Définition de la fonction au format JSON pour le function calling
FUNCTION_DEFINITION = {
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

def get_ia_data_for_date(supabase: Client, date_str: str):
    """
    Récupère les données de la table "IA" pour une date spécifique.
    """
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    logging.debug("Données récupérées : %s", response.data)
    return response.data

def call_function_with_parameters(supabase: Client, function_name: str, function_args_json: str):
    """
    Gère l'appel de fonction en fonction du nom de la fonction et des arguments fournis.
    """
    function_args = json.loads(function_args_json)
    if function_name == "get_ia_data_for_date":
        date_str = function_args.get("date")
        if date_str:
            logging.info(f"Date fournie par l'IA : {date_str}")
            function_response = get_ia_data_for_date(supabase, date_str)
            # Convertir les données en une chaîne lisible
            if not function_response:
                return "Aucune information trouvée pour la date spécifiée."
            data_str = json.dumps(function_response, ensure_ascii=False, indent=2)
            return f"Voici les données pour la date {date_str} :\n{data_str}"
        else:
            return "Date non spécifiée."
    return "Aucune fonction correspondante trouvée."
