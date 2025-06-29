#!/bin/bash

# Configuration
# Remplacez 'orchestrai-hackathon' par l'ID de votre projet GCP
PROJECT_ID="orchestrai-hackathon" 
# Compte de service par défaut de Cloud Run (il est souvent au format <PROJECT_NUMBER>-compute@developer.gserviceaccount.com)
CLOUD_RUN_SA="434296769439-compute@developer.gserviceaccount.com"
# Compte de service Google Cloud lié à votre Service Account Kubernetes 'orchestrai-sa'
# (C'est le GSA qui exécute vos pods GKE, et qui valide les jetons entrants)
GKE_SA="orchestrai-gra-firestore@${PROJECT_ID}.iam.gserviceaccount.com" 

echo "--- Vérification des permissions IAM pour la communication Cloud Run -> GKE ---"
echo "Projet GCP: ${PROJECT_ID}"
echo "Compte de service Cloud Run: ${CLOUD_RUN_SA}"
echo "Compte de service GKE (lié à orchestrai-sa): ${GKE_SA}"
echo ""

# Fonction pour vérifier si un rôle est attribué à un membre sur une ressource (compte de service)
check_iam_binding() {
    local member="$1"        # Le membre (ex: serviceAccount:email@example.com)
    local role="$2"          # Le rôle à vérifier (ex: roles/iam.serviceAccountUser)
    local resource_sa="$3"   # Le compte de service ressource sur lequel le rôle est attribué

    echo "Vérification si '${member}' a le rôle '${role}' sur '${resource_sa}'..."

    # Récupère la politique IAM du compte de service ressource et filtre les membres avec le rôle donné
    BINDINGS=$(gcloud iam service-accounts get-iam-policy "${resource_sa}" \
        --project="${PROJECT_ID}" \
        --format="json" 2>/dev/null | jq -r ".bindings[] | select(.role == \"${role}\") | .members[]" 2>/dev/null)

    # Vérifie si le membre est présent dans la liste des membres ayant ce rôle
    if echo "${BINDINGS}" | grep -q "${member}"; then
        echo "✅ Le rôle '${role}' est correctement attribué à '${member}' sur '${resource_sa}'."
        return 0
    else
        echo "❌ Le rôle '${role}' n'est PAS attribué à '${member}' sur '${resource_sa}'."
        return 1
    fi
}

# --- Étape de vérification principale ---
echo "Étape 1: Vérification de l'autorisation du compte Cloud Run à agir en tant que compte GKE."
echo "Ceci est nécessaire pour que le GKE SA puisse valider les jetons émis par le Cloud Run SA."
if ! check_iam_binding "serviceAccount:${CLOUD_RUN_SA}" "roles/iam.serviceAccountUser" "${GKE_SA}"; then
    echo ""
    echo "➡️ Pour corriger cela, exécutez la commande suivante :"
    echo "gcloud iam service-accounts add-iam-policy-binding \\"
    echo "    \"${GKE_SA}\" \\"
    echo "    --member=\"serviceAccount:${CLOUD_RUN_SA}\" \\"
    echo "    --role=\"roles/iam.serviceAccountUser\" \\"
    echo "    --project=\"${PROJECT_ID}\""
    echo ""
    echo "Ce rôle permet au compte de service Cloud Run d'utiliser le compte de service GKE pour l'authentification."
else
    echo "Le compte de service Cloud Run semble avoir les permissions nécessaires sur le compte de service GKE."
fi

echo ""
echo "--- Vérification terminée ---"
echo "Si des rôles ont été ajoutés, attendez quelques minutes pour la propagation IAM (cela peut prendre quelques minutes) et redéployez/redémarrez vos services Cloud Run et GKE pour qu'ils prennent en compte les nouvelles permissions."

