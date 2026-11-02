# Mon blog

Un blog statique minimal : des articles en Markdown, un flux RSS, rien d'autre.
Un seul script (`build.py`, sans dépendance) transforme `articles/` en pages HTML dans `site/`.

## Mettre en ligne (une seule fois)

1. Crée un dépôt **public** sur github.com et envoie-y le contenu de ce dossier.
2. Dans le dépôt : *Settings → Pages → Build and deployment → Source : **GitHub Actions***.
3. Un premier envoi déclenche la publication. L'adresse apparaît dans *Settings → Pages*.

## Publier un article (routine)

**Depuis le navigateur, sans terminal :** sur github.com, ouvre le dossier `articles/`, clique sur *Add file → Create new file*, nomme le fichier (par exemple `mon-article.md`), colle le texte, puis *Commit changes*. Pour une image : *Add file → Upload files*. Le site est à jour environ une minute plus tard.

**Depuis l'ordinateur :** crée ou modifie le fichier dans `articles/`, puis lance `./publier.sh "Titre"`.
Pour voir le résultat avant de publier : `python3 build.py serve` puis ouvre http://localhost:8000.

## Écrire un article

Un fichier `.md` dans `articles/` :

```
---
titre: Mon article
date: 2026-11-05
---

Le texte, en Markdown.
```

- `titre` et `date` (format `AAAA-MM-JJ`) sont les seuls champs utiles. Autres champs facultatifs : `css`, `js`, `page` (voir plus bas) et `brouillon: oui` (l'article n'est pas généré).
- Raccourci pour un post rapide : nomme le fichier `2026-11-05-mon-idee.md` et commence-le par `# Mon idée`. La date vient du nom du fichier, le titre de la première ligne, l'adresse sera `/mon-idee/`.
- L'adresse d'un article est son nom de fichier, simplifié (sans accents ni espaces).

**Markdown géré :** titres `#`, gras, italique, ~~barré~~, liens, images, listes (imbriquées possibles), citations `>`, code, séparateur `---`, et HTML brut quand il le faut. Pas de tableaux ni de notes de bas de page pour l'instant (on peut en écrire en HTML).

## Images

Deux façons :

- **À côté de l'article.** Crée un dossier au lieu d'un fichier : `articles/mon-article/index.md`, et mets-y les images. Dans le texte : `![description](photo.jpg "légende facultative")`.
- **Partagées.** Dépose-les dans `static/images/` et écris `![description](/images/photo.jpg)`.

Une image seule sur sa ligne devient une figure ; le texte entre guillemets est sa légende. Les images ne sont pas redimensionnées : pense à les exporter à une taille raisonnable (le site publié ne doit pas dépasser 1 Go).

## Style

- **Global :** `static/style.css`. Tout ce qui se règle d'un chiffre ou d'une couleur (marges, largeur, épaisseur de trait, police) est en haut, dans `:root`.
- **Structure des pages :** `templates/` (`base.html`, `index.html`, `article.html`, `item.html`). Ce sont du HTML ordinaire avec des `{{emplacements}}`.
- **Par page :** dans l'en-tête de l'article, `css: colonnes.css` et/ou `js: animation.js` (plusieurs fichiers séparés par des virgules). Le fichier est cherché d'abord dans le dossier de l'article, puis dans `static/pages/` (utile pour un style réutilisé par plusieurs articles). Il n'est chargé que sur cette page. Voir `articles/exemple-colonnes/`.
- **Page entièrement libre :** `page: libre` dans l'en-tête. L'article n'utilise alors ni le gabarit commun ni `style.css` : seul son propre contenu et ses propres fichiers comptent.

## Flux RSS

`feed.xml` contient, pour chaque article, le titre, la date et le lien. Rien d'autre pour le moment.

## Visibilité

Le site est public mais demande aux moteurs de recherche de ne pas l'indexer (`robots.txt` et balise `noindex`). C'est une demande de politesse, pas une protection : toute personne qui a l'adresse peut lire.

## Compteur de visites (facultatif)

Désactivé par défaut. Pour l'activer, crée un compte gratuit sur goatcounter.com, puis renseigne l'identifiant dans `config.toml`, section `[compteur]`. Mode `image` : aucun JavaScript. Les lecteurs qui te suivent uniquement par RSS ne sont pas comptés.

## Nom de domaine

Le jour où tu en as un : dans *Settings → Pages → Custom domain*, puis renseigne `url` dans `config.toml`.
