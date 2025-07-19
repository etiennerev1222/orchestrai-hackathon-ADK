import asyncio
from src.agents.user_interaction_agent.logic import UserInteractionAgentLogic

async def test_user_interaction():
    agent = UserInteractionAgentLogic()

    # ÉTAPE 1 — Entrée utilisateur brute
    raw_objective = "Créer une application mobile de gestion de tâches pour les étudiants."

    input_data = {
        "action": "clarify_objective",
        "objective": raw_objective,
        "context_id": None,
        "history": []
    }

    result, status = await agent.process(input_data)
    print(f"\n--- ÉTAPE 1 ---")
    print(f"STATUS: {status}")
    print("RESULT:")
    print(result)

    if status != "input_required":
        print("Fin du test, pas de clarification requise.")
        return

    # ÉTAPE 2 — Simulation de réponse utilisateur
    user_answer = "L'application doit fonctionner sur iOS et Android avec intégration à Google Calendar."

    second_input = {
        "action": "clarify_objective",
        "objective": raw_objective,  # <== on garde le même objectif de base
        "previous_turn": result,
        "user_answer": user_answer,  # <== réponse utilisateur injectée ici
        "context_id": None
    }

    result2, status2 = await agent.process(second_input)
    print(f"\n--- ÉTAPE 2 : RÉPONSE UTILISATEUR ---")
    print(f"STATUS: {status2}")
    print("RESULT:")
    print(result2)

if __name__ == "__main__":
    asyncio.run(test_user_interaction())

