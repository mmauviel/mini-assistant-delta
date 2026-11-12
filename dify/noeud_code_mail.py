# Nœud « Code » de Dify « mail » : met en page les mails des workflows B (alerte du matin) et C (fiche du 1er).
#
# Le texte ne change pas : ce nœud reprend tel quel ce qu'écrivent les autres nœuds (fiche, note de l'IA, alerte,
# données en direct) et l'habille aux couleurs de la charte Delta (Delta Blue #003366, Delta Red #C01933) :
# un bandeau avec le logo, un résumé en tête (ce qu'il faut retenir et faire), puis les sections, lisibles sur
# téléphone. Mise en page en tableaux et styles en ligne : la seule qui passe dans Gmail, Outlook et Apple Mail.
#
# Entrées :
#   genre     : facultatif. Sans lui (Dify n'accepte que des variables en entrée d'un nœud Code), le nœud
#               le déduit : une fiche reçue = « briefing » (workflow C), sinon « alert » (workflow B)
#   aeroport  : code IATA (MCO)
#   ia        : le texte du LLM (B : l'alerte ; C : la note de l'IA)
#   donnees   : B seulement, imprévu / resume (les données en direct, pour vérifier)
#   intro     : C seulement, rappel / message (le début du mail)
#   fiche     : C seulement, calcul / fiche (la fiche du mois, ou le bilan annuel)
#   logo      : adresse de l'image du logo (vide = le logo blanc du dépôt GitHub)
#   aujourd_hui : date ISO, seulement pour les tests ; vide = aujourd'hui
# Sorties :
#   html  : le mail en HTML, sur une seule ligne (à mettre dans le nœud Email avec « Convert to HTML » activé)
#   texte : le même mail en texte simple (version de secours, et lisible dans le journal de Dify)
#   apercu: la phrase que la boîte mail affiche à côté de l'objet
#
# Pourquoi une seule ligne et des caractères codés : avec « Convert to HTML », le plugin Email de Dify lit le
# contenu comme du Markdown, ligne par ligne. Une seule ligne sans « * », « [ », « ] » ni « ` » passe intacte.
import html as _html
import re
from datetime import datetime, timezone

BLEU = "#003366"        # Delta Blue (couleur principale)
ROUGE = "#C01933"       # Delta Red (secondaire)
BLEU_FONCE = "#002A50"  # Delta Dark Blue (tertiaire, en petite touche)
BLEU_CLAIR = "#7799CC"  # Delta Light Blue
VERT = "#5E7A1F"        # Delta Green assombri pour rester lisible sur blanc
ORANGE = "#B85F00"      # Delta Orange assombri pour rester lisible sur blanc
GRIS = "#5B6670"
FOND = "#EEF1F5"
LIGNE = "#D9DEE5"
POLICE = "font-family:Helvetica,Arial,sans-serif;"
LOGO = "https://raw.githubusercontent.com/mmauviel/mini-assistant-delta/main/dify/mail/delta_logo_white.png"

ACTIONS_ALERTE = [
    "Warn passengers on the affected flights through the Fly Delta app.",
    "Prepare rebookings.",
    "Reinforce standby crews and ground staff for those days.",
    "Coordinate with air traffic control.",
]

MOIS_EN = "January February March April May June July August September October November December".split()
MOIS_FR = "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()
JOURS_EN = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
JOURS_FR = "lundi mardi mercredi jeudi vendredi samedi dimanche".split()

# Niveau de perturbation écrit dans la fiche -> (couleur, texte court, prochaine étape)
NIVEAUX = {
    "recurring disruption": (ROUGE, "Recurring disruption", "Prepare the responses below before {mois}."),
    "at-risk disruption": (ORANGE, "At-risk disruption", "Prepare a light plan before {mois} and monitor closely."),
    "one-off disruption": (BLEU_FONCE, "One-off disruption", "No seasonal plan: monitor in real time."),
    "normal month": (VERT, "Normal month", "No special preparation needed: keep the usual monitoring."),
    "perturbation récurrente": (ROUGE, "Perturbation récurrente", "Préparer les réponses ci-dessous avant {mois}."),
    "perturbation à risque": (ORANGE, "Perturbation à risque", "Préparer un plan léger avant {mois} et surveiller de près."),
    "perturbation ponctuelle": (BLEU_FONCE, "Perturbation ponctuelle", "Pas de plan saisonnier : surveiller en temps réel."),
    "mois normal": (VERT, "Mois normal", "Aucune préparation particulière : surveillance habituelle."),
}


# ---------- Outils ----------

def esc(texte):
    """Échappe le texte pour le HTML, et code les caractères que le plugin Email lirait comme du Markdown."""
    t = _html.escape(str(texte or ""), quote=True)
    return t.replace("*", "&#42;").replace("[", "&#91;").replace("]", "&#93;").replace("`", "&#96;").replace("_", "&#95;")


def gras(texte):
    """Échappe, puis met en gras ce qui est entre ** ** (Markdown de la fiche ou du LLM)."""
    morceaux = re.split(r"\*\*(.+?)\*\*", str(texte or ""))
    return "".join(f"<strong>{esc(m)}</strong>" if i % 2 else esc(m) for i, m in enumerate(morceaux))


def sans_md(texte):
    """Texte simple : enlève les marques Markdown (gras, italique, citation)."""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", str(texte or ""))
    t = re.sub(r"^_(.+)_$", r"\1", t.strip())
    return t.lstrip("> ").strip()


def nombre(texte):
    try:
        return float(str(texte).replace(",", ".").replace(" ", "").strip())
    except ValueError:
        return None


def date_du_jour(jour, fr):
    if fr:
        return f"{JOURS_FR[jour.weekday()]} {jour.day} {MOIS_FR[jour.month - 1]} {jour.year}"
    return f"{JOURS_EN[jour.weekday()]} {jour.day} {MOIS_EN[jour.month - 1]} {jour.year}"


# ---------- Briques de mise en page ----------

def page(contenu, apercu, logo, titre, sous_titre, pied):
    """Le cadre du mail : fond gris, carte blanche de 600 px, bandeau bleu avec le logo, pied de page."""
    cache = (f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:{FOND};">'
             f'{esc(apercu)}</div>')
    image = (f'<img src="{esc(logo or LOGO)}" width="160" height="25" alt="DELTA" '
             f'style="display:block;border:0;outline:none;color:#FFFFFF;{POLICE}font-size:20px;font-weight:bold;letter-spacing:3px;">')
    bandeau = (f'<tr><td style="background-color:{BLEU};padding:28px 28px 22px 28px;">'
               f'{image}'
               f'<div style="{POLICE}color:#FFFFFF;font-size:22px;line-height:28px;font-weight:bold;margin-top:18px;">{esc(titre)}</div>'
               f'<div style="{POLICE}color:#C9D6E8;font-size:14px;line-height:20px;margin-top:4px;">{esc(sous_titre)}</div>'
               f'</td></tr>'
               f'<tr><td style="background-color:{ROUGE};height:4px;line-height:4px;font-size:4px;">&nbsp;</td></tr>')
    bas = (f'<tr><td style="padding:18px 28px 24px 28px;border-top:1px solid {LIGNE};{POLICE}color:{GRIS};font-size:12px;line-height:18px;">'
           f'{pied}</td></tr>')
    return (f'{cache}<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="background-color:{FOND};border-collapse:collapse;"><tr><td align="center" style="padding:24px 12px;">'
            f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
            f'style="width:100%;max-width:600px;background-color:#FFFFFF;border-collapse:collapse;border:1px solid {LIGNE};">'
            f'{bandeau}{contenu}{bas}</table></td></tr></table>')


def bloc(contenu, haut=22, bas=4):
    return f'<tr><td style="padding:{haut}px 28px {bas}px 28px;">{contenu}</td></tr>'


def titre_section(numero, texte):
    pastille = (f'<td width="30" valign="middle" style="width:30px;"><div style="width:24px;height:24px;line-height:24px;'
                f'border-radius:12px;background-color:{BLEU};color:#FFFFFF;text-align:center;{POLICE}font-size:13px;font-weight:bold;">'
                f'{esc(numero)}</div></td>') if numero else ""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin-bottom:10px;"><tr>'
            f'{pastille}<td valign="middle" style="{POLICE}color:{BLEU};font-size:17px;line-height:22px;font-weight:bold;">{esc(texte)}</td>'
            f'</tr></table>')


def paragraphe(contenu, taille=15, couleur="#1F2A37", marge=10):
    return f'<p style="margin:0 0 {marge}px 0;{POLICE}font-size:{taille}px;line-height:{round(taille * 1.5)}px;color:{couleur};">{contenu}</p>'


def puces(lignes, couleur=BLEU, taille=15):
    if not lignes:
        return ""
    rangs = "".join(
        f'<tr><td width="18" valign="top" style="width:18px;{POLICE}color:{couleur};font-size:{taille}px;line-height:{round(taille * 1.5)}px;">&#9679;</td>'
        f'<td valign="top" style="padding-bottom:6px;{POLICE}color:#1F2A37;font-size:{taille}px;line-height:{round(taille * 1.5)}px;">{l}</td></tr>'
        for l in lignes)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 8px 0;">{rangs}</table>'


def encadre(contenu, fond="#F5F7FA", bord=BLEU):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 12px 0;">'
            f'<tr><td style="background-color:{fond};border-left:4px solid {bord};padding:14px 16px;">{contenu}</td></tr></table>')


def etiquette(texte, couleur):
    return (f'<span style="display:inline-block;background-color:{couleur};color:#FFFFFF;{POLICE}font-size:12px;line-height:16px;'
            f'font-weight:bold;letter-spacing:1px;text-transform:uppercase;padding:4px 10px;border-radius:3px;">{esc(texte)}</span>')


def barres(valeurs, seuil, reseau, fr=False):
    """Petit graphique en barres, en tableaux (les images de graphique sont souvent bloquées par les boîtes mail)."""
    haut = max([v for _, v, _ in valeurs] + [seuil, reseau or 0]) * 1.15 or 1
    rangs = []
    for nom, v, alerte in valeurs:
        couleur = ROUGE if alerte else BLEU
        largeur = max(2, min(100, round(v / haut * 100)))
        rangs.append(
            f'<tr><td width="70" style="width:70px;padding:4px 8px 4px 0;{POLICE}font-size:14px;color:#1F2A37;">{esc(nom)}</td>'
            f'<td style="padding:4px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">'
            f'<tr><td width="{largeur}%" style="background-color:{couleur};height:14px;line-height:14px;font-size:1px;">&nbsp;</td>'
            f'<td style="background-color:{FOND};height:14px;line-height:14px;font-size:1px;">&nbsp;</td></tr></table></td>'
            f'<td width="64" align="right" style="width:64px;padding:4px 0 4px 8px;{POLICE}font-size:14px;font-weight:bold;color:{couleur};">'
            f'{esc(f"{v:.1f}%")}</td></tr>')
    legende = (f'<span style="color:{ROUGE};">&#9632;</span> {"au-dessus du seuil de" if fr else "above the"} {seuil:g}%'
               f'{"" if fr else " threshold"} &nbsp; <span style="color:{BLEU};">&#9632;</span> {"en dessous" if fr else "below"}')
    if reseau is not None:
        legende += f' &nbsp;&middot;&nbsp; {"Réseau Delta" if fr else "Delta network"}: {reseau:.1f}%'
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 6px 0;">'
            f'{"".join(rangs)}</table>' + paragraphe(legende, 12, GRIS))


def tableau_causes(causes, fr=False):
    tete = "".join(f'<td align="{a}" style="padding:6px 8px;{POLICE}font-size:12px;color:{GRIS};text-transform:uppercase;'
                   f'letter-spacing:1px;border-bottom:2px solid {BLEU};">{t}</td>'
                   for t, a in ((("Cause", "left"), ("Ce mois", "right"), ("Moyenne", "right"), ("Écart", "right")) if fr else
                                (("Cause", "left"), ("This month", "right"), ("Average", "right"), ("Change", "right"))))
    rangs = []
    for nom, v, moy, ecart in causes:
        couleur = ROUGE if ecart > 0.05 else VERT if ecart < -0.05 else GRIS
        signe = "+" if ecart >= 0 else "&minus;"
        rangs.append(
            f'<tr><td style="padding:7px 8px;{POLICE}font-size:14px;color:#1F2A37;border-bottom:1px solid {LIGNE};">{esc(nom.capitalize())}</td>'
            f'<td align="right" style="padding:7px 8px;{POLICE}font-size:14px;font-weight:bold;color:#1F2A37;border-bottom:1px solid {LIGNE};">{v:.1f}%</td>'
            f'<td align="right" style="padding:7px 8px;{POLICE}font-size:14px;color:{GRIS};border-bottom:1px solid {LIGNE};">{moy:.1f}%</td>'
            f'<td align="right" style="padding:7px 8px;{POLICE}font-size:14px;font-weight:bold;color:{couleur};border-bottom:1px solid {LIGNE};">'
            f'{signe}{abs(ecart):.1f} pt</td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 12px 0;">'
            f'<tr>{tete}</tr>{"".join(rangs)}</table>')


def tableau_md(lignes, seuil=25.0):
    """Tableau Markdown (bilan annuel) -> tableau HTML ; les niveaux sont colorés."""
    rangs = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lignes if not re.match(r"^\|\s*-", l.strip())]
    if not rangs:
        return ""
    tete = "".join(f'<td style="padding:6px 6px;{POLICE}font-size:11px;color:{GRIS};text-transform:uppercase;letter-spacing:1px;'
                   f'border-bottom:2px solid {BLEU};">{esc(c)}</td>' for c in rangs[0])
    corps = []
    for r in rangs[1:]:
        cases = []
        for c in r:
            bas = c.lower()
            couleur = ROUGE if bas.startswith(("recurring", "récurrente")) else ORANGE if bas.startswith(("at risk", "à risque")) else "#1F2A37"
            gros = "font-weight:bold;" if couleur != "#1F2A37" else ""
            annees = re.findall(r"(\d{4})\s*:\s*([\d.,]+)\s*%", c)
            if annees:  # « 2023: 23.3%, 2024: … » -> une ligne par année, en rouge au-dessus du seuil
                texte = "<br>".join(
                    f'<span style="white-space:nowrap;"><span style="color:{GRIS};">{a}</span>&nbsp; '
                    + (f'<strong style="color:{ROUGE};">{esc(v)}%</strong>' if (nombre(v) or 0) > seuil else f'{esc(v)}%') + "</span>"
                    for a, v in annees)
            else:
                texte = esc(c)
            cases.append(f'<td valign="top" style="padding:6px 6px;{POLICE}font-size:13px;line-height:18px;color:{couleur};{gros}'
                         f'border-bottom:1px solid {LIGNE};">{texte}</td>')
        corps.append(f'<tr>{"".join(cases)}</tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 12px 0;">'
            f'<tr>{tete}</tr>{"".join(corps)}</table>')


# ---------- Lecture de la fiche (Markdown du nœud « calcul ») ----------

def decouper_fiche(fiche):
    """Renvoie (titre, sous-titre, liste de sections (numéro, titre, lignes), pied)."""
    titre, sous_titre, sections, pied, avant = "", "", [], "", []
    for brut in (fiche or "").splitlines():
        l = brut.rstrip()
        if l.startswith("# "):
            titre = l[2:].strip()
        elif l.startswith("## "):
            m = re.match(r"##\s+(\d+)\.\s*(.+)", l)
            sections.append([m.group(1), m.group(2)] if m else ["", l[3:].strip()])
            sections[-1].append([])
        elif re.match(r"^_.+_$", l.strip()) and not sections and not sous_titre:
            sous_titre = l.strip()[1:-1]
        elif re.match(r"^_.+_$", l.strip()) and sections and sections[-1][2] and not sections[-1][2][-1].strip() and l.strip().startswith(("_Figures", "_Chiffres")):
            pied = l.strip()[1:-1]
        elif sections:
            sections[-1][2].append(l)
        else:
            avant.append(l)
    if avant and any(x.strip() for x in avant):
        sections.insert(0, ["", "", avant])
    return titre, sous_titre, sections, pied


def rendre_lignes(lignes):
    """Rendu générique : paragraphes, puces, citations, italiques, tableaux."""
    morceaux, liste, table = [], [], []

    def vider():
        if liste:
            morceaux.append(puces(liste)); liste.clear()
        if table:
            morceaux.append(tableau_md(table, seuil)); table.clear()

    seuil = 25.0
    for l in lignes:
        sq = re.search(r"(?:threshold|seuil)\s*:\s*([\d.,]+)", l)
        if sq:
            seuil = nombre(sq.group(1)) or seuil
        s = l.strip()
        if s.startswith("|"):
            if liste:
                morceaux.append(puces(liste)); liste.clear()
            table.append(s)
            continue
        if s.startswith("- "):
            if table:
                morceaux.append(tableau_md(table, seuil)); table.clear()
            liste.append(gras(s[2:]))
            continue
        vider()
        if not s:
            continue
        if s.startswith(">"):
            morceaux.append(encadre(paragraphe(f"&ldquo;{gras(s.lstrip('> ').strip())}&rdquo;", 15, "#1F2A37", 0), "#F5F7FA", BLEU_CLAIR))
        elif re.match(r"^_.+_$", s):
            morceaux.append(paragraphe(f"<em>{esc(s[1:-1])}</em>", 13, GRIS, 8))
        else:
            morceaux.append(paragraphe(gras(s)))
    vider()
    return "".join(morceaux)


def rendre_detecter(lignes):
    annees, autres, seuil, reseau = [], [], 25.0, None
    for l in lignes:
        s = l.strip()
        m = re.match(r"^- (\d{4})\s*:\s*([\d.,]+)\s*%\s*(⚠)?", s)
        if m:
            annees.append((m.group(1), nombre(m.group(2)), bool(m.group(3))))
            continue
        r = re.search(r"(?:network average|moyenne du réseau)[^:]*:\s*([\d.,]+)", s, re.IGNORECASE)
        if r:
            reseau = nombre(r.group(1))
        sq = re.search(r"(?:above|au-dessus de)\s+([\d.,]+)\s*%", s)
        if sq:
            seuil = nombre(sq.group(1)) or seuil
        autres.append(l)
    if not annees:
        return rendre_lignes(lignes)
    fr = any(re.search(r"moyenne du réseau", l, re.I) for l in lignes)
    return barres(annees, seuil, reseau, fr) + rendre_lignes([l for l in autres if not re.search(r"network average|moyenne du réseau", l, re.I)])


def rendre_expliquer(lignes):
    causes, autres, legende = [], [], ""
    for l in lignes:
        m = re.match(r"^- (.+?)\s*:\s*([\d.,]+)\s*%\s*\((?:vs|contre)\s*([\d.,]+)\s*%,\s*([+\-−]?[\d.,]+)\s*pt\)", l.strip())
        if m:
            causes.append((m.group(1), nombre(m.group(2)), nombre(m.group(3)), nombre(m.group(4).replace("−", "-"))))
        elif re.match(r"^(Share of flights delayed by each cause|Part des vols retardés par chaque cause)", l.strip()):
            legende = l.strip()
        else:
            autres.append(l)
    if not causes:
        return rendre_lignes(lignes)
    fr = legende.startswith("Part")
    return (paragraphe(esc(legende), 13, GRIS, 8) + tableau_causes(causes, fr) + rendre_lignes(autres))


# ---------- Lecture de la note de l'IA ----------

def rendre_note_ia(note):
    """La note du LLM : titres « 1. FACTS » en petites capitales, puces, paragraphes ; l'auto-contrôle en plus petit."""
    morceaux, liste, petit = [], [], False

    def vider():
        if liste:
            morceaux.append(puces(liste, BLEU_CLAIR, 13 if petit else 14)); liste.clear()

    for l in (note or "").splitlines():
        s = l.strip()
        if not s:
            continue
        m = re.match(r"^#*\s*\**(\d)\.\s*([A-ZÀ-Ý' \-]{3,})\**\s*:?$", s)
        if m:
            vider()
            petit = "CHECK" in m.group(2).upper() or "CONTR" in m.group(2).upper()
            morceaux.append(f'<div style="{POLICE}font-size:12px;line-height:16px;font-weight:bold;letter-spacing:1px;color:{BLEU};'
                            f'text-transform:uppercase;margin:14px 0 6px 0;">{esc(m.group(1))}. {esc(m.group(2).strip())}</div>')
        elif s.startswith(("- ", "* ")):
            liste.append(gras(s[2:]))
        else:
            vider()
            morceaux.append(paragraphe(gras(s.strip('"') if s.startswith('"') and s.endswith('"') else s), 13 if petit else 14,
                                       GRIS if petit else "#1F2A37", 6))
    vider()
    return "".join(morceaux)


# ---------- Mail C : la fiche du 1er ----------

def mail_fiche(aeroport, ia, intro, fiche, logo, jour):
    fr = (fiche or "").lstrip().startswith(("# Fiche", "# Bilan"))
    titre, lieu, sections, source = decouper_fiche(fiche)
    annuel = titre.lower().startswith(("annual", "bilan"))
    m_mois = re.search(r",\s*([A-Za-zéû]+)\s*$", titre)
    mois = m_mois.group(1) if m_mois else ""

    # Le résumé en tête : niveau, chiffre clé, prochaine étape
    niveau = None
    for cle, val in NIVEAUX.items():
        if re.search(r"\*\*" + re.escape(cle) + r"\*\*", fiche or "", re.IGNORECASE):
            niveau = val
            break
    annees = re.findall(r"^- (\d{4})\s*:\s*([\d.,]+)\s*%", fiche or "", re.M)
    reseau = re.search(r"(?:network average|moyenne du réseau)[^:\n]*:\s*([\d.,]+)", fiche or "", re.I)
    a_preparer = re.search(r"\*\*(?:Months to prepare|Mois à préparer)\*\*\s*:\s*([^.\n]+)", fiche or "")

    resume, apercu = "", ""
    if niveau and not annuel:
        couleur, nom_niveau, etape = niveau
        etape = etape.format(mois=mois)
        chiffre = ""
        if annees:
            an, v = annees[-1]
            chiffre = (f'<div style="{POLICE}font-size:15px;line-height:22px;color:#1F2A37;margin-top:10px;">'
                       f'<strong style="font-size:26px;line-height:30px;color:{couleur};">{esc(v)}%</strong>&nbsp; '
                       f'{"des vols en retard en" if fr else "of flights delayed in"} {esc(mois)} {esc(an)}'
                       + (f' &middot; {"réseau Delta" if fr else "Delta network"} {esc(reseau.group(1))}%' if reseau else "") + "</div>")
        resume = encadre(etiquette(nom_niveau, couleur) + chiffre
                         + f'<div style="{POLICE}font-size:15px;line-height:22px;color:#1F2A37;margin-top:10px;">'
                           f'<strong>{"À faire" if fr else "Next step"}:</strong> {esc(etape)}</div>', "#F5F7FA", couleur)
        apercu = f"{nom_niveau} at {aeroport} in {mois}. {etape}"
    elif annuel:
        mois_liste = a_preparer.group(1).strip() if a_preparer else ""
        resume = encadre(etiquette("Annual review" if not fr else "Bilan annuel", BLEU)
                         + f'<div style="{POLICE}font-size:15px;line-height:22px;color:#1F2A37;margin-top:10px;">'
                           f'<strong>{"Mois à préparer" if fr else "Months to prepare"}:</strong> {esc(mois_liste or ("none" if not fr else "aucun"))}</div>',
                         "#F5F7FA", BLEU)
        apercu = f"Months to prepare at {aeroport}: {mois_liste}." if mois_liste else f"Annual review for {aeroport}."

    # Le début du mail (rappel) : on garde les phrases, sans la salutation ni la dernière ligne automatique
    paras = [p.strip() for p in (intro or "").split("\n\n") if p.strip()]
    auto = [p for p in paras if re.search(r"sent automatically|envoyé automatiquement", p)]
    corps_intro = [p for p in paras if p not in auto]
    intro_html = "".join(paragraphe(gras(p).replace("\n", "<br>")) for p in corps_intro)

    contenu = bloc(resume + intro_html, 24, 4) if (resume or intro_html) else ""
    for numero, nom, lignes in sections:
        if numero == "1" and not annuel:
            rendu = rendre_detecter(lignes)
        elif numero == "2" and not annuel:
            rendu = rendre_expliquer(lignes)
        else:
            rendu = rendre_lignes(lignes)
        contenu += bloc((titre_section(numero, nom) if nom else "") + rendu, 18, 4)
    if (ia or "").strip():
        entete = (f'<div style="{POLICE}font-size:16px;font-weight:bold;color:{BLEU};margin:0 0 4px 0;">'
                  f'{"Note de l&#39;IA" if fr else "AI note"}</div>'
                  + paragraphe("Une proposition : à vérifier avec la checklist avant d'agir." if fr
                               else "A suggestion: check it with the checklist before acting.", 13, ORANGE, 6))
        contenu += bloc(encadre(entete + rendre_note_ia(ia), "#FBF6EE", ORANGE), 18, 4)

    pied = ""
    if source:
        pied += esc(source) + "<br><br>"
    pied += esc(" ".join(auto) or ("Ce message est envoyé automatiquement." if fr else "This message is sent automatically.")) + "<br>"
    pied += ("Projet étudiant (mini-assistant Delta) : pas une communication officielle de Delta Air Lines."
             if fr else "Student project (Delta mini-assistant): not an official Delta Air Lines communication.")

    sous = " · ".join(x for x in [lieu, f"{'Préparer' if fr else 'Prepare'} {mois}" if mois and not annuel else ""] if x)
    grand_titre = (f"{'Bilan annuel' if fr else 'Annual review'} · {aeroport}" if annuel
                   else f"{'Fiche' if fr else 'Briefing'} {mois} · {aeroport}" if mois else titre)
    html = page(contenu, apercu or grand_titre, logo, grand_titre, sous, pied)

    # Version texte
    t = [grand_titre.upper(), sous, "=" * 60, ""]
    if niveau and not annuel:
        t += [f"{niveau[1].upper()}" + (f" - {annees[-1][1]}% {'des vols en retard en' if fr else 'of flights delayed in'} {mois} {annees[-1][0]}" if annees else ""),
              f"{'À faire' if fr else 'Next step'}: {niveau[2].format(mois=mois)}", ""]
    if corps_intro:
        t += ["\n\n".join(corps_intro), ""]
    for numero, nom, lignes in sections:
        if nom:
            t += [f"{numero + '. ' if numero else ''}{nom.upper()}", "-" * 40]
        t += [sans_md(l) if not l.strip().startswith("- ") else "- " + sans_md(l.strip()[2:]) for l in lignes]
        t.append("")
    if (ia or "").strip():
        t += ["AI NOTE (suggestion, check it before acting)" if not fr else "NOTE DE L'IA (proposition, à vérifier)", "-" * 40, ia.strip(), ""]
    t += [x for x in [source, " ".join(auto)] if x]
    return html, re.sub(r"\n{3,}", "\n\n", "\n".join(t)).strip(), apercu or grand_titre


# ---------- Mail B : l'alerte du matin ----------

def mail_alerte(aeroport, ia, donnees, logo, jour):
    lignes = [l.strip() for l in (ia or "").splitlines() if l.strip()]
    titre_ia = ""
    if lignes and re.match(r"^\**alert\b", lignes[0], re.I):
        titre_ia = sans_md(lignes.pop(0))
    risques, actions, autres = [], [], []
    for l in lignes:
        s = sans_md(l)
        propre = s.lstrip("-•* ").strip().strip('"')
        if propre in ACTIONS_ALERTE or s.lower().startswith(("action", "suggested action")) and not propre.endswith(":"):
            actions.append(propre)
        elif s.startswith(("-", "•", "*")):
            risques.append(propre)
        elif re.match(r"^(suggested )?actions?\s*:?$", s, re.I):
            continue
        else:
            autres.append(propre)
    message = re.sub(r"^\s*alert\s+[A-Z]{3}\s*[:\-–]\s*", "", titre_ia, flags=re.I) or (autres.pop(0) if autres else "")

    banniere = (f'<tr><td style="background-color:#FCEDEF;padding:18px 28px;border-bottom:1px solid #F3C7CE;">'
                + etiquette("Alert", ROUGE)
                + f'<div style="{POLICE}font-size:19px;line-height:26px;font-weight:bold;color:{ROUGE};margin-top:10px;">{gras(message)}</div>'
                + "</td></tr>") if message else ""

    contenu = banniere
    if risques:
        rangs = []
        for r in risques:
            m = re.match(r"^(.{3,60}?\)|[^:]{3,60}):\s+(.+)$", r)
            quand, quoi = (m.group(1), m.group(2)) if m else ("", r)
            rangs.append(
                f'<tr><td valign="top" width="38%" style="width:38%;padding:9px 10px 9px 0;{POLICE}font-size:14px;line-height:20px;'
                f'font-weight:bold;color:{BLEU};border-bottom:1px solid {LIGNE};">{esc(quand)}</td>'
                f'<td valign="top" style="padding:9px 0;{POLICE}font-size:14px;line-height:20px;color:#1F2A37;border-bottom:1px solid {LIGNE};">'
                f'{gras(quoi)}</td></tr>')
        contenu += bloc(titre_section("", "Risks reported") +
                        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">'
                        f'{"".join(rangs)}</table>', 20, 4)
    if actions:
        cases = "".join(
            f'<tr><td width="26" valign="top" style="width:26px;{POLICE}font-size:16px;line-height:22px;color:{BLEU};">&#9744;</td>'
            f'<td valign="top" style="padding-bottom:6px;{POLICE}font-size:15px;line-height:22px;color:#1F2A37;font-weight:bold;">{esc(a)}</td></tr>'
            for a in actions)
        contenu += bloc(titre_section("", "What to do") + encadre(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">{cases}</table>',
            "#F5F7FA", BLEU), 16, 4)
    if autres:
        contenu += bloc("".join(paragraphe(gras(a)) for a in autres), 10, 4)

    brut = [l.strip() for l in (donnees or "").splitlines() if l.strip()]
    if brut:
        tete = brut.pop(0) if not brut[0].startswith("-") else "Live data"
        contenu += bloc(encadre(
            f'<div style="{POLICE}font-size:12px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;color:{GRIS};margin-bottom:6px;">'
            f'{esc(tete)}</div>' + puces([gras(b.lstrip("- ").strip()) for b in brut], BLEU_CLAIR, 13), "#F7F8FA", LIGNE), 16, 8)

    pied = ("Weather times are in UTC. Sources: FAA airport status, aviationweather.gov (airport forecast) and the National Weather Service "
            "(7-day forecast).<br>Sent automatically at 6:00 only when a risk is reported.<br>"
            "Student project (Delta mini-assistant): not an official Delta Air Lines communication.")
    titre = f"Weather and FAA alert · {aeroport}"
    sous = date_du_jour(jour, False)
    apercu = message or titre
    html = page(contenu, apercu, logo, titre, sous, pied)

    t = [titre.upper(), sous, "=" * 60, ""]
    if message:
        t += [f"ALERT: {message}", ""]
    if risques:
        t += ["RISKS REPORTED", "-" * 40] + [f"- {r}" for r in risques] + [""]
    if actions:
        t += ["WHAT TO DO", "-" * 40] + [f"[ ] {a}" for a in actions] + [""]
    t += autres + ([""] if autres else [])
    if (donnees or "").strip():
        t += ["LIVE DATA (to check)", "-" * 40, donnees.strip(), ""]
    t += ["Weather times are in UTC. Sent automatically at 6:00 only when a risk is reported."]
    return html, "\n".join(t).strip(), apercu


def main(genre: str = "", aeroport: str = "", ia: str = "", donnees: str = "", intro: str = "",
         fiche: str = "", logo: str = "", aujourd_hui: str = "") -> dict:
    ap = "".join(ch for ch in (aeroport or "").upper() if ch.isalpha())[:3]
    jour = datetime.fromisoformat(aujourd_hui) if aujourd_hui else datetime.now(timezone.utc)
    if logo and not str(logo).startswith("https://"):
        logo = ""  # seulement une adresse https
    g = (genre or "").strip().lower()
    if not g:
        g = "briefing" if (fiche or "").strip() else "alert"
    if g.startswith(("alert", "alerte")):
        html, texte, apercu = mail_alerte(ap, ia, donnees, logo, jour)
    else:
        html, texte, apercu = mail_fiche(ap, ia, intro, fiche, logo, jour)
    return {"html": html.replace("\n", " "), "texte": texte, "apercu": apercu}
