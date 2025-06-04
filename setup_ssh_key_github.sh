#!/bin/bash

echo "🔍 Clés disponibles dans ~/.ssh :"
ssh_dir="$HOME/.ssh"
keys=$(find "$ssh_dir" -type f -name "*.pub" | sed 's/\.pub$//' | xargs -n1 basename)
select keyname in $keys; do
    if [ -n "$keyname" ]; then
        selected_key="$ssh_dir/$keyname"
        echo "✅ Clé sélectionnée : $selected_key"
        break
    fi
done

# Demander si on veut mettre un alias (utile si plusieurs comptes GitHub)
read -p "Souhaites-tu utiliser un alias comme 'github-pro' ? (y/N) " alias_choice
if [[ "$alias_choice" =~ ^[Yy]$ ]]; then
    host_alias="github-pro"
    github_url="git@$host_alias:etiennerev1222/orchestrai-hackathon-ADK.git"
else
    host_alias="github.com"
    github_url="git@github.com:etiennerev1222/orchestrai-hackathon-ADK.git"
fi

# Créer ou modifier le fichier ~/.ssh/config
echo "🛠️ Mise à jour de ~/.ssh/config..."
mkdir -p ~/.ssh
touch ~/.ssh/config
chmod 600 ~/.ssh/config

cat <<EOF >> ~/.ssh/config

Host $host_alias
  HostName github.com
  User git
  IdentityFile $selected_key
  IdentitiesOnly yes
EOF

# Ajout au ssh-agent
echo "➕ Ajout de la clé au ssh-agent..."
eval "$(ssh-agent -s)"
ssh-add "$selected_key"

# Tester
echo "🔐 Test de la connexion SSH..."
ssh -T git@${host_alias}

# Appliquer à ce dépôt si en dossier Git
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "🔄 Mise à jour de l'URL du remote origin..."
    git remote set-url origin "$github_url"
    echo "✅ Nouveau remote :"
    git remote -v
else
    echo "⚠️ Ce dossier n'est pas un dépôt Git, aucune modification du remote."
fi

