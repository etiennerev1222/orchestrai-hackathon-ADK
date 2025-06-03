# Dans un nouveau fichier tests/unit/test_decomposition_logic.py
import pytest # ou unittest
import asyncio
from unittest.mock import patch, MagicMock # ou AsyncMock pour Python 3.8+

from src.agents.decomposition_agent.logic import DecompositionAgentLogic
# Assurez-vous que GEMINI_API_KEY est mockée ou non requise pour ce test si llm_client le vérifie
# @patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}) # Si nécessaire

@pytest.mark.asyncio
async def test_decomposition_logic_valid_plan_mocked_llm():
    logic = DecompositionAgentLogic()
    sample_plan_text = "Planifier un voyage à Paris pour 3 jours."
    
    # JSON attendu que le LLM est censé retourner (sous forme de chaîne)
    expected_llm_output_str = """
    {
        "global_context": "Planification d'un voyage de 3 jours à Paris.",
        "instructions": ["Prioriser le budget et les activités culturelles."],
        "tasks": [
            {
                "id": "T01_Paris",
                "nom": "Recherche Vols",
                "description": "Rechercher et comparer les vols aller-retour pour Paris pour les dates souhaitées.",
                "type": "exploratory",
                "dependances": [],
                "instructions_locales": ["Utiliser des comparateurs en ligne", "Vérifier les aéroports proches"],
                "acceptance_criteria": ["Au moins 3 options de vol identifiées", "Prix et horaires notés"],
                "assigned_agent_type": "web_research",
                "sous_taches": []
            },
            {
                "id": "T02_Paris",
                "nom": "Réservation Hébergement",
                "description": "Choisir et réserver un hébergement pour 2 nuits.",
                "type": "executable",
                "dependances": ["T01_Paris"],
                "instructions_locales": ["Préférer un hôtel central ou un Airbnb bien noté", "Budget max 150 EUR/nuit"],
                "acceptance_criteria": ["Hébergement réservé et confirmé", "Adresse et détails de check-in obtenus"],
                "assigned_agent_type": "general_analysis", 
                "sous_taches": []
            }
        ]
    }
    """
    
    # Mocker src.shared.llm_client.call_llm utilisé par DecompositionAgentLogic
    # Si vous utilisez Python 3.8+, vous pouvez utiliser AsyncMock directement.
    # Pour les versions antérieures, une coroutine factice peut être utilisée avec MagicMock.
    mock_call_llm = MagicMock(return_value=asyncio.Future())
    mock_call_llm.return_value.set_result(expected_llm_output_str)

    with patch('src.agents.decomposition_agent.logic.call_llm', mock_call_llm):
        result_dict = await logic.process(sample_plan_text, "test_ctx_decompose_01")

    assert isinstance(result_dict, dict)
    assert result_dict["global_context"] == "Planification d'un voyage de 3 jours à Paris."
    assert len(result_dict["tasks"]) == 2
    assert result_dict["tasks"][0]["id"] == "T01_Paris"
    assert result_dict["tasks"][0]["assigned_agent_type"] == "web_research"
    assert result_dict["tasks"][1]["dependances"] == ["T01_Paris"]

    # Vérifier que call_llm a été appelé avec les bons arguments (le prompt)
    # Cela nécessite de regarder le contenu du prompt généré dans la logique.
    # mock_call_llm.assert_called_once() # Ou assert_called_once_with(...) si vous voulez vérifier les args