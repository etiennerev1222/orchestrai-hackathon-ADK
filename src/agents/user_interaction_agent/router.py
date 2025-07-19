from fastapi import APIRouter, UploadFile, File, Form
from src.agents.user_interaction_agent.logic import UserInteractionAgentLogic

router = APIRouter()
agent_logic = UserInteractionAgentLogic()

@router.post("/upload-file")
async def upload_file(
    context_id: str = Form(...),
    file: UploadFile = File(...)
):
    """Point d'API pour téléverser un fichier."""
    file_content = await file.read()
    input_data = {
        "action": "receive_file",
        "file_name": file.filename,
        "file_content": file_content,
    }
    result, _ = await agent_logic.process(input_data, context_id)
    return result

