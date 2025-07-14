# src/tools/development_tools.py
# src/tools/development_tools.py

import os
import asyncio
import re
import json
from typing import Optional
from src.shared.llm_client import call_llm
from src.services.environment_manager.environment_manager import EnvironmentManager


# --- Helpers internes --- #

async def _generate_code_from_specs(specs: dict) -> str:
    """Appelle le LLM pour générer du code Python à partir de spécifications structurées."""
    system_prompt = (
        "Tu es un développeur IA expert en Python. Ta mission est de générer du code Python propre, "
        "fonctionnel et bien commenté, basé sur les spécifications fournies. "
        "N'inclus que le code dans ta réponse."
    )
    prompt = (
        f"Objectif : {specs.get('objective', '')}\n"
        f"Instructions : {specs.get('local_instructions', [])}\n"
        f"Critères : {specs.get('acceptance_criteria', [])}\n"
        "Génère UNIQUEMENT le code."
    )
    raw = await call_llm(prompt, system_prompt, json_mode=False)
    return re.sub(r'^\s*```(?:[a-zA-Z0-9]*)?\n|\n\s*```\s*$', '', raw, flags=re.MULTILINE).strip()


async def _generate_test_code_from_specs(specs: dict) -> str:
    """Appelle le LLM pour générer un fichier de tests à partir de spécifications."""
    system_prompt = (
        "Tu es un ingénieur QA expert en Python. Génère un fichier Python fonctionnel de tests, "
        "basé sur les spécifications suivantes. Retourne UNIQUEMENT le code."
    )
    prompt = (
        f"Objectif des tests : {specs.get('objective', '')}\n"
        f"Instructions : {', '.join(specs.get('local_instructions', [])) or 'Aucune'}\n"
        f"Critères : {', '.join(specs.get('acceptance_criteria', [])) or 'Non spécifiés'}\n"
    )
    if specs.get("deliverable"):
        prompt += f"Livrable à tester :\n```\n{specs['deliverable']}\n```\n"
    if specs.get("input_artifacts_content"):
        prompt += f"Artefacts d'entrée :\n```json\n{json.dumps(specs['input_artifacts_content'], indent=2)}\n```\n"

    raw = await call_llm(prompt, system_prompt, json_mode=False)
    return re.sub(r'^\s*```(?:[a-zA-Z0-9]*)?\n|\n\s*```\s*$', '', raw, flags=re.MULTILINE).strip()


# --- Outils exposés --- #

async def generate_code_and_write_file(input: dict, context_id: Optional[str] = None) -> dict:
    """Génère du code (si manquant) à partir des specs et l’écrit localement ou dans l’environnement du plan."""
    file_path = input.get("file_path")
    code = input.get("code")
    specs = {
        "objective": input.get("objective"),
        "local_instructions": input.get("local_instructions"),
        "acceptance_criteria": input.get("acceptance_criteria")
    }

    if not file_path:
        return {"error": "Champ 'file_path' manquant."}

    if not code:
        code = await _generate_code_from_specs(specs)

    try:
        if context_id:
            manager = EnvironmentManager()
            await manager.write_file_to_environment(context_id, file_path, code)
            return {"status": "success", "location": "environment", "path": file_path}
        else:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            return {"status": "success", "location": "local", "path": file_path}
    except Exception as e:
        return {"error": str(e)}


async def execute_command(input: dict, context_id: Optional[str] = None) -> dict:
    """Exécute une commande shell dans un environnement (ou localement si context absent)."""
    command = input.get("command")
    workdir = input.get("workdir", "/app")

    if not command:
        return {"error": "Champ 'command' requis."}

    try:
        if context_id:
            manager = EnvironmentManager()
            result = await manager.execute_command_in_environment(context_id, command, workdir)
            return {"status": "success", "location": "environment", **result}
        else:
            proc = await asyncio.create_subprocess_shell(
                command, cwd=workdir,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return {
                "status": "success" if proc.returncode == 0 else "error",
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": proc.returncode,
                "location": "local"
            }
    except Exception as e:
        return {"error": str(e)}


async def read_file(input: dict, context_id: Optional[str] = None) -> dict:
    file_path = input.get("file_path")
    if not file_path:
        return {"error": "file_path requis."}
    try:
        if context_id:
            manager = EnvironmentManager()
            content = await manager.read_file_from_environment(context_id, file_path)
            return {"content": content, "location": "environment"}
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                return {"content": f.read(), "location": "local"}
    except Exception as e:
        return {"error": str(e)}


async def list_directory(input: dict, context_id: Optional[str] = None) -> dict:
    path = input.get("path", ".")
    try:
        if context_id:
            manager = EnvironmentManager()
            files = await manager.list_files_in_environment(context_id, path)
            return {"files": files, "location": "environment"}
        else:
            files = os.listdir(path)
            return {"files": files, "location": "local"}
    except Exception as e:
        return {"error": str(e)}


async def complete_task(input: dict, context_id: Optional[str] = None) -> dict:
    return {
        "status": "complete",
        "summary": input.get("summary", "Objectif terminé."),
    }
