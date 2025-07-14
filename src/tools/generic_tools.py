# src/tools/generic_tools.py
import os
import httpx
import json
from typing import Optional

from src.shared.llm_client import call_llm



GRA_PUBLIC_URL = os.environ.get("GRA_PUBLIC_URL", "http://localhost:8000")



async def workforce_information(input: dict, context_id: Optional[str] = None) -> dict:
    """Fournit la liste des agents et leurs compétences depuis le GRA."""
    try:
        async with httpx.AsyncClient() as client:
            agents_resp = await client.get(f"{GRA_PUBLIC_URL}/agents")
            agents_resp.raise_for_status()
            stats_resp = await client.get(f"{GRA_PUBLIC_URL}/v1/stats/agents")
            stats_resp.raise_for_status()

        agents = agents_resp.json()
        stats = stats_resp.json()

        return {
            "agents": agents,
            "stats": stats,
            "summary_for_prompt": f"{len(agents)} agents déclarés avec statistiques globales disponibles."
        }
    except Exception as e:
        return {"error": str(e)}

async def capability_check(input: dict, context_id: Optional[str] = None) -> dict:
    from src.shared.tool_registry import ToolRegistry  # ✅ Import local

    deliverable = input.get("deliverable_description", "")
    if not deliverable:
        return {"error": "deliverable_description requis."}

    # Récupère dynamiquement les outils disponibles
    tools = ToolRegistry(agent_skill="coding_python").get_tools()
    tool_list = list(tools.keys())

    from src.shared.llm_client import call_llm

    system_prompt = (
        "Tu es un agent logiciel outillé pour accomplir des objectifs de développement Python.\n"
        "Voici la liste des outils que tu peux utiliser :\n"
        + "\n".join(f"- {tool}" for tool in tool_list) +
        "\n\nÉvalue si ces outils te permettent de réaliser le livrable suivant."
    )

    user_prompt = (
        f"Voici le livrable demandé :\n{deliverable}\n\n"
        "Réponds avec un objet JSON de la forme :\n"
        '{\n  "can_handle": true/false,\n  "confidence": "low/medium/high",\n  "comment": "explication brève"\n}'
    )

    try:
        response = await call_llm(user_prompt, system_prompt, json_mode=True)
        import json
        result = json.loads(response) if isinstance(response, str) else response
        return {
            "can_handle": result.get("can_handle", False),
            "confidence": result.get("confidence", "unknown"),
            "comment": result.get("comment", "Pas de commentaire du LLM.")
        }
    except Exception as e:
        return {"error": f"Erreur LLM : {str(e)}"}

async def ask_user(input: dict, context_id: str) -> dict:
    question = input["question"]
    return {
        "status": "pending",
        "forward_to": "UserInteractionAgent",
        "msg_type": "USER_QUERY",
        "payload": {"question": question}
    }
