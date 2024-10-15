import chainlit as cl

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Résumer les conversations IA de la semaine",
            message="Peux-tu me résumer les conversations autour de l'IA cette semaine ?",
            icon="/public/write.svg",  
        ),
        cl.Starter(
            label="Liens intéressants partagés",
            message="Donne moi les liens intéressants qui ont été partagés",
            icon="/public/learn.svg",
        ),
        cl.Starter(
            label="Nouveaux produits sur Roast me I'm famous",
            message="Quels produits ont été lancés récemment sur Roast me I'm famous ?",
            icon="/public/idea.svg", 
        ),
    ]
