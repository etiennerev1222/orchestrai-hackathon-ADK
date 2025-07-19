
import logging
import json
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime

import httpx
from src.shared.llm_client import call_llm
from src.shared.firebase_init import get_firestore_client

from src.shared.prompt_utils import build_dynamic_system_prompt
from src.shared.tool_registry import ToolRegistry
import uuid
from datetime import datetime

import src.shared.interaction_logger as interaction_logger





logger = logging.getLogger(__name__)
GRA_PUBLIC_URL = os.environ.get("GRA_PUBLIC_URL", "http://localhost:8000")

class BaseAgentLogic(ABC):
    def __init__(self):
        self.environment_manager = None
        self.agent_type = getattr(self, "agent_type", "generic")
        self.tool_registry = ToolRegistry(agent_skill=self.agent_type)
        
        logger.info(f"Logique d'agent de type '{self.__class__.__name__}' initialisée.")

    def set_environment_manager(self, manager: Any):
        self.environment_manager = manager
        logger.info(f"EnvironmentManager set for {self.__class__.__name__}.")

    def get_context_summary(self, context_id: str | None) -> str | None:
        if not context_id:
            logger.warning("[CTX] get_context_summary appelé sans context_id")
            return None
        try:
            from src.shared.execution_task_graph_management import ExecutionTaskGraph
            graph = ExecutionTaskGraph(context_id)
            node = graph.get_task(context_id)
            if not node:
                logger.warning(f"[CTX] Contexte {context_id} introuvable")
                return None
            return node.meta.get("context_summary") or node.result_summary
        except Exception as e:
            logger.error(f"[CTX] Erreur récupération contexte {context_id}: {e}")
            return None

    def extract_final_result_with_fallback(self, loop_result: dict) -> dict:
        final = loop_result.get("final_result", {})
        if "status" not in final or final["status"] is None:
            interactions = loop_result.get("interactions", [])
            if interactions and isinstance(interactions[-1], dict) and "status" in interactions[-1]:
                final = interactions[-1]
                logger.warning("[Fallback] Aucun status explicite dans final_result — utilisation du dernier élément de 'interactions'.")
        return final

    async def on_question_to_user(self, payload: dict) -> dict:
        """
        Handler appelé quand un autre agent pose une question à l'utilisateur via ce proxy.
        Le payload devrait inclure au minimum : {"question": "...", "context": "..."}
        """
        question = payload.get("question", "Question sans contenu.")
        return {
            "question_for_user": question,
            "status": "input_required"
        }
    async def ask_user_question(self, question: str, receiver_agent: str = "UserInteractionAgentServer") -> dict:
        """
        Méthode standard pour qu'un agent demande une clarification à l'utilisateur via UserInteractionAgent.
        """
        payload = {
            "action": "ask_user",
            "question": question
        }

        result = await self.send_collaborative_message(
            receiver_agent=receiver_agent,
            msg_type="QUESTION_TO_USER",
            payload=payload
        )

        return result
    def postprocess_reasoning_result(self, loop_result: dict, original_input: str) -> dict:
        final = self.extract_final_result_with_fallback(loop_result)
        final["original_input_text_this_turn"] = original_input
        return final

    def get_tool_description(self, tool_name: str) -> str:
        """
        Retourne une description humaine de l'outil, à afficher dans le prompt.
        """
        tool_descriptions = {
            "workforce_information": "Permet d'obtenir la liste des agents connus et leurs compétences.",
            "your_next_tool": "Décrit ce que ton futur outil fera ici..."
        }
        return tool_descriptions.get(tool_name, "Aucune description disponible.")

    def _inject_tool_descriptions(self, base_prompt: str, allowed_tools: Optional[list[str]]) -> str:
        """
        Injecte la section [TOOLS DISPONIBLES] à la fin du system prompt.
        """
        if not allowed_tools:
            return base_prompt

        tool_lines = []
        for name in allowed_tools:
            desc = self.get_tool_description(name)
            tool_lines.append(f"- {name}: {desc}")

        tools_section = "\n\n[TOOLS DISPONIBLES]\n" + "\n".join(tool_lines)
        return base_prompt.rstrip() + tools_section


    def _record_collaboration(
        sender_agent: str,
        receiver_agent: str,
        msg_type: str,
        context_id: str,
        tool_invoked: Optional[dict] = None,
        llm_prompt: Optional[str] = None,
        llm_output: Optional[dict] = None,
        result_summary: Optional[str] = None,
    ) -> str:
        artifact = interaction_logger.build_collaboration_artifact(
            context_id=context_id,
            msg_type=msg_type,
            sender_agent=sender_agent,
            receiver_agent=receiver_agent,
            llm_prompt=llm_prompt,
            llm_output=llm_output,
            result_summary=result_summary,
            tool_invoked=tool_invoked,
        )
        interaction_logger.log_collaboration_trace(artifact, context_id=context_id)
        return artifact["interaction_id"]

# src/shared/base_agent_logic.py

    def get_active_tools(self) -> dict:
        """
        Par défaut, aucun outil actif.
        Les sous-classes doivent surcharger cette méthode pour exposer leurs outils.
        """
        return {}
    
    async def tool_capability_check(self, input: dict) -> dict:
        deliverable = input.get("deliverable_description", "")
        tool_list = list(self.registered_tools.keys())

        return {
            "can_handle": self.can_deliver(deliverable),
            "tools_available": tool_list,
            "agent_type": self.agent_type,
            "deliverable_description": deliverable
        }

    async def run_reasoning_loop_with_tools(
        self,
        objective: str,
        context_id: Optional[str] = None,
        allowed_tools: Optional[list[str]] = None,
        initial_prompt: Optional[str] = None,
        max_iterations: int = 6,
        system_prompt: Optional[str] = None
    ) -> dict:
        """
        Boucle universelle : LLM propose une action, l'agent exécute et réinjecte le résultat jusqu'à finalisation.
        """
        result = None
        error = None
        interactions = []
        history = []

        if system_prompt:
            system_prompt_final = system_prompt
        else:
            tool_names = allowed_tools or list(self.tool_registry.tools.keys())
            system_prompt_final = build_dynamic_system_prompt(self.tool_registry.get_metadata_for_tools(tool_names))

        if context_id:
            ctx = self.get_context_summary(context_id)
            if ctx:
                system_prompt_final += f"\n\n[CTX]\n{ctx}"

        logger.info(f"[SYSTEM PROMPT Final ]\n{system_prompt_final}")

        for i in range(max_iterations):
            logger.info(f"[REASONING LOOP] Itération {i+1}")

            if i == 0 and initial_prompt:
                prompt = initial_prompt
            else:
                prompt = self._format_prompt(objective, result, history)

            try:
                llm_output = await call_llm(prompt, system_prompt_final, json_mode=True)
                parsed = self._safe_parse_llm_response(llm_output)
            except Exception as e:
                error = str(e)
                logger.exception("[LLM ERROR] Erreur lors de l'appel au LLM ou du parsing JSON.")
                break

            # Vérification de l’appel outil obligatoire à la 1ère itération
            if i == 0:
                if parsed.get("action") != "invoke_tool" or parsed.get("tool") != "workforce_information":
                    logger.warning("[LLM] A ignoré l'appel d'outil obligatoire en première itération.")
                    result = {
                        "error": "LLM did not invoke mandatory tool 'workforce_information' as required.",
                        "llm_output": parsed
                    }
                    break

            interactions.append(parsed)
            history.append(parsed)

            # Cas 1 : arrêt demandé explicitement par le LLM
            if parsed.get("action") == "complete_task":
                logger.info("[LLM] Tâche complétée par le LLM.")
                result = parsed
                break

            # Cas 2 : arrêt implicite si la réponse contient un `final_result` avec `status`
            if "final_result" in parsed and isinstance(parsed["final_result"], dict):
                status = parsed["final_result"].get("status")
                if status in ["clarified", "needs_confirmation_or_clarification"]:
                    logger.info(f"[LLM] Final result détecté avec status='{status}'")
                    result = parsed["final_result"]
                    break

            # Cas 3 : appel outil
            tool_name = parsed.get("tool")
            tool_input = parsed.get("input", "")

            if tool_name is not None:
                if allowed_tools and tool_name not in allowed_tools:
                    logger.warning(f"[TOOL] Tool '{tool_name}' non autorisé.")
                    result = {"error": f"Tool '{tool_name}' not allowed."}
                    break
                try:
                    tool_result = await self.invoke_tool(tool_name, tool_input)
                    result = {"tool_result": tool_result, "tool": tool_name}
                    logger.info(f"[TOOL] Outil {tool_name} invoqué avec succès.")
                except Exception as e:
                    result = {"error": f"Erreur exécution outil '{tool_name}': {e}"}
                    logger.exception(f"[TOOL ERROR] Échec de l'appel de l'outil {tool_name}")
                    break
            elif i == 0 and parsed.get("action") != "invoke_tool":
                logger.warning("[LLM] Aucun outil invoqué dans la première itération, ce qui est requis.")
                result = {"error": "Aucun outil invoqué dans la première itération"}
                break
            elif parsed.get("action") == "invoke_tool" and parsed.get("tool") is None:
                logger.warning("[LLM] Action 'invoke_tool' sans nom d’outil associé.")
                result = {"error": "Action 'invoke_tool' sans outil spécifié."}
                break

        return {
            "objective": objective,
            "final_result": result,
            "interactions": interactions,
            "error": error
        }
    async def execute_llm_action_loop(self, objective: str, context_id: str) -> str:
        return await self.run_reasoning_loop_with_tools(objective, context_id)

    async def invoke_tool(self, tool_name: str, payload: dict) -> Any:
        if tool_name == "workforce_information":
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
                logger.error(f"[TOOL] workforce_information failed: {e}", exc_info=True)
                return {"error": str(e)}

        logger.warning(f"[INVOKE] Appel outil inconnu : {tool_name}")
        return {"status": "noop"}

    def _safe_parse_llm_response(self, llm_output: Any) -> dict:
        """Parse la réponse LLM même si ce n’est pas exactement un JSON bien formé."""
        if isinstance(llm_output, dict):
            return llm_output

        try:
            return json.loads(llm_output)
        except Exception as e:
            logger.warning(f"[LLM RESPONSE PARSE] Échec du parsing JSON: {e}")
            return {"error": f"Invalid JSON: {str(e)}", "raw_output": llm_output}
    
    def _format_prompt(self, objective: str, result: Optional[dict], history: Optional[list] = None) -> str:
        prompt_parts = []

        # 🧠 Bloc objectif
        cleaned_objective = objective.strip() if objective else "[Non défini]"
        prompt_parts.append(f"[OBJECTIF]\n{cleaned_objective}")

        # 🧠 Bloc historique (les 3 derniers maximum)
        if history:
            prompt_parts.append("\n[HISTORIQUE]")
            for i, h in enumerate(history[-3:], 1):
                action = h.get("action", "—")
                tool = h.get("tool", "—")
                input_val = h.get("input", "")
                prompt_parts.append(f"\nÉtape {i}:")
                prompt_parts.append(f"- Action: {action}")
                prompt_parts.append(f"- Tool: {tool}")
                prompt_parts.append(f"- Input: {json.dumps(input_val)}")
                if "tool_result" in h:
                    prompt_parts.append(f"- Résultat Outil: {json.dumps(h['tool_result'], indent=2)}")
                elif tool:
                    prompt_parts.append(f"- Résultat Outil: Indisponible ou erreur")
                else:
                    prompt_parts.append(f"- Résultat: {json.dumps(h)}")

        # 🧠 Bloc dernier résultat (utile si outil exécuté ou erreur)
        if result:
            prompt_parts.append(f"\n[DERNIER RÉSULTAT]\n{json.dumps(result, indent=2)}")

        # ✅ Clôture du prompt
        prompt_parts.append("\nQuelle est la prochaine action ?")

        return "\n".join(prompt_parts)


    async def handle_collaborative_message(self, msg_type: str, payload: dict) -> dict:
        method = getattr(self, f"on_{msg_type.lower()}", None)
        if method:
            return await method(payload)
        return {"status": "unsupported", "msg_type": msg_type}

    async def on_capability_check(self, payload: dict) -> dict:
        prompt = f"Tu es un agent intelligent avec des outils. Voici la tâche : {payload}"
        system_prompt = "Tu évalues ta capacité à réaliser cette tâche en toute honnêteté."
        response = await call_llm(prompt, system_prompt, json_mode=True)
        result = json.loads(response)

        self._record_collaboration(
            sender_agent=payload.get("sender", "unknown"),
            receiver_agent=self.__class__.__name__,
            msg_type="CAPABILITY_CHECK",
            context_id=payload.get("context_id"),
            llm_prompt=prompt,
            llm_output=response,
            result_summary=str(result),
        )
        return result

    @abstractmethod
    async def process(self, input_data: Any, context_id: str | None = None) -> Any:
        pass
