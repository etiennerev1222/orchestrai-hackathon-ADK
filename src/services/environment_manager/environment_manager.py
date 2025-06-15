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

# NOUVEAU: Import de la base de données Firestore
from src.shared.firebase_init import db

from google.oauth2 import service_account
import google.auth

# Ajouter cette variable globale en haut
GKE_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

logger = logging.getLogger(__name__)

# Collection Firestore pour stocker les informations sur les environnements
K8S_ENVIRONMENTS_COLLECTION = "kubernetes_environments"

class EnvironmentManager:
    def __init__(self):
        self.api_client = None
        gke_cluster_endpoint = os.environ.get("GKE_CLUSTER_ENDPOINT")

        configuration = client.Configuration()

        if gke_cluster_endpoint:
            logger.info(f"GKE_CLUSTER_ENDPOINT found: {gke_cluster_endpoint}. Configuring Kubernetes client for remote GKE cluster.")

            configuration.host = f"https://{gke_cluster_endpoint}"

            # SSL vérification correctement configurée
            configuration.verify_ssl = True
            configuration.ssl_ca_cert = os.environ.get("GKE_SSL_CA_CERT")
            if configuration.ssl_ca_cert:
                logger.info("SSL verification ENABLED with provided CA certificate.")
            else:
                configuration.verify_ssl = False
                logger.warning("EnvironmentManager: SSL verification is DISABLED because GKE_SSL_CA_CERT is not set. DO NOT USE IN PRODUCTION.")

            # Obtenir explicitement les ADC credentials
            # Dans __init__()
            credentials, project_id = google.auth.default(scopes=GKE_SCOPES)
            if credentials:
                try:
                    credentials.refresh(Request())
                    configuration.api_key = {"authorization": "Bearer " + credentials.token}
                    logger.info("Kubernetes client authentication configured with ADC token and correct scopes.")
                except Exception as e:
                    logger.error(f"Failed to refresh ADC token: {e}")
                    raise Exception(f"ADC token refresh failed: {e}")
            else:
                raise Exception("ADC credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS environment variable.")            

        else:
            # Chargement kube_config localement
            try:
                config.load_kube_config()
                logger.info("Kubernetes config loaded from local kube_config.")
            except config.ConfigException:
                raise Exception("Neither GKE_CLUSTER_ENDPOINT nor local kube_config found.")

        client.Configuration.set_default(configuration)
        self.api_client = client.ApiClient(configuration)

        self.v1 = client.CoreV1Api(self.api_client)
        self.apps_v1 = client.AppsV1Api(self.api_client)

        self.namespace = os.environ.get("KUBERNETES_NAMESPACE", "default")
        self.environments = {}
        logger.info(f"EnvironmentManager initialized for Kubernetes namespace: {self.namespace}.")

    async def _load_existing_environment_details(self, environment_id: str):
        """Tente de charger les détails d'un environnement depuis Firestore et K8s API."""
        if environment_id in self.environments:
            return

        pod_name = f"dev-env-{environment_id}"
        pvc_name = f"dev-env-pvc-{environment_id}"

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

    async def create_isolated_environment(self, environment_id: str, base_image: str = "python:3.9-slim-buster") -> str:
        pod_name = f"dev-env-{environment_id}"
        pvc_name = f"dev-env-pvc-{environment_id}"
        volume_name = f"dev-env-vol-{environment_id}"

        await self._load_existing_environment_details(environment_id)
        if environment_id in self.environments:
            logger.info(f"Environment '{environment_id}' already active in manager and running. Reusing.")
            return environment_id

        try:
            try:
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
                        if event['type'] == 'ADDED' or event['type'] == 'MODIFIED': # Corrected: Removed duplicate 'or event['type'] == 'ADDED''
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

    async def execute_command_in_environment(self, environment_id: str, command: str, workdir: str = "/app") -> dict:
        if environment_id not in self.environments:
            await self._load_existing_environment_details(environment_id)
            if environment_id not in self.environments:
                logger.error(f"Attempted to execute command in non-existent environment: '{environment_id}' and could not discover it.")
                return {"stdout": "", "stderr": f"Environment '{environment_id}' not found.", "exit_code": 1}
        
        pod_name = self.environments[environment_id]['pod_name']
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
        if environment_id not in self.environments:
            await self._load_existing_environment_details(environment_id)
            if environment_id not in self.environments:
                raise ValueError(f"Environment '{environment_id}' not found for writing file and could not discover it.")
        
        pod_name = self.environments[environment_id]['pod_name']
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
        if environment_id not in self.environments:
            await self._load_existing_environment_details(environment_id)
            if environment_id not in self.environments:
                raise ValueError(f"Environment '{environment_id}' not found for reading file and could not discover it.")
        
        pod_name = self.environments[environment_id]['pod_name']
        container_name = "developer-sandbox"

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

    
    async def destroy_environment(self, environment_id: str) -> None:
        pod_name = f"dev-env-{environment_id}"
        pvc_name = f"dev-env-pvc-{environment_id}"

        try:
            try:
                await asyncio.to_thread(self.v1.delete_namespaced_pod, name=pod_name, namespace=self.namespace, body=client.V1DeleteOptions())
                logger.info(f"Pod '{pod_name}' requested for deletion.")
            except client.ApiException as e:
                if e.status == 404:
                    logger.warning(f"Pod '{pod_name}' not found for deletion.")
                else:
                    raise
            
            # --- NOUVEAU: Supprimer l'entrée de Firestore après destruction K8s ---
            env_doc_ref = db.collection(K8S_ENVIRONMENTS_COLLECTION).document(environment_id)
            await asyncio.to_thread(env_doc_ref.delete)
            logger.info(f"Environment '{environment_id}' entry deleted from Firestore.")

            try: # Tenter aussi de supprimer le PVC, mais on le fait après le document.
                await asyncio.to_thread(self.v1.delete_namespaced_persistent_volume_claim, name=pvc_name, namespace=self.namespace, body=client.V1DeleteOptions())
                logger.info(f"PVC '{pvc_name}' requested for deletion.")
            except client.ApiException as e:
                if e.status == 404:
                    logger.warning(f"PVC '{pvc_name}' not found for deletion.")
                else:
                    raise

            self.environments.pop(environment_id, None)
            logger.info(f"Environment '{environment_id}' (Pod: {pod_name}, PVC: {pvc_name}) destruction initiated.")
        except Exception as e:
            logger.error(f"Error destroying environment '{environment_id}': {e}", exc_info=True)