# OrchestrAI Hackathon ADK - Système de Planification Multi-Agents

Ce projet est une implémentation d'un système multi-agents pour la génération, l'évaluation, la validation et la révision itérative de plans à partir d'un objectif initial. Il utilise un Agent Development Kit (ADK) basé sur le protocole A2A, avec une persistance des données via Firestore et une découverte de services gérée par un Gestionnaire de Ressources et d'Agents (GRA). Les agents intègrent des modèles de langage (LLM via Gemini) pour leur logique métier.

## Table des Matières (Optionnel, mais utile pour les longs README)

* [Architecture Fonctionnelle](#architecture-fonctionnelle)
* [Architecture Technique](#architecture-technique)
* [Concepts Clés Mis en Œuvre](#concepts-clés-mis-en-œuvre)
* [Prérequis](#prérequis)
* [Installation](#installation)
* [Utilisation](#utilisation)
* [Structure du Projet](#structure-du-projet)
* [Pistes d'Évolution Futures](#pistes-dévolution-futures)

## Architecture Fonctionnelle

Cette section décrit les grandes capacités du système et comment les différents composants interagissent pour atteindre l'objectif global de planification.

* **Soumission d'Objectif** : L'utilisateur initie le processus en soumettant un objectif brut (via l'interface Streamlit ou un script).
* **Génération et Itération de Plan (TEAM 1 : PLAN GENERATION)** :
    * **Orchestration Centralisée** : Le `PlanningSupervisorLogic` pilote le flux.
    * **Reformulation** : L'`ReformulatorAgent` prend l'objectif (ou un plan à réviser avec feedback) et génère un plan d'action détaillé en utilisant un LLM.
    * **Évaluation** : L'`EvaluatorAgent` analyse le plan reformulé, identifie forces/faiblesses, et donne un score de faisabilité (via LLM), retournant un JSON structuré.
    * **Validation** : Le `ValidatorAgent` prend le plan et son évaluation, et (via LLM) approuve ou rejette le plan avec une justification.
    * **Boucle de Révision** : En cas de rejet par le validateur, le `PlanningSupervisorLogic` intègre les commentaires de rejet dans un nouvel objectif et relance une reformulation (jusqu'à `max_revisions`).
* **Découverte de Services** : Les agents s'enregistrent auprès du GRA. Le superviseur interroge le GRA pour localiser les agents nécessaires en fonction de leurs compétences.
* **Persistance des Données** : L'état complet des plans (graphe de tâches, artefacts, historique) est stocké dans Firestore pour la résilience et le suivi. Les informations d'enregistrement des agents sont également persistées dans Firestore par le GRA.
* **Interface Utilisateur et Monitoring de Base** :
    * Une application Streamlit permet de soumettre des objectifs, de lister les plans, de visualiser les graphes de tâches, de consulter les artefacts et de voir les agents enregistrés.

## Architecture Technique

Cette section détaille les technologies, les protocoles et les composants techniques.

* **Langage et Frameworks Backend** :
    * Python 3.11+
    * **Agents et GRA** : Serveurs ASGI basés sur Uvicorn.
        * Les agents utilisent le SDK A2A (`A2AStarletteApplication`).
        * Le GRA utilise FastAPI pour ses endpoints API.
    * **Logique Métier des Agents** : Intégration de modèles de langage via l'API Gemini (gérée par `src/shared/llm_client.py`).
* **Base de Données** :
    * **Google Cloud Firestore** : Utilisé en mode NoSQL (orienté document) pour :
        * Persistance des `TaskGraph` de chaque plan (collection `task_graphs`).
        * Registre des agents (collection `agents_registry` gérée par le GRA).
        * Publication de l'URL du GRA (document `service_registry/gra_instance_config`).
* **Communication Inter-Services** :
    * **Protocole A2A** : Pour la communication entre le `PlanningSupervisorLogic` et les agents spécialisés (`Reformulator`, `Evaluator`, `Validator`), gérée par `src/clients/a2a_api_client.py`.
    * **API REST (HTTP/JSON)** : Pour la communication entre :
        * Les agents et le GRA (pour l'enregistrement).
        * Le superviseur et le GRA (pour la découverte d'agents).
        * Le front-end Streamlit et le GRA (pour la soumission de plans et la récupération de données).
    * La bibliothèque `httpx` est utilisée pour les appels HTTP asynchrones.
* **Front-End** :
    * **Streamlit** : Pour l'interface utilisateur de démonstration et de suivi.
    * **Graphviz** : Pour la génération et l'affichage des graphes de tâches.
* **Gestion des Tâches Asynchrones** :
    * `asyncio` est utilisé extensivement pour la nature asynchrone des appels réseau et des opérations LLM.
    * Le GRA lance le traitement des plans en tâche de fond (`asyncio.create_task()`) pour ne pas bloquer les requêtes HTTP du front-end.

## Concepts Clés Mis en Œuvre

* **Architecture Microservices/Agents** : Chaque agent et le GRA sont des services indépendants, favorisant la modularité et la scalabilité.
* **Orchestration de Tâches** : Le `PlanningSupervisorLogic` agit comme un orchestrateur, gérant un graphe de dépendances de tâches (`TaskGraph`).
* **Service Discovery** : Le GRA et le mécanisme de publication/découverte via Firestore permettent aux services de se trouver dynamiquement.
* **Persistance des Données** : L'utilisation de Firestore assure que l'état des plans et les informations critiques ne sont pas perdus.
* **Traitement Itératif et Réflexif** : La boucle de révision permet au système d'apprendre des rejets et de tenter d'améliorer les plans.
* **Intelligence Artificielle (LLM)** : Les agents exploitent la puissance des LLM (Gemini) pour des tâches complexes de génération de texte, d'analyse et de prise de décision.
* **Communication Asynchrone** : L'ensemble du système est conçu pour fonctionner de manière asynchrone.
## Architecture Générale

Le système est composé des principaux éléments suivants :

1.  **Agents Spécialisés** :
    * **ReformulatorAgent** : Prend un objectif brut et le transforme en un plan détaillé et structuré.
    * **EvaluatorAgent** : Analyse un plan reformulé, identifie ses forces, faiblesses, risques et lui attribue un score de faisabilité. Retourne son analyse au format JSON.
    * **ValidatorAgent** : Prend l'évaluation et le plan, et décide si le plan est approuvé ou rejeté, en fournissant une justification.
    Chaque agent est un serveur A2A autonome (basé sur Starlette/Uvicorn).

2.  **Gestionnaire de Ressources et d'Agents (GRA)** :
    * Un service central (basé sur FastAPI/Uvicorn) qui utilise Firestore pour la persistance.
    * **Registre d'Agents** : Permet aux agents de s'enregistrer au démarrage (nom, URL, compétences) et au superviseur de les découvrir.
    * **Publication de sa propre URL** : Le GRA publie sa propre URL dans un document Firestore connu pour que les autres services puissent le trouver dynamiquement.
    * **(Optionnel) Magasin d'Artefacts** : Pourrait être étendu pour stocker de manière centralisée les artefacts volumineux (actuellement, les artefacts sont stockés dans les `TaskNode` sur Firestore).
    * Expose des endpoints API pour la gestion des plans par le front-end.

3.  **PlanningSupervisorLogic (Orchestrateur)** :
    * Le cerveau du système de génération de plan.
    * Gère un **TaskGraph** persistant sur Firestore pour suivre l'état et les dépendances des tâches.
    * Interroge le GRA pour trouver les agents nécessaires.
    * Orchestre la séquence : Reformulator -> Evaluator -> Validator.
    * Implémente une **boucle de révision** : si un plan est rejeté, il génère un nouvel objectif incluant le feedback et relance une reformulation (jusqu'à `max_revisions`).

4.  **Client LLM Partagé** :
    * Un module (`src/shared/llm_client.py`) pour interagir avec l'API Gemini, utilisé par la logique des agents.

5.  **Front-End Streamlit (`app_frontend.py`)** :
    * Une interface utilisateur pour soumettre de nouveaux objectifs, visualiser la liste des plans, afficher les graphes de tâches (avec `graphviz`), et consulter les artefacts.
    * Affiche également le statut des agents enregistrés auprès du GRA.
    * Interagit avec le backend via des endpoints API exposés par le GRA.

## Prérequis

* Python 3.11+
* Compte Google Cloud avec un projet configuré et Firestore activé.
* Fichier de clé de compte de service JSON pour l'accès à Firestore.
* Variables d'environnement configurées :
    * `GOOGLE_APPLICATION_CREDENTIALS` : Chemin vers votre fichier de clé de service.
    * `GEMINI_API_KEY` : Votre clé API pour Google Gemini.
    * `(Optionnel) GRA_PUBLIC_URL` : Si l'URL publique du GRA doit être différente de `http://localhost:8000`.
    * `(Optionnel) AGENT_XXX_PUBLIC_URL` : Si les URLs publiques des agents doivent être surchargées.
* Les bibliothèques Python listées dans `requirements.txt` (à créer).

## Installation

1.  **Clonez le dépôt :**
    ```bash
    git clone <URL_DU_DEPOT>
    cd orchestrai-hackathon-ADK
    ```

2.  **Créez un environnement virtuel et activez-le :**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Sur Linux/macOS
    # venv\Scripts\activate    # Sur Windows
    ```

3.  **Installez les dépendances :**
    Créez un fichier `requirements.txt` avec le contenu suivant (adaptez les versions si besoin) :
    ```txt
    # requirements.txt
    firebase-admin
    google-generativeai
    httpx
    uvicorn[standard]
    fastapi
    a2a-sdk # Assurez-vous d'avoir la bonne manière d'installer votre SDK A2A
    streamlit
    graphviz
    pydantic
    ```
    Puis installez :
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurez les variables d'environnement** (voir section Prérequis).

5.  **(Si `graphviz` n'est pas déjà installé sur votre système) :**
    * Sur Debian/Ubuntu : `sudo apt-get install graphviz`
    * Sur macOS (avec Homebrew) : `brew install graphviz`

## Utilisation

Pour lancer le système complet :

1.  **Démarrez le Gestionnaire de Ressources et d'Agents (GRA) :**
    Ouvrez un terminal et exécutez :
    ```bash
    python -m src.services.gra.server
    ```
    Vérifiez les logs pour la confirmation de la connexion à Firestore et la publication de son URL.

2.  **Démarrez les Agents (chacun dans un nouveau terminal) :**
    * Agent Reformulateur :
        ```bash
        python -m src.agents.reformulator.server
        ```
    * Agent Évaluateur :
        ```bash
        python -m src.agents.evaluator.server
        ```
    * Agent Validateur :
        ```bash
        python -m src.agents.validator.server
        ```
    Vérifiez les logs de chaque agent pour confirmer leur enregistrement auprès du GRA. Le GRA devrait aussi logger ces enregistrements.

3.  **Lancez l'Application Streamlit (Front-End) :**
    Ouvrez un nouveau terminal et exécutez :
    ```bash
    streamlit run app_frontend.py
    ```
    Ouvrez l'URL fournie par Streamlit (généralement `http://localhost:8501`) dans votre navigateur.

4.  **Utilisez l'Interface :**
    * Soumettez un nouvel objectif via le formulaire dans la barre latérale.
    * Suivez l'évolution des plans dans la liste.
    * Cliquez sur un plan pour voir son graphe de tâches et ses artefacts.
    * Consultez le statut des agents.

5.  **Pour lancer un plan directement via le script (sans l'interface Streamlit) :**
    Assurez-vous que le GRA et les 3 agents sont en cours d'exécution, puis :
    ```bash
    python run_orchestrator.py
    ```

## Structure du Projet (Principaux Dossiers et Fichiers)

orchestrai-hackathon-ADK/
├── src/
│   ├── agents/
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
│   │   └── planning_supervisor_logic.py
│   ├── services/
│   │   └── gra/
│   │       └── server.py  (Gestionnaire de Ressources et d'Agents)
│   └── shared/
│       ├── base_agent_executor.py
│       ├── base_agent_logic.py
│       ├── llm_client.py
│       ├── service_discovery.py
│       ├── task_graph_management.py
│       └── skill_types.py (si vous l'avez créé)
├── app_frontend.py         (Interface Streamlit)
├── run_orchestrator.py     (Script pour lancer un plan en backend)
├── .gitignore
├── requirements.txt        (À créer)
└── README.md               (Ce fichier)


## Pistes d'Évolution Futures

* Implémentation de la **"TEAM 2: EXECUTION"** avec un `ExecutionSupervisor` et des agents d'exécution.
* Logique de replanification plus sophistiquée dans `_handle_task_failure`.
* Interface utilisateur plus riche avec des mises à jour en temps réel (WebSockets).
* Gestion plus fine des erreurs et des reessais.
* Sécurisation des API du GRA et des agents.
* Déploiement sur une plateforme Cloud.
