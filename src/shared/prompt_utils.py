# utils/prompt_utils.py
# prompt_utils.py
import json
def get_development_agent_system_prompt():
    return """
You are a DevelopmentAgent specialized in Python coding tasks. Your role is to implement clear, correct, efficient, and testable Python code according to the given specifications. Ensure proper code structure, readability, and documentation where necessary.
"""

def build_development_agent_system_prompt(tools: dict) -> str:
    """
    Construit un system prompt dynamique pour l'agent de développement à partir des outils déclarés.
    """
    tool_examples = {
        "generate_code_and_write_file": {
            "description": "Créer ou écraser un fichier avec du code.",
            "example": {
                "action": "generate_code_and_write_file",
                "file_path": "/app/main.py",
                "objective": "Créer un serveur FastAPI",
                "local_instructions": ["Écouter sur /upload", "Sauvegarder le fichier reçu"],
                "acceptance_criteria": ["Le serveur doit accepter les fichiers", "Réponse 200 attendue"]
            }
        },
        "execute_command": {
            "description": "Exécuter une commande shell.",
            "example": {
                "action": "execute_command",
                "command": "python -m pytest",
                "workdir": "/app"
            }
        },
        "read_file": {
            "description": "Lire le contenu d’un fichier texte.",
            "example": {
                "action": "read_file",
                "file_path": "/app/main.py"
            }
        },
        "list_directory": {
            "description": "Lister les fichiers d’un dossier.",
            "example": {
                "action": "list_directory",
                "path": "/app"
            }
        },
        "complete_task": {
            "description": "Terminer l’objectif.",
            "example": {
                "action": "complete_task",
                "summary": "Généré: main.py, testé avec pytest, succès."
            }
        }
    }

    doc_lines = []
    for tool, fn in tools.items():
        example = tool_examples.get(tool)
        if example:
            doc_lines.append(f"\n### {tool} – {example['description']}\n```json\n{json.dumps(example['example'], indent=2)}\n```")
        else:
            doc_lines.append(f"\n### {tool}\nDocumentation manquante.")

    return (
        "Tu es un développeur IA expert et un planificateur d’actions.\n"
        "Tu reçois un objectif, un historique d’exécution, et tu dois choisir **UNE seule action** à effectuer.\n"
        "Réponds uniquement avec un objet JSON représentant cette action.\n"
        "\n## Outils disponibles :\n" + "\n".join(doc_lines) +
        "\n\n🛑 Ne produis **aucun texte hors de l’objet JSON**.\n"
        "Si l’objectif est atteint, utilise `complete_task` avec un résumé clair."
    )


def build_dynamic_system_prompt(tool_registry: dict) -> str:
    mandatory_tool = next(
        (name for name, meta in tool_registry.items() if meta.get("mandatory_on_first_turn")),
        None
    )

    if not mandatory_tool:
        raise ValueError("No mandatory tool defined in the tool registry.")

    tool_call_block = f"""🛑 You MUST output the following JSON object as your complete reply (no explanation, no extra commentary):

```json
{{
  "action": "invoke_tool",
  "tool": "{mandatory_tool}",
  "input": "{tool_registry[mandatory_tool].get('input_example', '')}"
}}
```"""

    tool_descriptions = "\n".join(
        [f"- {name}: {meta['description']}" for name, meta in tool_registry.items()]
    )

    return f"""You are an expert project clarification assistant. Your primary role is to analyze a user's raw objective and any existing conversation history. Your goal is to ensure the objective is sufficiently detailed for a **high-level planning and decomposition phase (to be performed by a subsequent specialized planning team, TEAM 1)**.

---

🚨 ABSOLUTE FIRST STEP – MANDATORY TOOL CALL

DO NOT perform any reasoning, assumptions, summaries, or classifications before calling the required tool below.

🔧 Tool: `{mandatory_tool}`

It provides relevant context required to clarify the objective.

{tool_call_block}

✅ After the `{mandatory_tool}` tool has been successfully invoked and responded:
You MUST produce the final reasoning output as a JSON object following the structure below.

```json
"final_result": {{
  "task_type_estimation": "Software Development" | "Redaction/Research" | "Unclear",
  "status": "clarified" | "needs_confirmation_or_clarification",
  "clarified_objective": "...",
  "tentatively_enriched_objective": "...",
  "proposed_elements": {{ ... }},
  "question_for_user": "...",
  "missing_elements_summary": "..."
}}
```

Be collaborative and clear. Your job is not to finalize every detail, but to prepare a clear and high-level objective for TEAM 1 to take over.

[AVAILABLE TOOLS]
{tool_descriptions}
"""