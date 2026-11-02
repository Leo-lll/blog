#!/usr/bin/env bash
# Publie les nouveautés : vérifie que le site se génère, puis envoie sur GitHub.
# Usage : ./publier.sh "Titre de l'article"   (le message est facultatif)
set -e
cd "$(dirname "$0")"

python3 build.py

git add -A
if git diff --cached --quiet; then
  echo "Rien de nouveau à publier."
  exit 0
fi
git commit -m "${1:-Nouvel article}"
git push
echo "Envoyé. Le site sera à jour dans environ une minute."
