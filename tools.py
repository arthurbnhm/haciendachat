import json
import logging
from supabase import Client
import plotly.graph_objects as go
from typing import Dict, Any

# Liste des définitions de fonctions pour OpenAI
FUNCTION_DEFINITIONS = [
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
        "name": "generate_plotly_chart",
        "description": "Générer un graphique Plotly basé sur les paramètres fournis",
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "description": "Le type de graphique à générer (e.g., bar, line)"
                },
                "data": {
                    "type": "object",
                    "description": "Les données pour le graphique",
                    "properties": {
                        "x": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Les valeurs de l'axe X"
                        },
                        "y": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Les valeurs de l'axe Y"
                        },
                        "title": {
                            "type": "string",
                            "description": "Le titre du graphique"
                        }
                    },
                    "required": ["x", "y"]
                }
            },
            "required": ["chart_type", "data"]
        }
    }
]

def get_ia_data_for_date(supabase: Client, date_str: str):
    """
    Récupère les données de la table "IA" pour une date spécifique.
    """
    response = supabase.table("IA").select("*").eq("Date", date_str).execute()
    logging.debug("Données récupérées : %s", response.data)
    return response.data

def generate_plotly_chart(supabase: Client, chart_type: str, data: Dict[str, Any]):
    """
    Génère un graphique Plotly basé sur les paramètres fournis.
    """
    try:
        if chart_type == "bar":
            fig = go.Figure(data=[go.Bar(x=data["x"], y=data["y"])])
        elif chart_type == "line":
            fig = go.Figure(data=[go.Scatter(x=data["x"], y=data["y"], mode='lines')])
        else:
            return json.dumps({"error": f"Type de graphique '{chart_type}' non supporté."})
        
        if "title" in data:
            fig.update_layout(title=data["title"])
        
        # Sérialiser le graphique en JSON
        fig_json = fig.to_json()
        return json.dumps({
            "text": f"Voici le graphique '{data.get('title', '')}':",
            "plotly_figure": fig_json
        })
    except Exception as e:
        logging.error("Erreur lors de la génération du graphique Plotly : %s", e)
        return json.dumps({"error": "Erreur lors de la génération du graphique."})

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
    elif function_name == "generate_plotly_chart":
        chart_type = function_args.get("chart_type")
        data = function_args.get("data")
        if chart_type and data:
            logging.info(f"Type de graphique demandé : {chart_type}")
            function_response = generate_plotly_chart(supabase, chart_type, data)
            return function_response
        else:
            return json.dumps({"error": "Paramètres 'chart_type' et 'data' sont requis."})
    return "Aucune fonction correspondante trouvée."
