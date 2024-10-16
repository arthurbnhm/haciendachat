# tools.py

import json
import logging
from supabase import Client
import plotly.graph_objects as go
from typing import Dict, Any
import random

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
                    "description": "Le type de graphique à générer (e.g., bar, line, scatter)"
                },
                "data": {
                    "type": "object",
                    "description": "Les données pour le graphique",
                    "properties": {
                        "x": {
                            "type": "array",
                            "items": {"type": "string"},
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
                        },
                        "labels": {
                            "type": "object",
                            "description": "Labels supplémentaires pour le graphique",
                            "properties": {
                                "xaxis": {"type": "string", "description": "Label de l'axe X"},
                                "yaxis": {"type": "string", "description": "Label de l'axe Y"}
                            }
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

def generate_plotly_chart(chart_type: str, data: Dict[str, Any]):
    """
    Génère un graphique Plotly basé sur les paramètres fournis.
    """
    try:
        fig = None
        if chart_type.lower() == "bar":
            fig = go.Figure(data=[go.Bar(x=data["x"], y=data["y"])])
        elif chart_type.lower() == "line":
            fig = go.Figure(data=[go.Scatter(x=data["x"], y=data["y"], mode='lines')])
        elif chart_type.lower() == "scatter":
            fig = go.Figure(data=[go.Scatter(x=data["x"], y=data["y"], mode='markers')])
        else:
            return json.dumps({"error": f"Type de graphique '{chart_type}' non supporté."})
        
        # Ajouter un titre si spécifié
        if "title" in data:
            fig.update_layout(title=data["title"])
        
        # Ajouter des labels si spécifiés
        if "labels" in data:
            labels = data["labels"]
            if "xaxis" in labels:
                fig.update_xaxes(title=labels["xaxis"])
            if "yaxis" in labels:
                fig.update_yaxes(title=labels["yaxis"])
        
        # Sérialiser le graphique en JSON
        fig_json = fig.to_json()
        return json.dumps({
            "text": f"Voici le graphique '{data.get('title', '')}':",
            "plotly_figure": fig_json,
            "title": data.get('title', 'Chart')
        })
    except Exception as e:
        logging.error("Erreur lors de la génération du graphique Plotly : %s", e)
        return json.dumps({"error": "Erreur lors de la génération du graphique."})

def generate_random_data():
    """
    Génère des données aléatoires pour le graphique.
    """
    categories = ['A', 'B', 'C', 'D', 'E']
    values = [random.randint(1, 100) for _ in categories]
    return {'x': categories, 'y': values, 'title': 'Données Aléatoires'}

def call_function_with_parameters(supabase: Client, function_name: str, function_args_json: str):
    """
    Gère l'appel de fonction en fonction du nom de la fonction et des arguments fournis.
    """
    if not function_args_json:
        # Si les arguments sont vides, fournir des valeurs par défaut
        if function_name == "generate_plotly_chart":
            chart_type = "bar"
            data = generate_random_data()
            logging.info(f"Utilisation de paramètres par défaut pour {function_name}")
            function_response = generate_plotly_chart(chart_type, data)
            return function_response
        else:
            return json.dumps({"error": "Paramètres manquants et aucun paramètre par défaut disponible."})
    
    try:
        function_args = json.loads(function_args_json)
    except json.JSONDecodeError as e:
        logging.error("Erreur lors du parsing des arguments JSON : %s", e)
        return json.dumps({"error": "Erreur de format des arguments JSON."})
    
    if function_name == "get_ia_data_for_date":
        date_str = function_args.get("date")
        if date_str:
            logging.info(f"Date fournie par l'IA : {date_str}")
            function_response = get_ia_data_for_date(supabase, date_str)
            # Convertir les données en une chaîne lisible
            if not function_response:
                return json.dumps({"error": "Aucune information trouvée pour la date spécifiée."})
            data_str = json.dumps(function_response, ensure_ascii=False, indent=2)
            return json.dumps({"text": f"Voici les données pour la date {date_str} :\n{data_str}", "data": function_response})
        else:
            return json.dumps({"error": "Date non spécifiée."})
    elif function_name == "generate_plotly_chart":
        chart_type = function_args.get("chart_type")
        data = function_args.get("data")
        if chart_type and data:
            logging.info(f"Type de graphique demandé : {chart_type}")
            function_response = generate_plotly_chart(chart_type, data)
            return function_response
        else:
            # Fournir des paramètres par défaut si certains sont manquants
            if not chart_type:
                chart_type = "bar"
            if not data:
                data = generate_random_data()
            function_response = generate_plotly_chart(chart_type, data)
            return function_response
    return json.dumps({"error": "Aucune fonction correspondante trouvée."})
