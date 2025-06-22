# OrchestrAI – From Idea to Action via LLM Agent Collaboration
*OrchestrAI – From Idea to Action with LLM-Driven Agent Collaboration*

---

[![Cloud Run Ready](https://img.shields.io/badge/cloud--run-ready-brightgreen)](https://cloud.google.com/run) [![Python](https://img.shields.io/badge/python-3.11-blue)](https://python.org/) [![Google ADK](https://img.shields.io/badge/ADK-Google%20Agent2Agent-blueviolet)](https://developers.google.com/agent-framework) [![Platform](https://img.shields.io/badge/platform-Google%20Cloud-lightgrey)](https://cloud.google.com/)

---

## ✨ Pitch

OrchestrAI turns any vague user goal into a detailed action plan and concrete deliverables thanks to a dynamically orchestrated team of specialized AI agents. Clarification, planning and execution are fully automated, supervised, recoverable and logged while keeping the user in the loop for relevance and quality.

---

## 🚀 Why OrchestrAI Stands Out

- **Human-in-the-loop automation**: The user remains involved at every key step.
- **Dynamic agent discovery**: Agents are registered and assigned in real time via the GRA registry.
- **Error resilience & incremental execution**: Plans and tasks can be retried, extended or patched without losing previous progress.
- **Composable & extensible**: Add new agents or skills anytime—just register with the GRA and they are orchestrated automatically.
- **A2A protocol & Google ADK compliant**: Ensures interoperability and future-proofing.
- **Full audit trail**: Every decision, correction and outcome is persisted in Firestore for transparency.
- **Isolated dev environments**: Generated code runs in Kubernetes pods managed by the `EnvironmentManager` for safety (see `docs/environment_manager.md`). Environment metadata lives in Firestore and, when no dedicated pod can be created, the manager reuses a shared `exec_default` environment (see `scripts/create_fallback_environment.py`).
- **Real-time agent status**: The GRA exposes `/gra_status` and `/ws/status` endpoints so the dashboard can display each agent's operational state (Idle, Busy, Working, etc.).
- **Agent logs**: Each agent exposes a `/logs` route and the GRA proxies it via `/v1/agents/<name>/logs` so the dashboard can fetch runtime logs securely. The GRA server itself exposes `/v1/gra/logs`.

---

## 🏗️ Table of Contents

1. [Functional Architecture](#functional-architecture)
2. [Technical Architecture](#technical-architecture)
3. [Key Concepts](#key-concepts)
4. [Installation & Prerequisites](#installation--prerequisites)
5. [Usage](#usage)
6. [Project Structure](#project-structure)
7. [Utility Scripts](#utility-scripts)
8. [Cloud / Firebase Deployment](#cloud--firebase-deployment)
9. [How to Add Your Agent](#how-to-add-your-agent)
10. [Roadmap & Perspectives](#roadmap--perspectives)

---

## 🧭 Functional Architecture

The functional architecture describes the flow from the user's idea all the way to execution by the agent teams.

**View the diagram on [mermaidchart.com](https://www.mermaidchart.com/app/projects/f16a002d-be5d-43d1-bdfb-c095ee3316f6/diagrams/b4c8f941-5b8a-469c-a670-a87c37b12923/version/v0.1/edit)**

```mermaid

subgraph "Infrastructure & Services"
  direction LR
  B_GRA[GRA - Service Discovery]
end

subgraph "Phase 1: Clarification"
  A[User] -->|Initial Goal| B(API Gateway)
  B --> C{Global Supervisor}
  C -.->|Finds Agent| B_GRA
  C --o|Clarification Request| D[User Interaction Agent]
  D --o|Display to User| E[Interface UI]
  E --o|Response| C
end

C -->|Clarified Goal| F{Planning Supervisor}
subgraph "Phase 2: Planning (TEAM 1)"
  F -.->|Finds Agents| B_GRA
  F -->|Generate Plan| G[Reformulator Agent]
  G -->|Evaluate Plan| H[Evaluator Agent]
  H -->|Validate Plan| I[Validator Agent]
  I -- "If Plan Rejected" --> F
end

I -- "Validated Plan" --> J{Execution Supervisor}
subgraph "Phase 3: Execution (TEAM 2)"
  J -.->|Finds Agents| B_GRA
  J -->|Split Plan| K[Decomposition Agent]
  K -->|Execution Task Graph| J
  J -- "Coordinate Tasks" --> L((Execution Agents Pool))
  subgraph L
    direction LR
    L1[Development Agent]
    L2[Research Agent]
    L3[Testing Agent]
  end
  L -- "Results & Artifacts" --> J
end

J -->|Final Results| M[Output]
```
## Technical Architecture

The technical architecture reflects the use of **Vertex AI** as the central platform for the Gemini models.

```mermaid
graph LR
    %% --- FRONTENDS ---
    subgraph "Frontends"
        User[(User)]
        ReactUI["React (Firebase Hosting)"]
        User --> ReactUI
    end

    %% --- BACKEND on Cloud Run ---
    subgraph "Cloud Run Services"
        GRA[fa:fa-server GRA / API Gateway]
        GlobalSupervisor[fa:fa-brain Global Supervisor]
        PlanningSupervisor[fa:fa-clipboard-list Planning Supervisor]
        ExecutionSupervisor[fa:fa-cogs Execution Supervisor]

        subgraph "Agents"
            UserInteractionAgent[fa:fa-comments User Interaction]
            DecompositionAgent[fa:fa-sitemap Decomposition]

            subgraph "TEAM 1 Agents"
                direction TB
                Reformulator
                Evaluator
                Validator
            end

            subgraph "TEAM 2 Execution Agents"
                direction TB
                DevelopmentAgent[fa:fa-code Development]
                ResearchAgent[fa:fa-search Research]
                TestingAgent[fa:fa-check-square Testing]
            end
        end
    end

    %% --- SHARED SERVICES ---
    subgraph "Shared Services"
        Firestore[(fa:fa-database Firestore)]
        VertexAI["fa:fa-brain Vertex AI\n(Gemini Models)"]
    end

    %% --- FLOW & INTERACTIONS ---
    ReactUI -- "REST API" --> GRA
    GRA -- "Forwards to" --> GlobalSupervisor
    GlobalSupervisor -- "Hands off to" --> PlanningSupervisor
    PlanningSupervisor -- "Triggers on Validated Plan" --> ExecutionSupervisor
    %% Agent Communications
    GlobalSupervisor <--> |"A2A"| UserInteractionAgent
    PlanningSupervisor <--> |"A2A"| Reformulator
    PlanningSupervisor <--> |"A2A"| Evaluator
    PlanningSupervisor <--> |"A2A"| Validator
    ExecutionSupervisor <--> |"A2A"| DecompositionAgent
    ExecutionSupervisor <--> |"A2A"| DevelopmentAgent
    ExecutionSupervisor <--> |"A2A"| ResearchAgent
    ExecutionSupervisor <--> |"A2A"| TestingAgent

    %% Database Connections
    GRA -- "R/W: Agent Registry" --> Firestore
    GlobalSupervisor -- "R/W: global_plans" --> Firestore
    PlanningSupervisor -- "R/W: task_graphs" --> Firestore
    ExecutionSupervisor -- "R/W: execution_task_graphs" --> Firestore

    %% LLM Connections
    UserInteractionAgent -- "API Call" --> VertexAI
    Reformulator -- "API Call" --> VertexAI
    Evaluator -- "API Call" --> VertexAI
    Validator -- "API Call" --> VertexAI
    DecompositionAgent -- "API Call" --> VertexAI
    DevelopmentAgent -- "API Call" --> VertexAI
    ResearchAgent -- "API Call" --> VertexAI
    TestingAgent -- "API Call" --> VertexAI
```

* **Backend Language & Frameworks**:
    * Python 3.11
    * Agents and the GRA run as ASGI servers (Uvicorn) using the A2A SDK (`A2AStarletteApplication`) and FastAPI for the GRA.
* **Agent Business Logic**: Gemini language models via **Google Cloud Vertex AI** (handled in `src/shared/llm_client.py`).
* **Database (Google Cloud Firestore)**:
    * `global_plans`, `task_graphs`, `execution_task_graphs`, `agents` (registry).
* **Inter-Service Communication**: A2A protocol (via `src/clients/a2a_api_client.py`).
* **Front End**: React served from Firebase Hosting.
* **Asynchronous Task Handling**: Extensive use of `asyncio`.
* **Environment Manager**: Creates and manages isolated Kubernetes pods to run the generated code. A dedicated API allows deleting a pod via `DELETE /api/environments/{env_id}`.

## ⚙️ Installation & Prerequisites

This guide covers everything you need to set up the environment and deploy OrchestrAI, both locally and on Google Cloud.

### Step 1: Local Environment Setup

1. **Clone the repository:**
```bash
git clone [URL_de_votre_dépôt]
cd orchestrai-hackathon-ADK
```

2. **Install Core Tools:** Make sure you have the following CLI tools installed on your machine:
* Python 3.11
* Google Cloud SDK (`gcloud`)
* Firebase CLI (`firebase`)
* Docker

3. **Create a Virtual Environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

4. **Install Python Dependencies:**
```bash
pip install -r requirements_py311.txt
```

### Step 2: Initial Google Cloud Project Setup

1. **Create or select a GCP Project:** Ensure the project is linked to a valid billing account.

2. **Set your Project with gcloud:**
```bash
gcloud config set project YOUR_PROJECT_ID
```

3. **Enable Required APIs:**
```bash
gcloud services enable \
    iam.googleapis.com \
    cloudrun.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    aiplatform.googleapis.com \
    firestore.googleapis.com \
    firebase.googleapis.com \
    container.googleapis.com \
    vpcaccess.googleapis.com
```

### Step 3: Provisioning Core Infrastructure & Permissions

1. **Create VPC Connector & GKE Cluster:**
```bash
./create_vpc_connector.sh
./create_gke_cluster.sh
```

2. **Set Up IAM Permissions:**
```bash
./scripts/grant_agent_permissions.sh
./scripts/grant_gke_permissions_to_cloudrun_sa.sh
./scripts/grant_gclou_kubernet.sh
```

### Step 4: Authentication

1. **For Cloud Deployment (Recommended):**
```bash
gcloud auth login
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

2. **For Local Development & Testing:**
* Create a Service Account in the GCP Console with appropriate roles (e.g., Editor).
* Generate and download a JSON key for this service account.
* Set the following environment variable in your shell:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```

You are now fully set up to use the deployment scripts described in the **Usage** and **Cloud Deployment** sections.

## Usage (Local Development)

The `deployment.sh` script can generate a `docker-compose.yml` file to launch all services locally.

1. **Generate the local configuration:**
    ```bash
    ./deployment.sh configure
    ```
2. **Start all services with Docker Compose:**
    ```bash
    cd docker_build
    docker-compose up --build
    ```
    This builds the images and starts the nine containers.

3. **Access the Front End:** the React front end is served by the `user_interaction_agent` service and is available on the port defined in `docker-compose.yml`.

## Cloud / Firebase Deployment

The `deployment.sh` script automates the entire deployment process.

**Deployment prerequisites:**
1. Install and configure the `gcloud` SDK.
2. Authenticate:
    ```bash
    gcloud auth login
    gcloud config set project YOUR_PROJECT_ID
    gcloud auth configure-docker europe-west1-docker.pkg.dev
    ```
3. Enable all required APIs on the project (see Prerequisites section).

**Deployment commands:**
```bash
# Configure, build, push and deploy everything in one go:
./deployment.sh all

# Deploy only the front end after a change:
./deployment.sh deploy_frontend

# Quickly deploy a single agent after modifying its code
# (make sure the agent image has been built and pushed first)
./deployment.sh deploy-one user_interaction_agent

# Rebuild, push and deploy just one agent in a single command
./deployment.sh all_single_agent user_interaction_agent
```
The script automatically injects the correct environment variables (`GCP_PROJECT_ID`, `GCP_REGION`, service URLs) into the deployed containers. API key authentication is no longer required.

## Project Structure
```Markdown
orchestrai-hackathon-ADK/
├── src/
│   ├── agents/
│   │   ├── ... (8 specialized agents)
│   ├── clients/
│   ├── orchestrators/
│   ├── services/
│   │   ├── gra/
│   │   └── environment_manager/
│   └── shared/
├── react_frontend/                   # Lightweight React interface
├── deployment.sh                     # Cloud Run deployment script
└── requirements_py311.txt            # Dependency list for Python 3.11
```

## Utility Scripts

Several helper scripts are provided for deployment and maintenance tasks.

### Shell Scripts

- `build_and_deploy.sh` – generate `requirements.txt`, build the Docker images and push them.
- `create_gke_cluster.sh` – create a GKE cluster and configure `kubectl`.
- `create_vpc_connector.sh` – create a VPC connector for Cloud Run.
- `deployment.sh` – build and deploy all agents and the GRA registry.
- `run_gra_docker.sh` – start the GRA container locally with credentials.
- `setup_ssh_key_github.sh` – configure an SSH key for GitHub and update the remote.
- `test_droit.sh` – grant persistent volume claim permissions on Kubernetes.
- `create_PODimage_and_deploy.sh` – build a `python-devtools` image for isolated environments and push it to GCR.
- `scripts/create_fallback_environment.py` – create the shared fallback pod used when environment creation fails.
- `scripts/deploy_test.sh` – deploy agents using an existing GKE cluster and connector.
- `scripts/grant_agent_permissions.sh` – allow inter-service Cloud Run invocations.
- `scripts/grant_gke_permissions_to_cloudrun_sa.sh` – give the Cloud Run service account access to GKE.
- `scripts/grant_gclou_kubernet.sh` – example script to set up GCP and Kubernetes roles.
- `tests/test_development_agent_curl.sh` – send a test request to the development agent.

### Python Scripts

- `scripts/cleanup_firestore_plans.py` – remove unfinished plans from Firestore.
- `src/run_orchestrator.py` – trigger a planning sequence from the command line.
- `src/tests/k8s_iam_test_server.py` – FastAPI server to test GKE IAM authentication.
- `react_frontend/secure_server.py` – run the React front end with HTTPS.
- `init_projet.py.initial` – example project scaffolding utility.

## Future Enhancements

* More advanced re-planning logic in `ExecutionSupervisorLogic`.
* Finer-grained error handling and retry mechanisms.
* API hardening beyond Cloud Run IAM authentication.
* Collect and display performance statistics per agent.
* Create and document specialized tools for agents (e.g., access to specific databases, etc.).

## Bugs & Improvements

* Integrate an external validation loop into **Team 2** so tasks can be realigned when needed.
* Stabilize communication between the agents and the resource manager.
* Add processing status indicators (e.g., *In Progress*, *IDLE*) to the agent monitoring dashboard.
* Stabilize the file manager component.

---

# OrchestrAI Hackathon Project

© 2025 Étienne Revol - Licensed under GPLv3

## About

This software is part of the OrchestrAI Hackathon project. It is distributed under the GNU General Public License v3 (GPLv3).
No part of this software may be reused in proprietary or security-critical systems without the explicit written consent of Étienne Revol.

## License

This project is licensed under the GNU General Public License v3. See the LICENSE file or https://www.gnu.org/licenses/gpl-3.0.html for details.

## Disclaimer

This software is provided "as is", without warranty of any kind. Use at your own risk.
