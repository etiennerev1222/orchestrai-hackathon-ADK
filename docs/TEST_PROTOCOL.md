# Protocole de tests des agents

Ce document décrit la procédure pour vérifier individuellement le bon fonctionnement de chaque agent du projet **OrchestrAI**.

## 1. Préparation commune

1. Installer les dépendances principales puis celles dédiées aux tests :
   ```bash
   pip install -r requirements.txt
   pip install -r tests/requirements.txt
   ```
2. Lancer la batterie de tests unitaires et d'intégration :
   ```bash
   pytest
   ```
   Certains tests nécessitent l'accès à Google Cloud (Firestore, Vertex AI, GKE) et peuvent échouer si ces services ne sont pas configurés.

## 2. Vérification agent par agent

Chaque agent peut être exécuté localement via son serveur A2A puis testé avec le script associé du dossier `tests/`.

### Decomposition Agent
1. Démarrer le serveur :
   ```bash
   python -m src.agents.decomposition_agent.server
   ```
2. Exécuter le client de test :
   ```bash
   python tests/test_decoposeur.py
   ```

### Development Agent
1. Démarrer le serveur ou disposer d'un pod accessible via `kubectl`.
2. Lancer le script d'intégration :
   ```bash
   bash tests/run_test_development_agent.sh
   ```
   Ce test envoie une tâche simple et vérifie qu'un artefact est généré.

### Environment Manager
1. Assurer la présence du service dans votre cluster Kubernetes.
2. Utiliser le script :
   ```bash
   bash tests/run_test_environment_manager.sh
   ```
   Celui‑ci crée un environnement, télécharge un fichier, l'exécute puis supprime le pod.

### Evaluator, Reformulator et Validator
1. Démarrer chaque serveur avec la commande `python -m src.agents.<agent>.server`.
2. Lancer les clients correspondants :
   ```bash
   python tests/test_evaluator_client.py
   python tests/test_reformulator_client.py
   ```
   Les réponses retournées sont affichées dans la console.

### User Interaction Agent
1. Démarrer le serveur :
   ```bash
   python -m src.agents.user_interaction_agent.server
   ```
2. Exécuter l'exemple de simulation :
   ```bash
   python tests/simule_UserInteractionAgentLogic.py
   ```

### Testing Agent
Cet agent s'exécute généralement après le Development Agent. Une fois un projet généré, il peut être appelé via :
```bash
python -m src.agents.testing_agent.server
```
Les tests à proprement parler dépendent du code produit et sont donc déclenchés par le plan d'exécution.

## 3. Validation finale

Une fois tous les tests terminés sans erreur, les agents peuvent être déployés sur les environnements Cloud Run ou GKE. Pour plus de détails sur la mise en production, se référer aux scripts du dossier `scripts/` et à la documentation principale du dépôt.
