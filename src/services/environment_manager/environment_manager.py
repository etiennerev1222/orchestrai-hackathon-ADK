import logging
import time
import io
import tarfile
import os
import asyncio
from kubernetes import client, config, watch
from kubernetes.stream import stream
from google.oauth2 import credentials
from google.auth.transport.requests import Request
import google.auth
from typing import Optional, Dict, Any , List 
import json
from src.shared.firebase_init import db
import re
from google.oauth2 import service_account
import google.auth

GKE_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

logger = logging.getLogger(__name__)

K8S_ENVIRONMENTS_COLLECTION = "kubernetes_environments"

FALLBACK_ENV_ID = "exec_default"


class EnvironmentManager:
    def __init__(self):
        self.api_client = None
        gke_cluster_endpoint = os.environ.get("GKE_CLUSTER_ENDPOINT")
        configuration = client.Configuration()

        if gke_cluster_endpoint:
            logger.info(f"GKE_CLUSTER_ENDPOINT found: {gke_cluster_endpoint}. Configuring Kubernetes client for remote GKE cluster.")
            configuration.host = f"https://{gke_cluster_endpoint}"

            # SSL
            ssl_ca_cert = os.environ.get("GKE_SSL_CA_CERT")
            if ssl_ca_cert:
                configuration.ssl_ca_cert = ssl_ca_cert
                configuration.verify_ssl = True
                logger.info("SSL verification ENABLED with provided CA certificate.")
            else:
                configuration.verify_ssl = False
                logger.warning("SSL verification is DISABLED because GKE_SSL_CA_CERT is not set. ⚠️ Not recommended for production.")

            # Auth via ADC
            credentials, _ = google.auth.default(scopes=GKE_SCOPES)
            if credentials:
                try:
                    credentials.refresh(Request())
                    configuration.api_key = {"authorization": f"Bearer {credentials.token}"}
                    logger.info("Kubernetes client authentication configured with refreshed ADC token.")
                except Exception as e:
                    logger.error(f"Failed to refresh ADC token: {e}")
                    raise Exception(f"ADC token refresh failed: {e}")
            else:
                raise Exception("ADC credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS env var or use gcloud auth.")

        else:
            # Fallback local config
            try:
                config.load_kube_config()
                logger.info("Kubernetes config loaded from local kube_config.")
            except config.ConfigException as e:
                raise Exception(f"Kubernetes config load failed: {e}")

        client.Configuration.set_default(configuration)
        self.api_client = client.ApiClient(configuration)
        self.v1 = client.CoreV1Api(self.api_client)
        self.apps_v1 = client.AppsV1Api(self.api_client)
        self.namespace = os.environ.get("KUBERNETES_NAMESPACE", "default")
        self.environments = {}
        logger.info(f"EnvironmentManager initialized for Kubernetes namespace: {self.namespace}.")


    @staticmethod
    def normalize_environment_id(plan_id: str) -> str:
        """Return standardized environment ID for a given plan or environment identifier."""
        return f"exec-{EnvironmentManager.extract_global_plan_id(plan_id)}"

    @staticmethod
    def generate_k8s_names(environment_id: str) -> dict:
        safe_env_id = EnvironmentManager._make_safe_k8s_name_static(environment_id)
        return {
            "pod_name": f"dev-env-{safe_env_id}",
            "pvc_name": f"dev-env-pvc-{safe_env_id}",
            "volume_name": f"dev-env-vol-{safe_env_id}"
        }

    @staticmethod
    def _make_safe_k8s_name_static(base: str) -> str:
        safe = base.lower()
        safe = re.sub(r'[^a-z0-9.-]', '-', safe)
        safe = re.sub(r'^[^a-z0-9]+', '', safe)
        safe = re.sub(r'[^a-z0-9]+$', '', safe)
        return safe
    @staticmethod
    def extract_global_plan_id(plan_id: str) -> str:
        """
        Extrait la partie gplan_<id> d'un plan_id quel que soit son préfixe (team1_, team2_, exec_, etc.)
        """
        if plan_id =='N/A':
            return "default"
        import re
        match = re.search(r'gplan_[a-f0-9]+', plan_id)
        if not match:
          return "default"  # Valeur par défaut si aucun match trouvé
          # raise ValueError(f"Cannot extract global_plan_id from plan_id: {plan_id}")
        return match.group(0)

    async def _ensure_pod_running(self, pod_name: str):
        try:
            pod = await asyncio.to_thread(self.v1.read_namespaced_pod, pod_name, self.namespace)
            if pod.status.phase != 'Running':
                raise RuntimeError(f"Pod '{pod_name}' is not in Running state: {pod.status.phase}")
        except client.ApiException as e:
            if e.status == 404:
                raise RuntimeError(f"Pod '{pod_name}' does not exist (404).")
            else:
                raise
        except Exception as e:
            logger.error(f"Connection error while verifying pod '{pod_name}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to connect to Kubernetes API for pod '{pod_name}'.")

    async def _load_existing_environment_details(self, environment_id: str):
        """Tente de charger les détails d'un environnement depuis Firestore et K8s API."""
        environment_id = f"exec-{self.extract_global_plan_id(plan_id=environment_id)}"

        if environment_id in self.environments:
            return
        names = EnvironmentManager.generate_k8s_names(environment_id)
        pod_name = names["pod_name"]
        pvc_name = names["pvc_name"]

        self.environments[environment_id] = {
            'pod_name': pod_name,
            'pvc_name': pvc_name
        }
        try:
            env_doc_ref = db.collection(K8S_ENVIRONMENTS_COLLECTION).document(environment_id)
            env_doc = await asyncio.to_thread(env_doc_ref.get)

            if env_doc.exists:
                env_data = env_doc.to_dict()
                logger.info(f"Environment '{environment_id}' found in Firestore. Data: {env_data}")
                
                try:
                    pod = await asyncio.to_thread(self.v1.read_namespaced_pod, name=pod_name, namespace=self.namespace)
                    pvc = await asyncio.to_thread(self.v1.read_namespaced_persistent_volume_claim, name=pvc_name, namespace=self.namespace)

                    if pod.status.phase == 'Running' and pvc.status.phase == 'Bound':
                        self.environments[environment_id] = {'pod_name': pod_name, 'pvc_name': pvc_name}
                        logger.info(f"Existing environment '{environment_id}' (Pod: {pod_name}) verified 'Running' and loaded from K8s.")
                    else:
                        logger.warning(f"Existing environment '{environment_id}' (Pod: {pod_name}) found in Firestore but K8s state is not Running/Bound. Pod={pod.status.phase}, PVC={pvc.status.phase}. Marking as potentially unhealthy/stale.")
                        await asyncio.to_thread(env_doc_ref.update, {"status": "stale", "last_checked": time.time()})
                except client.ApiException as e:
                    if e.status == 404: 
                        logger.warning(f"Environment '{environment_id}' found in Firestore but Pod '{pod_name}' or PVC '{pvc_name}' not found on K8s API (404). Removing from Firestore.")
                        await asyncio.to_thread(env_doc_ref.delete)
                    else:
                        logger.error(f"Kubernetes API Error (Status {e.status}) while verifying environment '{environment_id}' on K8s: Reason={e.reason}, Body={e.body}", exc_info=True)
                        raise 
                except Exception as e:
                    logger.error(f"Unexpected error while verifying environment '{environment_id}' on K8s: {e}", exc_info=True)
                    raise
            else:
                logger.debug(f"Environment '{environment_id}' not found in Firestore. It needs to be created or is genuinely non-existent.")

        except Exception as e:
            logger.error(f"Error during initial Firestore/K8s lookup for environment '{environment_id}': {e}", exc_info=True)
    def _make_safe_k8s_name(self, base: str) -> str:
        return EnvironmentManager._make_safe_k8s_name_static(base)
    



    async def get_environment_or_fallback(self, plan_id: str, fallback_id: str = FALLBACK_ENV_ID) -> str:
        """Return the environment id for a plan, creating it if needed. If creation fails, use fallback."""
        target_env = EnvironmentManager.normalize_environment_id(plan_id)
        await self._load_existing_environment_details(target_env)
        if target_env not in self.environments:
            created = await self.create_isolated_environment(target_env)
            if not created:
                logger.warning(f"Environment '{target_env}' unavailable, falling back to '{fallback_id}'.")
                await self._load_existing_environment_details(fallback_id)
                if fallback_id not in self.environments:
                    await self.create_isolated_environment(fallback_id)
                return fallback_id
        return target_env

   

    async def create_isolated_environment(self, environment_id: str, base_image: str = "gcr.io/orchestrai-hackathon/python-devtools:3.9-full") -> str:
        environment_id = EnvironmentManager.normalize_environment_id(environment_id)
        safe_env_id = EnvironmentManager._make_safe_k8s_name_static(environment_id)

        names = EnvironmentManager.generate_k8s_names(environment_id)
        pod_name = names["pod_name"]
        pvc_name = names["pvc_name"]
        volume_name = names.get("volume_name")
        logger.info(f"Creating isolated environment '{environment_id}' with Pod: {pod_name}, PVC: {pvc_name}, Volume: {volume_name}")
        await self._load_existing_environment_details(environment_id)
        if environment_id in self.environments:
            pod_name = self.environments[environment_id]['pod_name']
            try:
                await self._ensure_pod_running(pod_name)
                logger.info(f"Environment '{environment_id}' already active in manager and pod '{pod_name}' is running. Reusing.")
                return environment_id
            except RuntimeError:
                logger.warning(f"Environment '{environment_id}' found in manager but pod '{pod_name}' missing or not running. Recreating environment.")

        try:
            try:
                logger.info(f"Checking Volume '{volume_name}' for environment '{environment_id}'...")
                await asyncio.to_thread(self.v1.read_namespaced_persistent_volume_claim, name=pvc_name, namespace=self.namespace)
                logger.info(f"PVC '{pvc_name}' already exists, reusing.")
            except client.ApiException as e:
                if e.status == 404:
                    pvc_manifest = {
                        "apiVersion": "v1",
                        "kind": "PersistentVolumeClaim",
                        "metadata": {"name": pvc_name},
                        "spec": {
                            "accessModes": ["ReadWriteOnce"],
                            "resources": {"requests": {"storage": "1Gi"}}
                        }
                    }
                    await asyncio.to_thread(self.v1.create_namespaced_persistent_volume_claim, body=pvc_manifest, namespace=self.namespace)
                    logger.info(f"PVC '{pvc_name}' created.")
                else:
                    raise

            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": pod_name,
                    "labels": {"app": "dev-environment", "environment_id": environment_id}
                },
                "spec": {
                    "serviceAccountName": "orchestrai-sa",
                    "volumes": [
                        {
                            "name": volume_name,
                            "persistentVolumeClaim": {"claimName": pvc_name}
                        }
                    ],
                    "containers": [
                        {
                            "name": "developer-sandbox",
                            "image": base_image,
                            "command": ["/bin/bash", "-c", "tail -f /dev/null"],
                            "workingDir": "/app",
                            "volumeMounts": [
                                {
                                    "name": volume_name,
                                    "mountPath": "/app"
                                }
                            ],
                            "env": [
                                {"name": "PYTHONUNBUFFERED", "value": "1"}
                            ]
                        }
                    ],
                    "restartPolicy": "Never"
                }
            }

            try:
                existing_pod = await asyncio.to_thread(self.v1.read_namespaced_pod, name=pod_name, namespace=self.namespace)
                logger.info(f"Existing Pod '{pod_name}' found, deleting and recreating.")
                await asyncio.to_thread(self.v1.delete_namespaced_pod, name=pod_name, namespace=self.namespace, body=client.V1DeleteOptions())
                
                logger.info(f"Waiting for Pod '{pod_name}' to be fully deleted before recreating...")
                w_delete = watch.Watch()
                delete_timeout = 180 
                delete_start_time = time.time()
                pod_deleted = False
                try:
                    for event in await asyncio.to_thread(w_delete.stream, self.v1.list_namespaced_pod, namespace=self.namespace,
                                                  field_selector=f"metadata.name={pod_name}", timeout_seconds=10):
                        if event['type'] == 'DELETED':
                            logger.info(f"Pod '{pod_name}' confirmed deleted.")
                            pod_deleted = True
                            w_delete.stop()
                            break
                        if time.time() - delete_start_time > delete_timeout:
                            logger.warning(f"Timeout waiting for Pod '{pod_name}' to delete.")
                            w_delete.stop()
                            break
                except client.ApiException as e:
                    if e.status == 404:
                        logger.info(f"Pod '{pod_name}' already gone during delete watch (404).")
                        pod_deleted = True
                    else:
                        logger.error(f"Error watching for Pod deletion: {e}", exc_info=True)
                        raise
                except Exception as e:
                    logger.error(f"Unexpected error during Pod deletion watch: {e}", exc_info=True)
                    raise

                if not pod_deleted:
                    try:
                        await asyncio.to_thread(self.v1.read_namespaced_pod, name=pod_name, namespace=self.namespace)
                        raise Exception(f"Pod '{pod_name}' still exists after delete attempt and watch timeout.")
                    except client.ApiException as e:
                        if e.status == 404:
                            logger.info(f"Pod '{pod_name}' confirmed deleted via read (404).")
                        else:
                            raise

            except client.ApiException as e:
                if e.status == 404:
                    pass
                else:
                    raise

            await asyncio.to_thread(self.v1.create_namespaced_pod, body=pod_manifest, namespace=self.namespace)
            logger.info(f"Pod '{pod_name}' created. Waiting for it to be running...")

            w_run = watch.Watch()
            timeout = 120
            start_time = time.time()
            while True:
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    raise Exception(f"Pod '{pod_name}' did not reach 'Running' state within {timeout} seconds.")
                
                event_stream = await asyncio.to_thread(w_run.stream, self.v1.list_namespaced_pod, namespace=self.namespace,
                                                  field_selector=f"metadata.name={pod_name}", timeout_seconds=10)
                try:
                    for event in event_stream:
                        if event['type'] == 'ADDED' or event['type'] == 'MODIFIED':
                            if event['object'].status.phase == 'Running':
                                logger.info(f"Pod '{pod_name}' is running.")
                                w_run.stop()
                                break
                        elif event['type'] == 'DELETED':
                            logger.warning(f"Pod '{pod_name}' was deleted during waiting for running.")
                            raise Exception(f"Pod '{pod_name}' was unexpectedly deleted while waiting for it to run.")
                    else:
                        await asyncio.sleep(2)
                        continue
                    break
                except StopAsyncIteration:
                    await asyncio.sleep(2)
                    continue
                except Exception as e:
                    logger.error(f"Error while watching Pod status: {e}", exc_info=True)
                    await asyncio.sleep(5)
                    continue
            
            self.environments[environment_id] = {'pod_name': pod_name, 'pvc_name': pvc_name}
            
            env_doc_ref = db.collection(K8S_ENVIRONMENTS_COLLECTION).document(environment_id)
            env_data = {
                "environment_id": environment_id,
                "pod_name": pod_name,
                "pvc_name": pvc_name,
                "base_image": base_image,
                "namespace": self.namespace,
                "status": "running",
                "created_at": time.time()
            }
            await asyncio.to_thread(env_doc_ref.set, env_data)
            logger.info(f"Environment '{environment_id}' details stored in Firestore.")

            return environment_id
        except client.ApiException as e:
            logger.error(f"Kubernetes API Error creating environment '{environment_id}': Status {e.status}, Reason {e.reason}, Body {e.body}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating environment '{environment_id}': {e}", exc_info=True)
            return None

    async def _get_valid_pod_name(self, environment_id: str) -> str:
        """
        Normalise l'environment_id, vérifie son existence dans le cache,
        et s'assure que le pod est en état Running.

        :param environment_id: ID logique du plan (ex: gplan_xxx ou exec_gplan_xxx)
        :return: pod_name valide prêt à être utilisé
        :raises: RuntimeError si l'environnement ou le pod sont invalides
        """
        if environment_id=="N/A":
            environment_id = "default"

        if not str(environment_id).startswith("exec-gplan_") and not str(environment_id) == "default":
            environment_id = f"exec-{self.extract_global_plan_id(plan_id=environment_id)}"

        # Vérifie présence dans le cache
        if environment_id not in self.environments:
            await self._load_existing_environment_details(environment_id)
        if environment_id not in self.environments:
            raise RuntimeError(
                f"Unknown environment_id: {environment_id}. Ensure it is created before use."
            )

        pod_name = self.environments[environment_id]['pod_name']

        # Vérifie état du pod
        await self._ensure_pod_running(pod_name)

        return pod_name
    async def safe_tool_call(self, tool_coro, description: str, timeout_sec: int = 60) -> dict:
        try:
            result = await asyncio.wait_for(tool_coro, timeout=timeout_sec)
            return result
        except asyncio.TimeoutError:
            msg = f"Le délai d'exécution de l'outil a été dépassé pour : {description}"
            logger.error(msg)
            return {"error": msg}
        except Exception as e:
            msg = f"Erreur lors de l'appel de l'outil ({description}): {str(e)}"
            logger.error(msg, exc_info=True)
            return {"error": msg}

    async def execute_command_in_environment(self, environment_id: str, command: str, workdir: str = "/app") -> dict:
        pod_name = await self._get_valid_pod_name(environment_id)
        container_name = "developer-sandbox"
        try:
            logger.info(f"Executing command '{command}' in Pod '{pod_name}' (container '{container_name}') at workdir '{workdir}')")
            
            exec_command = ["/bin/bash", "-c", command] 
            
            resp = await asyncio.to_thread(stream, self.v1.connect_get_namespaced_pod_exec,
                                        pod_name,
                                        self.namespace,
                                        command=exec_command,
                                        container=container_name,
                                        stderr=True, stdin=False, stdout=True, tty=False,
                                        _preload_content=False)

            stdout_buffer = io.BytesIO()
            stderr_buffer = io.BytesIO()
            
            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    chunk = resp.read_stdout()
                    if chunk:
                        stdout_buffer.write(chunk.encode('utf-8'))
                if resp.peek_stderr():
                    chunk = resp.read_stderr()
                    if chunk:
                        stderr_buffer.write(chunk.encode('utf-8'))
                if not resp.is_open():
                    break
            
            stdout = stdout_buffer.getvalue().decode('utf-8', errors='ignore').strip()
            stderr = stderr_buffer.getvalue().decode('utf-8', errors='ignore').strip()

            exit_code = 0 
            if stderr or "command not found" in stdout.lower() or "no such file or directory" in stdout.lower() or "error" in stdout.lower()[:50]:
                exit_code = 1 

            logger.info(f"Command '{command}' in '{pod_name}' finished. Exit code heuristic: {exit_code}. Output captured.")
            logger.debug(f"Stdout:\n{stdout}")
            logger.debug(f"Stderr:\n{stderr}")
            return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
        except client.ApiException as e:
            logger.error(f"Kubernetes API Error executing command '{command}' in '{pod_name}': Status {e.status}, Reason {e.reason}, Body {e.body}", exc_info=True)
            return {"stdout": "", "stderr": f"Kubernetes API Error: {e}", "exit_code": 1}
        except Exception as e:
            logger.error(f"Unexpected error executing command '{command}' in '{pod_name}': {e}", exc_info=True)
            return {"stdout": "", "stderr": f"Internal Error: {e}", "exit_code": 1}

    async def write_file_to_environment(self, environment_id: str, file_path: str, content: str) -> None:
        pod_name = await self._get_valid_pod_name(environment_id)
        container_name = "developer-sandbox"
        dir_name = os.path.dirname(file_path)
        if dir_name and dir_name != "/":
            cmd_result = await self.execute_command_in_environment(environment_id, f"mkdir -p {dir_name}")
            if cmd_result['exit_code'] != 0:
                logger.warning(f"Could not create directory '{dir_name}' in '{pod_name}': {cmd_result['stderr']}")
                if "File exists" not in cmd_result['stderr'] and "mkdir: cannot create directory" in cmd_result['stderr']:
                    raise Exception(f"Failed to create directory {dir_name}: {cmd_result['stderr']}")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            file_data = content.encode('utf-8')
            tarinfo = tarfile.TarInfo(name=os.path.basename(file_path)) 
            tarinfo.size = len(file_data)
            tar.addfile(tarinfo, io.BytesIO(file_data))
        tar_stream.seek(0)
        
        exec_command = ["/bin/bash", "-c", f"tar -C {dir_name if dir_name else '/'} -xf -"]
        
        try:
            resp = await asyncio.to_thread(stream, self.v1.connect_get_namespaced_pod_exec,
                                        pod_name,
                                        self.namespace,
                                        command=exec_command,
                                        container=container_name,
                                        stdin=True, stderr=True, stdout=True, tty=False,
                                        _preload_content=False)
            
            await asyncio.to_thread(resp.write_stdin, tar_stream.getvalue())
            await asyncio.to_thread(resp.close)

            stdout = await asyncio.to_thread(resp.read_stdout, timeout=60)
            stderr = await asyncio.to_thread(resp.read_stderr, timeout=60)

            if stderr:
                logger.error(f"Error while writing file '{file_path}' to Pod '{pod_name}': {stderr.strip()}")
                raise Exception(f"Failed to write file via tar: {stderr.strip()}")

            logger.info(f"File '{file_path}' written to Pod '{pod_name}'.")
        except client.ApiException as e:
            logger.error(f"Kubernetes API Error writing file '{file_path}' to '{pod_name}': Status {e.status}, Reason {e.reason}, Body {e.body}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error writing file '{file_path}' to '{pod_name}': {e}", exc_info=True)
            raise

    async def read_file_from_environment(self, environment_id: str, file_path: str) -> str:
        pod_name = await self._get_valid_pod_name(environment_id)
        container_name = "developer-sandbox"
        try:
            pod = await asyncio.to_thread(self.v1.read_namespaced_pod, pod_name, self.namespace)
            if pod.status.phase != 'Running':
                raise RuntimeError(f"Pod '{pod_name}' is not in Running state (current state: {pod.status.phase}).")
        except client.ApiException as e:
            if e.status == 404:
                raise RuntimeError(f"Pod '{pod_name}' does not exist.")
            else:
                raise


        exec_command = ["/bin/bash", "-c", f"tar -cf - {file_path}"]
        
        try:
            resp = await asyncio.to_thread(stream, self.v1.connect_get_namespaced_pod_exec,
                                        pod_name,
                                        self.namespace,
                                        command=exec_command,
                                        container=container_name,
                                        stderr=True, stdin=False, stdout=True, tty=False,
                                        _preload_content=False)
            
            stdout_buffer = io.BytesIO()
            stderr_buffer = io.BytesIO()

            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    chunk = resp.read_stdout()
                    if chunk:
                        stdout_buffer.write(chunk.encode('utf-8'))
                if resp.peek_stderr():
                    chunk = resp.read_stderr()
                    if chunk:
                        stderr_buffer.write(chunk.encode('utf-8'))
                if not resp.is_open():
                    break

            stderr = stderr_buffer.getvalue().decode('utf-8', errors='ignore').strip()
            if stderr:
                logger.warning(f"Stderr from tar command for '{file_path}': {stderr}")
                if "no such file or directory" in stderr.lower() or "not found" in stderr.lower():
                    raise FileNotFoundError(f"File '{file_path}' not found in container '{pod_name}'.")

            file_obj = io.BytesIO(stdout_buffer.getvalue())
            
            with tarfile.open(fileobj=file_obj, mode='r') as tar:
                members = tar.getmembers()
                if not members:
                    raise FileNotFoundError(f"No content found in tar archive for '{file_path}'.")
                
                target_filename = file_path.lstrip('/')
                member_to_extract = None
                for member in members:
                    if member.name == target_filename or member.name.endswith(f"/{target_filename.split('/')[-1]}"):
                        member_to_extract = member
                        break
                
                if member_to_extract:
                    return tar.extractfile(member_to_extract).read().decode('utf-8')
                else:
                    raise FileNotFoundError(f"File '{file_path}' not found in tar archive from Pod '{pod_name}'.")

        except client.ApiException as e:
            if e.status == 404:
                raise FileNotFoundError(f"Pod '{pod_name}' not found for file read, or API error: {e}")
            logger.error(f"Kubernetes API Error reading file '{file_path}' from '{pod_name}': Status {e.status}, Reason {e.reason}, Body {e.body}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading file '{file_path}' from '{pod_name}': {e}", exc_info=True)
            raise

    async def list_files_in_environment(self, environment_id: str, path: str = '.') -> List[Dict[str, Any]]:
        """
        Liste les fichiers et répertoires dans un chemin donné à l'intérieur d'un pod.
        Retourne une liste d'objets avec des détails sur chaque entrée.
        """
        pod_name = await self._get_valid_pod_name(environment_id)
        container_name = "developer-sandbox"
        try:
            pod = await asyncio.to_thread(self.v1.read_namespaced_pod, pod_name, self.namespace)
            if pod.status.phase != 'Running':
                raise RuntimeError(f"Pod '{pod_name}' is not in Running state (current state: {pod.status.phase}).")
        except client.ApiException as e:
            if e.status == 404:
                raise RuntimeError(f"Pod '{pod_name}' does not exist.")
            else:
                raise


        # Utilise 'find' pour obtenir des détails structurés et gère les noms de fichiers complexes.
        # -maxdepth 1 pour ne pas lister récursivement.
        # -printf '{"name":"%f", "type":"%y", "size":%s, "mtime":%T@}\n'
        # %f: Nom du fichier, %y: Type (d=dir, f=file), %s: Taille, %T@: Mtime en timestamp Unix
        # On échappe les guillemets pour le shell.
        workdir = f"/workspace{path}"  # Assure-toi que /workspace est ton point de montage racine dans le pod
        cmd_str = (
            f"cd {path} && "
            "find . -maxdepth 1 -mindepth 1 "
            "-exec stat -c '{\"name\":\"%n\", \"type\":\"%F\", \"size\":%s, \"mtime\":%Y}' {} \\; | jq -s ."
        )

        try:
            # Réutilise la logique de `execute_command_in_pod`
            result = await self.execute_command_in_environment(
                environment_id,
                cmd_str,
                workdir=path
            )
            stdout = result["stdout"]
            stderr = result["stderr"]
            exit_code = result["exit_code"]            

            if exit_code != 0:
                logger.error(f"Error listing files in '{pod_name}' at path '{path}'. Exit code: {exit_code}, Stderr: {stderr}")
                if "No such file or directory" in stderr:
                    raise FileNotFoundError(f"Path '{path}' not found in environment '{environment_id}'.")
                raise RuntimeError(f"Failed to list files: {stderr}")

            if not stdout:
                return []
            
            # La sortie de jq est un unique objet JSON (un tableau de fichiers)
            file_list_raw = json.loads(stdout)

            # Convertit le type de 'y' (d, f, l) en un type plus lisible.
            type_map = {
                'd': 'directory',
                'f': 'file',
                'l': 'link'
            }
            
            # Formatte la liste finale
            formatted_list = []
            for item in file_list_raw:
                formatted_list.append({
                    "name": item["name"],
                    "type": type_map.get(item["type"], "unknown"),
                    "size": int(item["size"]),
                    # Convertir le timestamp en une chaîne ISO 8601 serait une bonne amélioration
                    "last_modified": int(float(item["mtime"])) 
                })

            return formatted_list

        except client.ApiException as e:
            logger.error(f"Kubernetes API Error listing files in '{pod_name}': {e}", exc_info=True)
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from find command output: {stdout}", exc_info=True)
            raise RuntimeError("Failed to parse file list from environment.")
        except Exception as e:
            logger.error(f"Unexpected error listing files in '{pod_name}': {e}", exc_info=True)
            raise
 
    async def destroy_environment(self, environment_id: str) -> None:
        environment_id = EnvironmentManager.normalize_environment_id(environment_id)
        safe_env_id = EnvironmentManager._make_safe_k8s_name_static(environment_id)
        names = EnvironmentManager.generate_k8s_names(environment_id)
        pod_name = names["pod_name"]
        pvc_name = names["pvc_name"]
        
        try:
            try:
                await asyncio.to_thread(self.v1.delete_namespaced_pod, name=pod_name, namespace=self.namespace, body=client.V1DeleteOptions())
                logger.info(f"Pod '{pod_name}' requested for deletion.")
            except client.ApiException as e:
                if e.status == 404:
                    logger.warning(f"Pod '{pod_name}' not found for deletion.")
                else:
                    raise
            
            env_doc_ref = db.collection(K8S_ENVIRONMENTS_COLLECTION).document(environment_id)
            await asyncio.to_thread(env_doc_ref.delete)
            logger.info(f"Environment '{environment_id}' entry deleted from Firestore.")

            try:
                await asyncio.to_thread(self.v1.delete_namespaced_persistent_volume_claim, name=pvc_name, namespace=self.namespace, body=client.V1DeleteOptions())
                logger.info(f"PVC '{pvc_name}' requested for deletion.")
            except client.ApiException as e:
                if e.status == 404:
                    logger.warning(f"PVC '{pvc_name}' not found for deletion.")
                else:
                    raise

            self.environments.pop(environment_id, None)

            logger.info(f"Environment '{environment_id}' (Pod: {pod_name}, PVC: {pvc_name}) destruction initiated.")
            # Optionnel : attendre que le pod soit effectivement supprimé
            try:
                await self._ensure_pod_running(pod_name)
                await asyncio.sleep(5)  # Attente courte pour laisser le temps à Kubernetes de traiter la suppression
            except client.ApiException as e:
                logger.error(f"Kubernetes API Error destroying environment '{environment_id}': Status {e.status}, Reason {e.reason}, Body {e.body}", exc_info=True)
        except Exception as e:
            logger.error(f"Error destroying environment '{environment_id}': {e}", exc_info=True)