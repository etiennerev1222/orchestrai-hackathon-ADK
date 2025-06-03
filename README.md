OrchestrAI Hackathon ADK - Système de Planification Multi-Agents Interactif
Ce projet est une implémentation d'un système multi-agents pour la clarification interactive d'objectifs, suivie par la génération, l'évaluation, la validation et la révision itérative de plans. Il utilise un Agent Development Kit (ADK) basé sur le protocole A2A, avec une persistance des données via Firestore et une découverte de services gérée par un Gestionnaire de Ressources et d'Agents (GRA). Les agents intègrent des modèles de langage (LLM via Gemini) pour leur logique métier.

La principale évolution par rapport à une planification purement autonome est l'introduction d'un GlobalSupervisorLogic et d'un UserInteractionAgent, qui collaborent pour affiner l'objectif initial avec l'utilisateur avant de lancer le processus de planification détaillé (désormais appelé "TEAM 1").

Table des Matières
Architecture Fonctionnelle
Étape 1 : Clarification de l'Objectif (Orchestrée par GlobalSupervisorLogic)
Étape 2 : Génération et Itération de Plan (TEAM 1 : PLAN GENERATION, Orchestrée par PlanningSupervisorLogic)
Architecture Technique
Concepts Clés Mis en Œuvre
Architecture Générale Détaillée
Prérequis
Installation
Utilisation
Structure du Projet
Pistes d'Évolution Futures
Architecture Fonctionnelle
Cette section décrit les grandes capacités du système et comment les différents composants interagissent pour atteindre l'objectif global de planification, désormais en deux phases distinctes.

Étape 1 : Clarification de l'Objectif (Orchestrée par GlobalSupervisorLogic)
Cette phase cruciale a été ajoutée pour garantir que l'objectif soumis par l'utilisateur est suffisamment clair et détaillé avant d'engager des ressources dans la planification.

Soumission d'Objectif : L'utilisateur initie le processus en soumettant un objectif brut via l'interface Streamlit (), qui communique avec l'API du GRA ().
Orchestration Globale : Le GlobalSupervisorLogic prend la main (). Il enregistre l'objectif initial et l'état du dialogue dans la collection global_plans de Firestore.
Dialogue Interactif via UserInteractionAgent :
Le GlobalSupervisorLogic invoque le UserInteractionAgent ().
Cet agent utilise un LLM pour analyser l'objectif, estimer son type (ex: "Software Development", "Redaction/Research"), identifier les manques d'informations critiques pour la planification de haut niveau par TEAM 1, proposer des enrichissements, et si nécessaire, formuler une question précise à l'utilisateur. Il retourne un JSON structuré.
L'état du plan global passe à CLARIFICATION_PENDING_USER_INPUT.
Boucle de Clarification via Streamlit :
L'interface affiche la question de l'agent, l'objectif enrichi proposé (éditable), et les éléments assumés par l'agent.
L'utilisateur peut répondre à la question et/ou modifier directement l'objectif enrichi.
En soumettant sa réponse, le GlobalSupervisorLogic peut relancer le UserInteractionAgent pour un nouveau cycle de clarification (jusqu'à MAX_CLARIFICATION_ATTEMPTS).
Acceptation de l'Objectif : À tout moment, si l'objectif (enrichi par l'agent ou modifié par l'utilisateur) est jugé satisfaisant, l'utilisateur clique sur "Valider Objectif Actuel & Lancer TEAM 1". Le GlobalSupervisorLogic marque l'objectif comme OBJECTIVE_CLARIFIED et initie la phase suivante.
Étape 2 : Génération et Itération de Plan (TEAM 1 : PLAN GENERATION, Orchestrée par PlanningSupervisorLogic)
Une fois l'objectif clarifié et validé par l'utilisateur, cette phase prend en charge la création du plan détaillé.

Orchestration Centralisée (TEAM 1) : Le PlanningSupervisorLogic pilote le flux de cette équipe d'agents. Il reçoit l'objectif clarifié du GlobalSupervisorLogic.
Reformulation : L'ReformulatorAgent prend cet objectif (ou un plan à réviser avec feedback) et génère un plan d'action détaillé en utilisant un LLM.
Évaluation : L'EvaluatorAgent analyse le plan reformulé, identifie forces/faiblesses, et donne un score de faisabilité (via LLM), retournant un JSON structuré.
Validation : Le ValidatorAgent prend le plan et son évaluation, et (via LLM) approuve ou rejette le plan avec une justification.
Boucle de Révision : En cas de rejet par le validateur, le PlanningSupervisorLogic intègre les commentaires de rejet dans un nouvel objectif et relance une reformulation (jusqu'à max_revisions). (Voir les logs pour un exemple de cette boucle).
Capacités Transverses :

Découverte de Services : Les agents s'enregistrent auprès du GRA. Les superviseurs interrogent le GRA pour localiser les agents nécessaires en fonction de leurs compétences.
Persistance des Données : L'état complet des plans globaux (collection global_plans) et des plans détaillés de TEAM 1 (graphe de tâches task_graphs, artefacts, historique) est stocké dans Firestore pour la résilience et le suivi. Les informations d'enregistrement des agents sont également persistées dans Firestore par le GRA ().
Interface Utilisateur et Monitoring :
Une application Streamlit permet de soumettre des objectifs, de gérer le dialogue de clarification, de lister les plans globaux et leur état, de visualiser les graphes de tâches de TEAM 1, de consulter les artefacts et de voir les agents enregistrés.
Architecture Technique
Cette section détaille les technologies, les protocoles et les composants techniques.

Langage et Frameworks Backend :
Python 3.11+
Agents et GRA : Serveurs ASGI basés sur Uvicorn.
Les agents utilisent le SDK A2A (A2AStarletteApplication).
Le GRA utilise FastAPI pour ses endpoints API.
Logique Métier des Agents : Intégration de modèles de langage via l'API Gemini (gérée par src/shared/llm_client.py), supportant le mode JSON pour les sorties structurées.
Base de Données :
Google Cloud Firestore : Utilisé en mode NoSQL (orienté document) pour :
Persistance des global_plans (collection global_plans).
Persistance des TaskGraph de chaque plan de TEAM 1 (collection task_graphs).
Registre des agents (collection agents gérée par le GRA).
Publication de l'URL du GRA (document service_registry/gra_instance_config).
Communication Inter-Services :
Protocole A2A : Pour la communication entre les Superviseurs et les agents spécialisés, gérée par src/clients/a2a_api_client.py.
API REST (HTTP/JSON) : Pour la communication entre :
Les agents et le GRA (pour l'enregistrement).
Les superviseurs et le GRA (pour la découverte d'agents).
Le front-end Streamlit et le GRA (pour la soumission d'objectifs, le dialogue de clarification, et la récupération de données sur les plans).
La bibliothèque httpx est utilisée pour les appels HTTP asynchrones.
Front-End :
Streamlit : Pour l'interface utilisateur de démonstration et de suivi.
Graphviz : Pour la génération et l'affichage des graphes de tâches.
Gestion des Tâches Asynchrones :
asyncio est utilisé extensivement.
Le GlobalSupervisorLogic lance le traitement des plans de TEAM 1 en tâche de fond (asyncio.create_task()) pour ne pas bloquer les requêtes HTTP et permettre au superviseur de gérer d'autres plans ou interactions.
Concepts Clés Mis en Œuvre
Architecture Microservices/Agents : Chaque agent et le GRA sont des services indépendants, favorisant la modularité et la scalabilité.
Orchestration à Deux Niveaux : Le GlobalSupervisorLogic gère l'interaction utilisateur de haut niveau et le cycle de vie global, tandis que le PlanningSupervisorLogic orchestre la génération détaillée et autonome du plan.
Agent Interactif (Human-in-the-Loop) : Introduction du UserInteractionAgent pour un dialogue collaboratif avec l'utilisateur afin de clarifier l'objectif, utilisant des états A2A comme input_required.
Orchestration de Tâches (TEAM 1) : Le PlanningSupervisorLogic agit comme un orchestrateur, gérant un graphe de dépendances de tâches (TaskGraph).
Service Discovery : Le GRA et le mécanisme de publication/découverte via Firestore permettent aux services de se trouver dynamiquement.
Persistance des Données Structurée : Utilisation de collections Firestore distinctes (global_plans, task_graphs, agents) pour une meilleure organisation.
Traitement Itératif et Réflexif (TEAM 1) : La boucle de révision permet au système d'apprendre des rejets et de tenter d'améliorer les plans.
Intelligence Artificielle (LLM) : Les agents exploitent la puissance des LLM (Gemini) pour des tâches complexes de génération de texte, d'analyse, de dialogue et de prise de décision, y compris la génération de JSON structuré.
Communication Asynchrone : L'ensemble du système est conçu pour fonctionner de manière asynchrone.
Architecture Générale Détaillée
Le système est composé des principaux éléments suivants :

Agents Spécialisés :

UserInteractionAgent (Nouvel Agent) :
Analyse l'objectif initial de l'utilisateur, identifie les ambiguïtés ou les manques.
Pose des questions de clarification à l'utilisateur via un LLM.
Propose un objectif enrichi et des éléments assumés.
Retourne son analyse et ses questions au format JSON structuré.
ReformulatorAgent : Prend un objectif (clarifié ou à réviser) et le transforme en un plan détaillé et structuré.
EvaluatorAgent : Analyse un plan reformulé, identifie ses forces, faiblesses, risques et lui attribue un score de faisabilité. Retourne son analyse au format JSON.
ValidatorAgent : Prend l'évaluation et le plan, et décide si le plan est approuvé ou rejeté, en fournissant une justification.
Chaque agent est un serveur A2A autonome (basé sur Starlette/Uvicorn).
Gestionnaire de Ressources et d'Agents (GRA) :

Un service central (basé sur FastAPI/Uvicorn) qui utilise Firestore pour la persistance.
Registre d'Agents : Permet aux agents de s'enregistrer au démarrage (nom, URL, compétences) et aux superviseurs de les découvrir.
Publication de sa propre URL : Le GRA publie sa propre URL dans un document Firestore connu (service_registry/gra_instance_config) pour que les autres services puissent le trouver dynamiquement.
API Gateway pour le Front-End : Expose des endpoints API pour la gestion complète du cycle de vie des plans globaux (initiation, clarification, acceptation) et la consultation des plans détaillés de TEAM 1.
Superviseurs (Orchestrateurs) :

GlobalSupervisorLogic (Nouvel Orchestrateur) :
Le cerveau de la phase de clarification interactive.
Gère un GlobalPlan persistant sur Firestore (collection global_plans) pour suivre l'état du dialogue, l'historique de la conversation, les tentatives de clarification.
Interroge le GRA pour trouver le UserInteractionAgent.
Orchestre la séquence : Interaction Utilisateur -> Validation Utilisateur -> Lancement TEAM 1.
PlanningSupervisorLogic (Orchestrateur de TEAM 1) :
Le cerveau du système de génération de plan détaillé (TEAM 1).
Gère un TaskGraph persistant sur Firestore (collection task_graphs) pour suivre l'état et les dépendances des tâches de planification.
Interroge le GRA pour trouver les agents de TEAM 1 (Reformulator, Evaluator, Validator).
Orchestre la séquence : Reformulator -> Evaluator -> Validator.
Implémente une boucle de révision : si un plan est rejeté, il génère un nouvel objectif incluant le feedback et relance une reformulation (jusqu'à max_revisions).
Client LLM Partagé :

Un module (src/shared/llm_client.py) pour interagir avec l'API Gemini, utilisé par la logique de tous les agents.
Front-End Streamlit (src/app_frontend.py) :

Une interface utilisateur pour soumettre de nouveaux objectifs, interagir durant la phase de clarification (répondre aux questions, modifier l'objectif proposé), valider l'objectif clarifié pour lancer TEAM 1, visualiser la liste des plans globaux, afficher les graphes de tâches de TEAM 1 (avec graphviz), et consulter les artefacts.
Affiche également le statut des agents enregistrés auprès du GRA.
Interagit avec le backend via des endpoints API REST exposés par le GRA.
Prérequis
Python 3.11+
Compte Google Cloud avec un projet configuré et Firestore activé.
Fichier de clé de compte de service JSON pour l'accès à Firestore (GOOGLE_APPLICATION_CREDENTIALS).
Variables d'environnement configurées :
GOOGLE_APPLICATION_CREDENTIALS : Chemin vers votre fichier de clé de service.
GEMINI_API_KEY : Votre clé API pour Google Gemini.
(Optionnel) GRA_PUBLIC_URL : Si l'URL publique du GRA doit être différente de http://localhost:8000 (par exemple, en cas de déploiement ou d'utilisation de tunnels).
(Optionnel) AGENT_XXX_PUBLIC_URL : Si les URLs publiques des agents doivent être surchargées (par exemple AGENT_USERINTERACTIONAGENTSERVER_PUBLIC_URL).
Les bibliothèques Python listées dans requirements.txt.
Installation
Clonez le dépôt :

Bash

git clone <URL_DU_DEPOT>
cd orchestrai-hackathon-ADK
Créez un environnement virtuel et activez-le :

Bash

python -m venv venv
source venv/bin/activate  # Sur Linux/macOS
# venv\Scripts\activate    # Sur Windows
Installez les dépendances :
Le fichier requirements.txt devrait contenir au minimum (adaptez les versions si besoin) :

Plaintext

# requirements.txt
firebase-admin
google-generativeai
httpx
uvicorn[standard]
fastapi
a2a-sdk
streamlit
graphviz
pydantic
Puis installez :

Bash

pip install -r requirements.txt
Configurez les variables d'environnement (voir section Prérequis).

(Si graphviz n'est pas déjà installé sur votre système) :

Sur Debian/Ubuntu : sudo apt-get install graphviz
Sur macOS (avec Homebrew) : brew install graphviz
Utilisation
Pour lancer le système complet, 4 agents et le GRA doivent être démarrés.

Démarrez le Gestionnaire de Ressources et d'Agents (GRA) :
Ouvrez un terminal et exécutez :

Bash

python -m src.services.gra.server
Vérifiez les logs pour la confirmation de la connexion à Firestore et la publication de son URL.

Démarrez les Agents (chacun dans un nouveau terminal) :

Agent d'Interaction Utilisateur (UserInteractionAgentServer):
Bash

python -m src.agents.user_interaction_agent.server
Agent Reformulateur (ReformulatorAgentServer):
Bash

python -m src.agents.reformulator.server
Agent Évaluateur (EvaluatorAgentServer):
Bash

python -m src.agents.evaluator.server
Agent Validateur (ValidatorAgentServer):
Bash

python -m src.agents.validator.server
Vérifiez les logs de chaque agent pour confirmer leur enregistrement auprès du GRA. Le GRA devrait aussi logger ces enregistrements.

Lancez l'Application Streamlit (Front-End) :
Ouvrez un nouveau terminal et exécutez :

Bash

streamlit run src/app_frontend.py
Ouvrez l'URL fournie par Streamlit (généralement http://localhost:8501) dans votre navigateur.

Utilisez l'Interface :

Soumettez un nouvel objectif via le formulaire dans la barre latérale.
Si l'UserInteractionAgent a besoin de clarifications, des questions et des propositions apparaîtront. Vous pourrez y répondre ou modifier l'objectif enrichi proposé.
Cliquez sur "Soumettre Réponse pour Continuer Clarification" pour itérer avec l'agent, ou "Valider Objectif Actuel & Lancer TEAM 1" lorsque l'objectif est satisfaisant.
Suivez l'évolution des plans globaux (phase de clarification) et des plans de TEAM 1 (graphe de tâches) dans la liste et la vue détaillée.
Consultez le statut des agents.
Pour lancer un plan TEAM 1 directement via le script (sans l'interface Streamlit et la phase de clarification globale) :
(Ceci correspond à l'ancien mode de fonctionnement, utile pour tester TEAM 1 isolément si l'objectif est déjà clair).
Assurez-vous que le GRA et les 3 agents de TEAM 1 (Reformulator, Evaluator, Validator) sont en cours d'exécution, puis :

Bash

python -m src.run_orchestrator
(Note: run_orchestrator.py initie directement le PlanningSupervisorLogic)

Structure du Projet (Principaux Dossiers et Fichiers)
orchestrai-hackathon-ADK/
├── src/
│   ├── agents/
│   │   ├── user_interaction_agent/  # NOUVEL AGENT pour la clarification
│   │   │   ├── logic.py
│   │   │   ├── executor.py
│   │   │   └── server.py
│   │   ├── reformulator/
│   │   │   ├── logic.py
│   │   │   ├── executor.py
│   │   │   └── server.py
│   │   ├── evaluator/
│   │   │   └── ... (idem)
│   │   └── validator/
│   │       └── ... (idem)
│   ├── clients/
│   │   └── a2a_api_client.py
│   ├── orchestrators/
│   │   ├── global_supervisor_logic.py    # NOUVEAU superviseur pour la phase de clarification
│   │   └── planning_supervisor_logic.py  # Superviseur pour TEAM 1 (planification détaillée)
│   ├── services/
│   │   └── gra/
│   │       └── server.py                 # Gestionnaire de Ressources et d'Agents (API Gateway)
│   └── shared/
│       ├── base_agent_executor.py
│       ├── base_agent_logic.py
│       ├── firebase_init.py              # Module d'initialisation centralisé pour Firestore
│       ├── llm_client.py
│       ├── service_discovery.py
│       └── task_graph_management.py
├── src/app_frontend.py                   # Interface Streamlit (mise à jour pour interaction)
├── src/run_orchestrator.py               # Script pour lancer un plan TEAM 1 en backend
├── .gitignore
├── requirements.txt
└── README.md                             (Ce fichier)
Pistes d'Évolution Futures
Implémentation de la "TEAM 2: EXECUTION" avec un ExecutionSupervisor et des agents d'exécution.
Logique de replanification plus sophistiquée dans _handle_task_failure du PlanningSupervisorLogic.
Interface utilisateur plus riche avec des mises à jour en temps réel (par exemple, via WebSockets) pour refléter l'avancement sans rafraîchissement manuel.
Gestion plus fine des erreurs et des mécanismes de reessai (retry) à tous les niveaux.
Sécurisation des API du GRA et des agents (authentification, autorisation).
Amélioration de la robustesse de la découverte de services et de la gestion des pannes d'agents.
Déploiement sur une plateforme Cloud (ex: Google Cloud Run pour les services, Cloud Functions pour des tâches asynchrones légères), en utilisant les variables d'environnement pour la configuration.
Tests unitaires et d'intégration plus exhaustifs.
