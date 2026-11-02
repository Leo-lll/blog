#!/usr/bin/env python3
"""Générateur du blog : articles/ -> site/ (pages HTML + flux RSS).

Aucune dépendance : Python 3.11 ou plus suffit.

    python3 build.py          génère le site dans le dossier site/
    python3 build.py serve    génère puis sert le site sur http://localhost:8000
"""
import html
import os
import re
import shutil
import sys
import tomllib
import unicodedata
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

RACINE = Path(__file__).resolve().parent
ARTICLES = RACINE / "articles"
MODELES = RACINE / "templates"
STATIQUE = RACINE / "static"
SORTIE = RACINE / "site"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


# --------------------------------------------------------------------------
# Petits outils
# --------------------------------------------------------------------------

def slugifier(texte):
    """'Mon Été à Lyon !' -> 'mon-ete-a-lyon'"""
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", texte.lower()).strip("-")


def date_fr(d):
    return f"{d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]} {d.year}"


def rendre(modele, **variables):
    """Remplace {{nom}} par sa valeur, en une seule passe."""
    def remplacer(m):
        return str(variables.get(m.group(1), m.group(0)))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", remplacer, modele)


def lire_modele(nom):
    return (MODELES / nom).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Markdown (version minimale, sans dépendance)
# Gère : titres, paragraphes, gras, italique, barré, liens, images (avec
# légende), listes (imbriquées), citations, code, séparateurs, HTML brut.
# --------------------------------------------------------------------------

FENCE = re.compile(r"^\s{0,3}(```+|~~~+)\s*([\w+-]*)\s*$")
TITRE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
CITATION = re.compile(r"^\s{0,3}>")
ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
ITEM_INTERROMPT = re.compile(r"^\s{0,3}([-*+]|1[.)])\s+\S")
BLOC_HTML = re.compile(
    r"^</?(div|section|article|aside|header|footer|nav|figure|figcaption|"
    r"details|summary|table|thead|tbody|tr|td|th|ul|ol|li|p|pre|blockquote|"
    r"h[1-6]|hr|style|script|iframe|video|audio|canvas|svg|form|main|dl|dt|dd)\b",
    re.I)
IMAGE_SEULE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)')


def balise_img(alt, src, titre=None):
    t = f' title="{html.escape(titre)}"' if titre else ""
    return f'<img src="{html.escape(src)}" alt="{html.escape(alt)}"{t} loading="lazy">'


def inline(txt):
    pieces = []

    def garder(s):
        pieces.append(s)
        return f"\x00{len(pieces) - 1}\x00"

    # code, commentaires, échappements, sauts de ligne, entités
    txt = re.sub(r"(`+)(.+?)\1",
                 lambda m: garder("<code>" + html.escape(m.group(2).strip(), quote=False) + "</code>"),
                 txt, flags=re.S)
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    txt = re.sub(r"\\([\\`*_{}\[\]()#+.!~<>|-])",
                 lambda m: garder(html.escape(m.group(1), quote=False)), txt)
    txt = re.sub(r"(?: {2,}|\\)\n", lambda m: garder("<br>\n"), txt)
    txt = re.sub(r"&(#?\w+);", lambda m: garder(m.group(0)), txt)
    # liens automatiques <https://...> puis balises HTML en ligne
    txt = re.sub(r"<(https?://[^\s<>]+)>",
                 lambda m: garder(f'<a href="{html.escape(m.group(1))}">'
                                  f'{html.escape(m.group(1), quote=False)}</a>'), txt)
    txt = re.sub(r"</?[A-Za-z][^<>]*>", lambda m: garder(m.group(0)), txt)
    # images puis liens
    txt = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)',
                 lambda m: garder(balise_img(*m.groups())), txt)

    def lien(m):
        t = f' title="{html.escape(m.group(3))}"' if m.group(3) else ""
        return garder(f'<a href="{html.escape(m.group(2))}"{t}>{inline(m.group(1))}</a>')
    txt = re.sub(r'\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', lien, txt)

    txt = html.escape(txt, quote=False)

    # mise en forme
    txt = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*(?!\*)", r"<strong>\1</strong>", txt, flags=re.S)
    txt = re.sub(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w|_)", r"<strong>\1</strong>", txt, flags=re.S)
    txt = re.sub(r"\*(?=\S)(.+?)(?<=\S)\*", r"<em>\1</em>", txt, flags=re.S)
    txt = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"<em>\1</em>", txt, flags=re.S)
    txt = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", txt, flags=re.S)

    while "\x00" in txt:
        txt = re.sub(r"\x00(\d+)\x00", lambda m: pieces[int(m.group(1))], txt)
    return txt


def indent_de(ligne):
    l = ligne.expandtabs(4)
    return len(l) - len(l.lstrip())


def debut_bloc(l):
    s = l.strip()
    return bool(FENCE.match(l) or TITRE.match(l) or HR.match(l) or CITATION.match(l)
                or ITEM_INTERROMPT.match(l) or BLOC_HTML.match(s) or s.startswith("<!--"))


def liste(lignes, i):
    """Lit une liste à partir de la ligne i. Renvoie (html, ligne suivante)."""
    n = len(lignes)
    base = indent_de(lignes[i])
    ordonnee = ITEM.match(lignes[i]).group(2)[0].isdigit()
    items = []
    while i < n:
        l = lignes[i]
        if not l.strip():
            j = i + 1
            while j < n and not lignes[j].strip():
                j += 1
            if j < n:
                mj = ITEM.match(lignes[j])
                if indent_de(lignes[j]) > base or (
                        mj and indent_de(lignes[j]) == base
                        and mj.group(2)[0].isdigit() == ordonnee):
                    i = j
                    continue
            break
        mi = ITEM.match(l)
        ind = indent_de(l)
        if mi and ind == base:
            if mi.group(2)[0].isdigit() != ordonnee:
                break
            items.append({"texte": mi.group(3), "sous": []})
            i += 1
        elif mi and ind > base and items:
            sous, i = liste(lignes, i)
            items[-1]["sous"].append(sous)
        elif mi:
            break
        elif items and (ind > base or not debut_bloc(l)):
            items[-1]["texte"] += "\n" + l.strip()
            i += 1
        else:
            break
    balise = "ol" if ordonnee else "ul"
    corps = "\n".join("<li>" + inline(it["texte"]) + "".join(it["sous"]) + "</li>" for it in items)
    return f"<{balise}>\n{corps}\n</{balise}>", i


def blocs(lignes, ids):
    sortie = []
    n = len(lignes)
    i = 0
    while i < n:
        l = lignes[i]
        if not l.strip():
            i += 1
            continue

        # bloc de code
        m = FENCE.match(l)
        if m:
            marque = m.group(1)[:3]
            j = i + 1
            code = []
            while j < n and not lignes[j].strip().startswith(marque):
                code.append(lignes[j])
                j += 1
            cls = f' class="langage-{m.group(2)}"' if m.group(2) else ""
            sortie.append(f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
            i = j + 1
            continue

        # <style>, <script>, <pre>, <svg>… et commentaires : copiés tels quels
        s = l.strip()
        m = re.match(r"<(style|script|pre|svg|canvas)\b", s, re.I)
        if m or s.startswith("<!--"):
            commentaire = s.startswith("<!--")
            fin = "-->" if commentaire else f"</{m.group(1).lower()}>"
            j = i
            bloc = []
            while j < n:
                bloc.append(lignes[j])
                j += 1
                if fin in bloc[-1].lower():
                    break
            if not commentaire:
                sortie.append("\n".join(bloc))
            i = j
            continue

        # titre
        m = TITRE.match(l)
        if m:
            niveau = len(m.group(1))
            base = slugifier(re.sub(r"[`*_~\[\]]", "", m.group(2))) or "section"
            ident, k = base, 2
            while ident in ids:
                ident = f"{base}-{k}"
                k += 1
            ids.add(ident)
            sortie.append(f'<h{niveau} id="{ident}">{inline(m.group(2))}</h{niveau}>')
            i += 1
            continue

        # séparateur
        if HR.match(l):
            sortie.append("<hr>")
            i += 1
            continue

        # citation
        if CITATION.match(l):
            j = i
            q = []
            while j < n and CITATION.match(lignes[j]):
                q.append(re.sub(r"^\s{0,3}>\s?", "", lignes[j]))
                j += 1
            sortie.append("<blockquote>\n" + blocs(q, ids) + "\n</blockquote>")
            i = j
            continue

        # liste
        if ITEM.match(l):
            h, i = liste(lignes, i)
            sortie.append(h)
            continue

        # HTML brut (jusqu'à la prochaine ligne vide)
        if BLOC_HTML.match(s):
            j = i
            bloc = []
            while j < n and lignes[j].strip():
                bloc.append(lignes[j])
                j += 1
            sortie.append("\n".join(bloc))
            i = j
            continue

        # paragraphe
        para = [l]
        j = i + 1
        while j < n and lignes[j].strip() and not debut_bloc(lignes[j]):
            para.append(lignes[j])
            j += 1
        texte = "\n".join(para).strip()
        m = IMAGE_SEULE.fullmatch(texte)
        if m:
            alt, src, titre = m.groups()
            legende = f"<figcaption>{inline(titre)}</figcaption>" if titre else ""
            sortie.append(f"<figure>{balise_img(alt, src)}{legende}</figure>")
        else:
            sortie.append(f"<p>{inline(texte)}</p>")
        i = j
    return "\n".join(sortie)


def markdown(texte):
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    return blocs(texte.split("\n"), set())


# --------------------------------------------------------------------------
# Lecture des articles
# --------------------------------------------------------------------------

def separer_entete(texte):
    """Sépare l'en-tête (entre deux lignes ---) du texte de l'article."""
    meta = {}
    m = re.match(r"﻿?---[ \t]*\n(.*?)\n---[ \t]*(\n|$)", texte, re.S)
    if m:
        for ligne in m.group(1).splitlines():
            if ":" in ligne and not ligne.lstrip().startswith("#"):
                cle, val = ligne.split(":", 1)
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                meta[cle.strip().lower()] = val
        texte = texte[m.end():]
    return meta, texte


def lire_date(valeur, nom, avert):
    valeur = (valeur or "").strip()
    if not valeur:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", nom)
        valeur = m.group(1) if m else ""
    if valeur:
        try:
            d = datetime.fromisoformat(valeur.replace("/", "-"))
            if len(valeur) <= 10:
                d = d.replace(hour=12)
            return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
        except ValueError:
            avert.append(f"{nom} : date illisible « {valeur} » (format attendu : 2026-11-02)")
    else:
        avert.append(f"{nom} : pas de date, la date du jour est utilisée")
    return datetime.now(timezone.utc)


def trouver_sources(avert):
    """Renvoie la liste (nom, fichier .md, dossier ou None)."""
    sources = []
    for p in sorted(ARTICLES.iterdir()):
        if p.name.startswith((".", "_")):
            continue
        if p.is_file() and p.suffix == ".md":
            sources.append((p.stem, p, None))
        elif p.is_dir() and (p / "index.md").is_file():
            sources.append((p.name, p / "index.md", p))
        else:
            avert.append(f"articles/{p.name} ignoré (ce n'est ni un .md ni un dossier avec index.md)")
    return sources


def lien_asset(nom, dossier, racine, slug, avert):
    if nom.startswith(("http://", "https://", "//")):
        return nom
    if dossier and (dossier / nom).is_file():
        return nom
    if (STATIQUE / "pages" / nom).is_file():
        return f"{racine}pages/{nom}"
    avert.append(f"{slug} : fichier « {nom} » introuvable (ni dans l'article, ni dans static/pages/)")
    return None


def charger_article(nom, fichier, dossier, avert):
    meta, texte = separer_entete(fichier.read_text(encoding="utf-8"))
    if meta.get("brouillon", "").lower() in ("oui", "true", "1"):
        return None
    titre = meta.get("titre")
    if not titre:
        m = re.match(r"\s*#[ \t]+(.+?)[ \t]*(\n|$)", texte)
        if m:
            titre = m.group(1)
            texte = texte[m.end():]
    slug = slugifier(re.sub(r"^\d{4}-\d{2}-\d{2}[-_ ]+", "", nom)) or slugifier(nom)
    if not slug:
        avert.append(f"{nom} : nom de fichier inutilisable, article ignoré")
        return None
    if not titre:
        titre = slug.replace("-", " ").capitalize()
        avert.append(f"{nom} : pas de titre, « {titre} » utilisé")
    dt = lire_date(meta.get("date"), nom, avert)
    return {
        "slug": slug, "titre": titre, "dt": dt, "texte": texte, "dossier": dossier,
        "css": [x for x in re.split(r"[,\s]+", meta.get("css", "")) if x],
        "js": [x for x in re.split(r"[,\s]+", meta.get("js", "")) if x],
        "page": meta.get("page", "").lower(),
    }


# --------------------------------------------------------------------------
# Génération
# --------------------------------------------------------------------------

def compteur(config, chemin, avert):
    """Compteur de visites facultatif (GoatCounter), vide par défaut."""
    reglages = config.get("compteur", {})
    code = str(reglages.get("goatcounter", "")).strip()
    if not code:
        return ""
    if not re.fullmatch(r"[a-z0-9-]+", code):
        avert.append("config.toml : l'identifiant GoatCounter ne doit contenir que des lettres minuscules, chiffres et tirets")
    base = f"https://{code}.goatcounter.com/count"
    if reglages.get("mode", "image") == "script":
        return f'<script data-goatcounter="{base}" async src="//gc.zgo.at/count.js"></script>'
    return (f'<img src="{base}?p={chemin}" alt="" width="1" height="1" '
            f'style="position:absolute;left:-9999px">')


def flux_rss(config, articles, url):
    nom = xml_escape(config.get("nom", "Blog"))
    description = xml_escape(config.get("description") or config.get("nom", "Blog"))
    derniere = max((a["dt"] for a in articles), default=datetime.now(timezone.utc))
    items = []
    for a in articles:
        lien = f"{url}/{a['slug']}/"
        items.append(
            "    <item>\n"
            f"      <title>{xml_escape(a['titre'])}</title>\n"
            f"      <link>{lien}</link>\n"
            f'      <guid isPermaLink="true">{lien}</guid>\n'
            f"      <pubDate>{format_datetime(a['dt'])}</pubDate>\n"
            "    </item>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{nom}</title>\n"
        f"    <link>{url}/</link>\n"
        f"    <description>{description}</description>\n"
        "    <language>fr</language>\n"
        f"    <lastBuildDate>{format_datetime(derniere)}</lastBuildDate>\n"
        f'    <atom:link href="{url}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items) + ("\n" if items else "")
        + "  </channel>\n</rss>\n")


def construire():
    avert = []
    config = tomllib.loads((RACINE / "config.toml").read_text(encoding="utf-8"))
    nom_site = html.escape(config.get("nom", "Blog"))
    url = (os.environ.get("SITE_URL") or config.get("url") or "").rstrip("/")
    if not url:
        url = "https://exemple.org"
        avert.append("aucune adresse du site (url dans config.toml) : le flux RSS utilise https://exemple.org en attendant")

    base = lire_modele("base.html")
    modele_index = lire_modele("index.html")
    modele_item = lire_modele("item.html")
    modele_article = lire_modele("article.html")
    modele_libre = lire_modele("libre.html")

    # lecture des articles
    articles = []
    vus = {}
    for nom, fichier, dossier in trouver_sources(avert):
        a = charger_article(nom, fichier, dossier, avert)
        if not a:
            continue
        if a["slug"] in vus:
            sys.exit(f"Erreur : deux articles donnent la même adresse « {a['slug']} » ({vus[a['slug']]} et {nom})")
        vus[a["slug"]] = nom
        articles.append(a)
    articles.sort(key=lambda a: a["dt"], reverse=True)

    # dossier de sortie : copie de static/ puis pages
    if SORTIE.exists():
        shutil.rmtree(SORTIE)
    shutil.copytree(STATIQUE, SORTIE)
    reserves = {p.name for p in SORTIE.iterdir()} | {"feed.xml", "index.html"}

    for a in articles:
        if a["slug"] in reserves:
            sys.exit(f"Erreur : l'adresse « {a['slug']} » est réservée, renomme l'article")
        racine = "../"
        corps = markdown(a["texte"])
        corps = re.sub(r'(src|href)="/(?!/)', lambda m: f'{m.group(1)}="{racine}', corps)

        tete = []
        for c in a["css"]:
            h = lien_asset(c, a["dossier"], racine, a["slug"], avert)
            if h:
                tete.append(f'<link rel="stylesheet" href="{html.escape(h)}">')
        for j in a["js"]:
            h = lien_asset(j, a["dossier"], racine, a["slug"], avert)
            if h:
                tete.append(f'<script src="{html.escape(h)}" defer></script>')
        tete = "\n".join(tete)

        titre = html.escape(a["titre"])
        cpt = compteur(config, f"/{a['slug']}/", avert)
        variables = dict(racine=racine, accueil=racine, nom_site=nom_site, tete=tete,
                         compteur=cpt, titre=titre, date=date_fr(a["dt"]),
                         date_iso=a["dt"].strftime("%Y-%m-%d"), corps=corps)
        if a["page"] == "libre":
            page = rendre(modele_libre, titre_page=f"{titre} — {nom_site}", classe="page-" + a["slug"], **variables)
        else:
            variables["contenu"] = rendre(modele_article, **variables)
            page = rendre(base, titre_page=f"{titre} — {nom_site}", classe="page-" + a["slug"], **variables)

        dest = SORTIE / a["slug"]
        dest.mkdir(parents=True)
        (dest / "index.html").write_text(page, encoding="utf-8")
        if a["dossier"]:
            for p in a["dossier"].rglob("*"):
                if p.is_file() and p.name != "index.md" and not p.name.startswith("."):
                    cible = dest / p.relative_to(a["dossier"])
                    cible.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, cible)

    # page d'accueil
    liste_html = "\n".join(
        rendre(modele_item, lien=f"{a['slug']}/", titre=html.escape(a["titre"]),
               date=date_fr(a["dt"]), date_iso=a["dt"].strftime("%Y-%m-%d"))
        for a in articles)
    contenu = rendre(modele_index, intro=html.escape(config.get("intro", "")), liste=liste_html)
    accueil = rendre(base, titre_page=nom_site, classe="page-accueil", racine="", accueil="./",
                     nom_site=nom_site, tete="", compteur=compteur(config, "/", avert), contenu=contenu)
    (SORTIE / "index.html").write_text(accueil, encoding="utf-8")

    # flux RSS
    (SORTIE / "feed.xml").write_text(flux_rss(config, articles, url), encoding="utf-8")

    print(f"{len(articles)} article(s) généré(s) dans {SORTIE.relative_to(RACINE)}/")
    for a in avert:
        print("  ! " + a)


def servir():
    import functools
    import http.server
    gestionnaire = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SORTIE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 8000), gestionnaire) as serveur:
        print("Site visible sur http://localhost:8000  (Ctrl+C pour arrêter)")
        try:
            serveur.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    construire()
    if "serve" in sys.argv[1:]:
        servir()
