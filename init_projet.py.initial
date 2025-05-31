import os

project_structure = {
    ".git": None,
    "agents": [
        "__init__.py",
        "planificateur.py",
        "reformulateur.py",
        "evaluateur.py",
        "validateur_plan.py",
        "execution_supervisor.py",
        "execution_planner.py",
        "performer.py",
        "tester.py",
        "validateur_execution.py",
        "base_agent.py"
    ],
    "core": [
        "__init__.py",
        "message_types.py",
        "schemas.py"
    ],
    "scenarios": [
        "__init__.py",
        "scenario_simple.py"
    ],
    "tests": {
        "__init__.py": None,
        "test_agents": [
            "__init__.py"
            # Ajoutez d'autres fichiers de test ici si nécessaire
        ]
    },
    "": [
        "main.py",
        "requirements.txt",
        "README.md"
    ]
}

def create_structure(base_path, structure):
    for name, content in (structure.items() if isinstance(structure, dict) else enumerate(structure)):
        path = os.path.join(base_path, name) if not isinstance(name, int) else os.path.join(base_path, content)
        if isinstance(content, dict) or isinstance(content, list):
            os.makedirs(path, exist_ok=True)
            create_structure(path, content)
        elif isinstance(content, str) and content.endswith(".py"):
            os.makedirs(base_path, exist_ok=True)
            with open(os.path.join(base_path, content), "w") as f:
                f.write("# " + content)
        elif content is None:
            os.makedirs(path, exist_ok=True)

if __name__ == "__main__":
    create_structure(".", project_structure)
    print("✅ Structure de projet créée.")

