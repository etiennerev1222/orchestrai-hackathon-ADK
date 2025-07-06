# 🚀 Branche Release Notes – GRA-K8s Connectivity & Stability

## 🧠 Context
Cette release résout des problèmes fondamentaux de connectivité et d'authentification entre le serveur GRA (CloudRun) et le cluster Kubernetes distant (GKE). Une mauvaise compréhension initiale du réseau VPC, du scaling GKE, et de l'authentification par token a entraîné des erreurs difficiles à diagnostiquer (pods inaccessibles, 401, redéploiements inefficaces).

## ✅ Changements clés
- Injection dynamique du token d’accès Kubernetes dans l’environnement CloudRun (`K8S_BEARER_TOKEN`)
- Ajout de `GKE_SSL_CA_CERT` pour activer la vérification SSL entre CloudRun et GKE
- Refonte du script `deployment.sh` avec support tokenisé
- Activation de l’autoprovisioning GKE avec :
  - `--min-cpu 2` / `--max-cpu 8`
  - `--min-memory 4GiB` / `--max-memory 32GiB`
- Correction du `CrashLoopBackOff` causé par un scaling trop faible ou un CPU insuffisant
- Stabilisation de l’environnement `environment-manager` et vérification des droits RBAC
- Relecture complète des logs et enrichissement de la logique de diagnostic

## 📌 À surveiller
- Bien s’assurer que le bon token est injecté à chaque déploiement CloudRun
- Suivre les droits IAM sur les `ServiceAccount` pour GKE vs CloudRun
- Traiter plus rigoureusement les redéploiements : forcer le trafic vers la bonne révision

