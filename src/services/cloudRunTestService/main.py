import os
import httpx
import logging
import socket
import subprocess
import asyncio
from flask import Flask, jsonify, request
from google.auth import default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.auth.exceptions import RefreshError
from google.oauth2.id_token import fetch_id_token
from fastapi import FastAPI, Query
from google.auth.transport.requests import Request
from google.oauth2 import id_token

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- URLs pour les tests par FQDN (via variables d'environnement) ---
# Ces variables doivent être passées lors du déploiement de Cloud Run
# Exemple: DEV_AGENT_URL="http://development-agent.default.svc.cluster.local:80"
DEV_AGENT_URL = os.environ.get("DEV_AGENT_URL")
ENV_MANAGER_URL = os.environ.get("ENV_MANAGER_URL")

# --- URLs pour les tests par IP directe (nouvelles IPs de LoadBalancer Interne) ---
# Ces IPs ont été obtenues après le provisionnement des LoadBalancers Internes
# de development-agent et environment-manager (10.132.0.6 et 10.132.0.5)
DEV_AGENT_URL_DIRECT_IP = "http://10.132.0.6:80"
ENV_MANAGER_URL_DIRECT_IP = "http://10.132.0.5:80"

# --- IP de votre service kube-dns (devra être mise à jour après Cloud DNS pour GKE) ---
# Une fois que kube-dns aura un LoadBalancer Interne, mettez à jour cette IP
# Pour l'instant, elle sera utilisée pour le test direct, mais n'est pas la cible finale.
KUBE_DNS_IP = "34.118.224.10" # <--- METTRE À JOUR APRÈS LB INTERNE DE KUBE-DNS SI VOUS LE FAITES

@app.route('/')
def index():
    return "Service de test Cloud Run pour la connectivité GKE. Utilisez /run-tests, /test-dns-lookup, /test-dig, /test-ping, /test-results, /run-direct-ip-tests."
from fastapi import FastAPI
import httpx
import asyncio
import os
import uuid
import datetime
from google.auth.transport.requests import Request
from google.oauth2 import id_token

app = FastAPI()

ENV_MGR_URL = os.getenv("ENV_MGR_URL", "http://10.132.0.5")
DEV_AGENT_URL = os.getenv("DEV_AGENT_URL", "http://10.132.0.6")

async def get_id_token(audience: str) -> str:
    return id_token.fetch_id_token(Request(), audience)
@app.get("/test-dev-agent-end2end")
async def test_dev_agent_e2e(
    env_mgr_url: str = Query(default="http://environment-manager.default.svc.cluster.local"),
    dev_agent_url: str = Query(default="http://development-agent.default.svc.cluster.local")
):
    environment_id = f"exec-test-{int(datetime.datetime.now().timestamp())}"
    base_image = "gcr.io/orchestrai-hackathon/python-devtools:1751122256"
    headers_env = {
        "Authorization": f"Bearer {await get_id_token(env_mgr_url)}",
        "Content-Type": "application/json"
    }
    headers_dev = {
        "Authorization": f"Bearer {await get_id_token(dev_agent_url)}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. Create environment
        resp_create = await client.post(f"{env_mgr_url}/create_environment", json={
            "environment_id": environment_id,
            "base_image": base_image
        }, headers=headers_env)

        if resp_create.status_code != 200:
            return {"error": "Failed to create environment", "detail": resp_create.text}

        # 2. Send message to Dev Agent
        message_payload = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "contextId": f"gplan-{uuid.uuid4().hex[:12]}",
                    "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                    "role": "user",
                    "parts": [
                        {
                            "text": "{\n  \"action\": \"generate_code_and_write_file\",\n  \"file_path\": \"/app/sum_util.py\",\n  \"objective\": \"Create a Python function named 'sum_numbers' that takes two arguments and returns their sum.\",\n  \"local_instructions\": [\"Ensure it handles both integers and floats.\", \"Add docstrings and type hints.\"],\n  \"acceptance_criteria\": [\"sum_numbers(2, 3) should return 5\", \"sum_numbers(2.5, 3.5) should return 6.0\"],\n  \"environment_id\": \"%s\"\n}" % environment_id
                        }
                    ]
                },
                "skillId": "coding_python"
            },
            "id": "1"
        }

        resp_dev = await client.post(f"{dev_agent_url}/", json=message_payload, headers=headers_dev)

        # Optional: wait a few seconds
        await asyncio.sleep(4)

        # 3. Read file back
        read_resp = await client.post(f"{env_mgr_url}/download_from_environment", json={
            "environment_id": environment_id,
            "path": "/app/sum_util.py"
        }, headers=headers_env)

        # 4. Execute it
        exec_resp = await client.post(f"{env_mgr_url}/exec_in_environment", json={
            "environment_id": environment_id,
            "command": "python -c 'from sum_util import sum_numbers; print(sum_numbers(2, 3))'"
        }, headers=headers_env)

        # 5. Cleanup
        await client.post(f"{env_mgr_url}/delete_environment", json={
            "environment_id": environment_id
        }, headers=headers_env)

    return {
        "environment_id": environment_id,
        "create_env": resp_create.json(),
        "dev_agent_response": resp_dev.json(),
        "read_file": read_resp.json(),
        "exec_result": exec_resp.json(),
        "cleanup": "done"
    }

async def _get_id_token_for_audience(audience_url: str) -> str | None:
    try:
        credentials, project = default()
        auth_req = GoogleAuthRequest()

        id_token = fetch_id_token(auth_req, audience_url) 

        if id_token:
            logger.info(f"Jeton d'identité obtenu avec succès pour l'audience: {audience_url}")
            return id_token
        else:
            logger.warning(f"Impossible d'obtenir un jeton d'identité pour l'audience: {audience_url}")
            return None
    except RefreshError as e:
        logger.error(f"Erreur de rafraîchissement lors de l'obtention du jeton pour {audience_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'obtention du jeton pour {audience_url}: {e}")
        return None

# Fonction pour exécuter les tests de connectivité GKE via IP directe
async def _run_gke_connectivity_tests_direct_ip():
    global _last_test_results
    current_results = {}

    headers = {"Content-Type": "application/json"}

    # Test Development Agent (via IP directe)
    if DEV_AGENT_URL_DIRECT_IP:
        logger.info(f"Début du test pour l'Agent de Développement (IP directe: {DEV_AGENT_URL_DIRECT_IP})")
        dev_agent_id_token = await _get_id_token_for_audience(DEV_AGENT_URL_DIRECT_IP)
        if dev_agent_id_token:
            headers["Authorization"] = f"Bearer {dev_agent_id_token}"
        else:
            current_results['dev_agent_health_direct_ip'] = {'error': 'Impossible d\'obtenir le jeton d\'identité pour l\'Agent de Développement (IP directe).'}
            logger.error("Impossible d'obtenir le jeton d'identité pour l'Agent de Développement (IP directe). Tentative sans jeton.")
            headers = {"Content-Type": "application/json"}

        if "error" not in current_results.get('dev_agent_health_direct_ip', {}): 
            try:
                logger.info(f"Test de connexion à l'Agent de Développement (IP directe): {DEV_AGENT_URL_DIRECT_IP}/health")
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{DEV_AGENT_URL_DIRECT_IP}/health", headers=headers, timeout=10)
                    response.raise_for_status()
                    current_results['dev_agent_health_direct_ip'] = {'status': response.status_code, 'response': response.json()}
                    logger.info(f"Agent de Développement (IP directe): {response.status_code} - {response.json()}")
            except httpx.HTTPStatusError as e:
                current_results['dev_agent_health_direct_ip'] = {'error': f"HTTP Error: {e.response.status_code} - {e.response.text}"}
                logger.error(f"Agent de Développement (HTTP Error, IP directe): {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                current_results['dev_agent_health_direct_ip'] = {'error': f"Request Error: {str(e)}"}
                logger.error(f"Agent de Développement (Request Error, IP directe): {e}")
            except Exception as e:
                current_results['dev_agent_health_direct_ip'] = {'error': f"Unexpected Error: {str(e)}"}
                logger.error(f"Agent de Développement (Unexpected Error, IP directe): {e}")
    else:
        current_results['dev_agent_health_direct_ip'] = {'status': 'Skipped', 'message': 'DEV_AGENT_URL_DIRECT_IP non défini.'}

    headers = {"Content-Type": "application/json"} # Réinitialise les headers pour le prochain service

    # Test Environment Manager (via IP directe)
    if ENV_MANAGER_URL_DIRECT_IP:
        logger.info(f"Début du test pour l'Environment Manager (IP directe: {ENV_MANAGER_URL_DIRECT_IP})")
        env_manager_id_token = await _get_id_token_for_audience(ENV_MANAGER_URL_DIRECT_IP)
        if env_manager_id_token:
            headers["Authorization"] = f"Bearer {env_manager_id_token}"
        else:
            current_results['env_manager_health_direct_ip'] = {'error': 'Impossible d\'obtenir le jeton d\'identité pour l\'Environment Manager (IP directe).'}
            logger.error("Impossible d'obtenir le jeton d'identité pour l'Environment Manager (IP directe). Tentative sans jeton.")
            headers = {"Content-Type": "application/json"}

        if "error" not in current_results.get('env_manager_health_direct_ip', {}): 
            try:
                logger.info(f"Test de connexion à l'Environment Manager (IP directe): {ENV_MANAGER_URL_DIRECT_IP}/health")
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{ENV_MANAGER_URL_DIRECT_IP}/health", headers=headers, timeout=10)
                    response.raise_for_status()
                    current_results['env_manager_health_direct_ip'] = {'status': response.status_code, 'response': response.json()}
                    logger.info(f"Environment Manager (IP directe): {response.status_code} - {response.json()}")
            except httpx.HTTPStatusError as e:
                current_results['env_manager_health_direct_ip'] = {'error': f"HTTP Error: {e.response.status_code} - {e.response.text}"}
                logger.error(f"Environment Manager (HTTP Error, IP directe): {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                current_results['env_manager_health_direct_ip'] = {'error': f"Request Error: {str(e)}"}
                logger.error(f"Environment Manager (Request Error, IP directe): {e}")
            except Exception as e:
                current_results['env_manager_health_direct_ip'] = {'error': f"Unexpected Error: {str(e)}"}
                logger.error(f"Environment Manager (Unexpected Error, IP directe): {e}")
    else:
        current_results['env_manager_health_direct_ip'] = {'status': 'Skipped', 'message': 'ENV_MANAGER_URL_DIRECT_IP non défini.'}

    _last_test_results = current_results # Stocke les résultats
    return _last_test_results

# Fonction pour exécuter tous les tests de connectivité GKE via FQDN
# (utilise les variables DEV_AGENT_URL et ENV_MANAGER_URL lues depuis l'environnement)
async def _run_all_gke_connectivity_tests():
    global _last_test_results
    current_results = {}
    
    headers = {"Content-Type": "application/json"}

    # Test Development Agent
    if DEV_AGENT_URL:
        logger.info(f"Début du test pour l'Agent de Développement ({DEV_AGENT_URL})")
        dev_agent_id_token = await _get_id_token_for_audience(DEV_AGENT_URL)
        if dev_agent_id_token:
            headers["Authorization"] = f"Bearer {dev_agent_id_token}"
        else:
            current_results['dev_agent_health'] = {'error': 'Impossible d\'obtenir le jeton d\'identité pour l\'Agent de Développement.'}
            logger.error("Impossible d'obtenir le jeton d'identité pour l'Agent de Développement. Tentative sans jeton.")
            headers = {"Content-Type": "application/json"}
            
        if "error" not in current_results.get('dev_agent_health', {}): # Procède si pas d'erreur sur le token
            try:
                logger.info(f"Test de connexion à l'Agent de Développement: {DEV_AGENT_URL}/health")
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{DEV_AGENT_URL}/health", headers=headers, timeout=10)
                    response.raise_for_status()
                    current_results['dev_agent_health'] = {'status': response.status_code, 'response': response.json()}
                    logger.info(f"Agent de Développement: {response.status_code} - {response.json()}")
            except httpx.HTTPStatusError as e:
                current_results['dev_agent_health'] = {'error': f"HTTP Error: {e.response.status_code} - {e.response.text}"}
                logger.error(f"Agent de Développement (HTTP Error): {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                current_results['dev_agent_health'] = {'error': f"Request Error: {str(e)}"}
                logger.error(f"Agent de Développement (Request Error): {e}")
            except Exception as e:
                current_results['dev_agent_health'] = {'error': f"Unexpected Error: {str(e)}"}
                logger.error(f"Agent de Développement (Unexpected Error): {e}")
    else:
        current_results['dev_agent_health'] = {'status': 'Skipped', 'message': 'DEV_AGENT_URL non défini.'}

    headers = {"Content-Type": "application/json"} # Réinitialise les headers pour le prochain service
    
    # Test Environment Manager
    if ENV_MANAGER_URL:
        logger.info(f"Début du test pour l'Environment Manager ({ENV_MANAGER_URL})")
        env_manager_id_token = await _get_id_token_for_audience(ENV_MANAGER_URL)
        if env_manager_id_token:
            headers["Authorization"] = f"Bearer {env_manager_id_token}"
        else:
            current_results['env_manager_health'] = {'error': 'Impossible d\'obtenir le jeton d\'identité pour l\'Environment Manager.'}
            logger.error("Impossible d'obtenir le jeton d'identité pour l'Environment Manager. Tentative sans jeton.")
            headers = {"Content-Type": "application/json"}
            
        if "error" not in current_results.get('env_manager_health', {}): # Procède si pas d'erreur sur le token
            try:
                logger.info(f"Test de connexion à l'Environment Manager: {ENV_MANAGER_URL}/health")
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{ENV_MANAGER_URL}/health", headers=headers, timeout=10)
                    response.raise_for_status()
                    current_results['env_manager_health'] = {'status': response.status_code, 'response': response.json()}
                    logger.info(f"Environment Manager: {response.status_code} - {response.json()}")
            except httpx.HTTPStatusError as e:
                current_results['env_manager_health'] = {'error': f"HTTP Error: {e.response.status_code} - {e.response.text}"}
                logger.error(f"Environment Manager (HTTP Error): {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                current_results['env_manager_health'] = {'error': f"Request Error: {str(e)}"}
                logger.error(f"Environment Manager (Request Error): {e}")
            except Exception as e:
                current_results['env_manager_health'] = {'error': f"Unexpected Error: {str(e)}"}
                logger.error(f"Environment Manager (Unexpected Error): {e}")
    else:
        current_results['env_manager_health'] = {'status': 'Skipped', 'message': 'ENV_MANAGER_URL non défini.'}

    _last_test_results = current_results # Stocke les résultats
    return _last_test_results

# Endpoint pour déclencher les tests via FQDN
@app.route('/run-tests', methods=['GET'])
async def run_tests_endpoint():
    logger.info("Déclenchement des tests de connectivité GKE...")
    results = await _run_all_gke_connectivity_tests()
    return jsonify({"message": "Tests de connectivité exécutés.", "results": results})

# Endpoint pour déclencher les tests via IP directe
@app.route('/run-direct-ip-tests', methods=['GET'])
async def run_direct_ip_tests_endpoint():
    logger.info("Déclenchement des tests de connectivité GKE via IP directe...")
    results = await _run_gke_connectivity_tests_direct_ip()
    return jsonify({"message": "Tests de connectivité via IP directe exécutés.", "results": results})


# Endpoint pour récupérer les derniers résultats des tests
@app.route('/test-results', methods=['GET'])
def get_test_results_endpoint():
    global _last_test_results
    if not _last_test_results:
        return jsonify({"message": "Aucun résultat de test disponible. Exécutez /run-tests d'abord."}), 404
    return jsonify(_last_test_results)


# --- Nouveaux Endpoints pour un Débogage plus Profond ---

@app.route('/test-dns-lookup', methods=['GET'])
async def test_dns_lookup():
    hostname = request.args.get('hostname')
    if not hostname:
        return jsonify({'error': 'Paramètre "hostname" manquant.'}), 400
    
    try:
        # Utilisation de socket.gethostbyname_ex qui fournit plus de détails
        host_info = socket.gethostbyname_ex(hostname)
        hostname_resolved = host_info[0]
        aliaslist = host_info[1]
        ip_addresses = host_info[2]
        
        logger.info(f"Résolution DNS pour {hostname}: {ip_addresses}")
        return jsonify({
            'hostname_query': hostname,
            'hostname_resolved': hostname_resolved,
            'aliases': aliaslist,
            'ip_addresses': ip_addresses
        }), 200
    except socket.gaierror as e:
        logger.error(f"Erreur de résolution DNS pour {hostname}: {e} (Errno: {e.errno})")
        return jsonify({'error': f"Échec de la résolution DNS pour {hostname}: {e} (Errno: {e.errno})"}), 500
    except Exception as e:
        logger.error(f"Erreur inattendue lors de la résolution DNS pour {hostname}: {e}")
        return jsonify({'error': f"Erreur inattendue: {e}"}), 500
import requests
@app.route('/test-internal-call')
def test_internal_call():
    try:
        url = os.environ.get("DEV_AGENT_URL", "http://development-agent.default.svc.cluster.local:80")
        response = requests.get(url, timeout=3)
        return jsonify({
            "url": url,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text[:500]  # On limite à 500 chars
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/test-dig', methods=['GET'])
async def test_dig():
    hostname = request.args.get('hostname')
    if not hostname:
        return jsonify({'error': 'Paramètre "hostname" manquant.'}), 400
    
    try:
        # Exécuter dig avec l'option +short pour un résultat concis, ou sans pour un résultat complet
        dig_command = f"dig {hostname}"
        if request.args.get('short') == 'true':
            dig_command += " +short"

        process = await asyncio.create_subprocess_shell(
            dig_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Commande dig échouée pour {hostname}: {stderr.decode()}")
            return jsonify({'error': f"Commande dig échouée: {stderr.decode()}"}), 500
        
        logger.info(f"Résultat dig pour {hostname}:\n{stdout.decode()}")
        return jsonify({'hostname': hostname, 'dig_output': stdout.decode()}), 200
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de dig pour {hostname}: {e}")
        return jsonify({'error': f"Erreur inattendue lors de l'exécution de dig: {e}"}), 500

# NOUVEAU ENDPOINT POUR TESTER DIRECTEMENT KUBE-DNS
@app.route('/test-dig-direct', methods=['GET'])
async def test_dig_direct():
    hostname = request.args.get('hostname')
    if not hostname:
        return jsonify({'error': 'Paramètre "hostname" manquant.'}), 400
    
    try:
        # Exécuter dig en spécifiant explicitement le serveur kube-dns
        dig_command = f"dig @{KUBE_DNS_IP} {hostname}"
        if request.args.get('short') == 'true':
            dig_command += " +short"

        process = await asyncio.create_subprocess_shell(
            dig_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Commande dig directe échouée pour {hostname} via {KUBE_DNS_IP}: {stderr.decode()}")
            return jsonify({'error': f"Commande dig directe échouée: {stderr.decode()}"}), 500
        
        logger.info(f"Résultat dig directe pour {hostname} via {KUBE_DNS_IP}:\n{stdout.decode()}")
        return jsonify({'hostname': hostname, 'dig_output': stdout.decode(), 'dns_server': KUBE_DNS_IP}), 200
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de dig directe pour {hostname} via {KUBE_DNS_IP}: {e}")
        return jsonify({'error': f"Erreur inattendue lors de l'exécution de dig directe: {e}"}), 500


@app.route('/test-ping', methods=['GET'])
async def test_ping():
    target = request.args.get('target') # Peut être un nom d'hôte ou une IP
    count = request.args.get('count', '3') # Nombre de pings
    if not target:
        return jsonify({'error': 'Paramètre "target" manquant (hostname ou IP).'}), 400

    try:
        command = f"ping -c {count} {target}"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Commande ping échouée pour {target}: {stderr.decode()}")
            return jsonify({'error': f"Commande ping échouée: {stderr.decode()}"}), 500
        
        logger.info(f"Résultat ping pour {target}:\n{stdout.decode()}")
        return jsonify({'target': target, 'ping_output': stdout.decode()}), 200
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de ping pour {target}: {e}")
        return jsonify({'error': f"Erreur inattendue lors de l'exécution de ping: {e}"}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
