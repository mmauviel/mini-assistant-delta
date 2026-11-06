# Code à coller dans le nœud « Code » (Python 3) de Dify : tout le calcul du mini-assistant se fait ici.
# C'est etape7_mini_assistant.py réécrit sans pandas (Dify ne l'a pas forcément), avec seulement la bibliothèque standard.
#
# Entrées du nœud :
#   bts     : texte du fichier BTS des causes de retard (Airline_Delay_Cause.csv), lu par un Extracteur de documents
#   suivi   : texte du fichier de suivi des avions et de la météo (delta_monthly_airport_full.csv) ; vide = sans suivi
#   aeroport: code de l'aéroport (MCO, ATL…)
#   mois    : 1 à 12 pour la fiche du mois, 0 pour le bilan annuel (les 12 mois, à lancer en octobre)
#   langue  : "fr" ou "en" : langue de la fiche et de la réponse de l'IA (le prompt est toujours en anglais)
# Sorties : fiche (la fiche du mini-assistant) et prompt (les chiffres du prompt 3 + les consignes pour l'IA, version Dify 2).
# L'Extracteur de documents peut rendre un CSV tel quel ou sous forme de tableau Markdown : les deux sont lus.
import csv
import io
import math

SEUIL = 25  # % de vols en retard au-dessus duquel on parle de perturbation forte
CAUSES_COLS = ["carrier_ct", "late_aircraft_ct", "nas_ct", "weather_ct"]
SUIVI_COLS = ["Carrier_ct", "NAS_ct", "Weather_ct", "Security_ct", "Unresolved_ct"]
VIDES = ("", "nan", "NaN", "None", "null")


def lire_table(texte):
    """Lit un CSV, ou le tableau Markdown que l'Extracteur de documents de Dify fabrique à partir d'un CSV."""
    lignes = [l for l in (texte or "").splitlines() if l.strip()]
    if not lignes:
        return []
    if lignes[0].lstrip().startswith("|"):
        rows = []
        for l in lignes:
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if all(c and set(c) <= set("-: ") for c in cells):
                continue  # ligne de séparation |---|---|
            rows.append(cells)
    else:
        rows = list(csv.reader(io.StringIO("\n".join(lignes))))
    entete = rows[0]
    if entete and entete[0] == "":  # colonne d'index ajoutée par certains exports
        rows = [r[1:] for r in rows]
        entete = rows[0]
    return [dict(zip(entete, r)) for r in rows[1:]]


def nombre(x):
    return 0.0 if x is None or str(x).strip() in VIDES else float(x)


def somme(rows, col):
    return math.fsum(nombre(r.get(col)) for r in rows)


def div(a, b):
    """Division comme pandas : 0/0 donne nan, x/0 donne l'infini (au lieu d'une erreur)."""
    if b:
        return a / b
    return math.nan if a == 0 else math.copysign(math.inf, a)


def analyse(bts, suivi_txt, AP, MOIS, EN):
    T = lambda f, e: e if EN else f
    N = lambda x: f"{x:.1f}" if EN else f"{x:.1f}".replace(".", ",")
    P = "%" if EN else " %"
    SEP = T(" : ", ": ")
    NOMS_MOIS = T("janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
                  "January February March April May June July August September October November December").split()
    CAUSES = {"carrier_ct": T("compagnie", "airline"), "late_aircraft_ct": T("avion arrivé en retard", "late-arriving aircraft"),
              "nas_ct": T("système aérien national", "national aviation system"), "weather_ct": T("météo extrême", "extreme weather")}

    d = [r for r in lire_table(bts) if str(r.get("arr_flights", "")).strip() not in VIDES]
    for r in d:
        r["year"], r["month"] = int(float(r["year"])), int(float(r["month"]))
    a = [r for r in d if r.get("airport") == AP]
    if not a:
        msg = f"Aéroport {AP} absent du fichier"
        return msg, "Reply only with this sentence: " + msg
    noms = [r.get("airport_name", "") for r in a if str(r.get("airport_name", "")).strip() not in VIDES]
    nom = noms[0] if noms else AP
    y0, m0 = min((r["year"], r["month"]) for r in d)
    y1, m1 = max((r["year"], r["month"]) for r in d)
    COURT_FR = "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.".split()
    COURT_EN = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    LONG_EN = "January February March April May June July August September October November December".split()
    PERIODE = T(f"{COURT_FR[m0 - 1]} {y0} - {COURT_FR[m1 - 1]} {y1}", f"{COURT_EN[m0 - 1]} {y0} - {COURT_EN[m1 - 1]} {y1}")
    PERIODE_PROMPT = f"{LONG_EN[m0 - 1]} {y0} to {LONG_EN[m1 - 1]} {y1}"

    # 1. REPÉRER
    am = [r for r in a if r["month"] == MOIS]
    if not am:
        msg = f"Pas de vols Delta à {AP} ce mois-là dans le fichier"
        return msg, "Reply only with this sentence: " + msg
    taux_an = {}
    for y in sorted({r["year"] for r in am}):
        ry = [r for r in am if r["year"] == y]
        taux_an[y] = div(somme(ry, "arr_del15"), somme(ry, "arr_flights")) * 100
    dm = [r for r in d if r["month"] == MOIS]
    reseau = div(somme(dm, "arr_del15"), somme(dm, "arr_flights")) * 100
    haut = [v > SEUIL for v in taux_an.values()]
    n_fort = sum(haut)
    recurrent = n_fort == len(taux_an)
    a_risque = not recurrent and ((len(haut) >= 2 and haut[-1] and haut[-2]) or n_fort > len(haut) / 2)

    # 2. EXPLIQUER : causes du mois contre la moyenne de tous les mois de l'aéroport
    def parts(rows):
        vols = somme(rows, "arr_flights")
        return {c: div(somme(rows, c), vols) * 100 for c in CAUSES}
    m, calme = parts(am), parts(a)
    hausse = {c: m[c] - calme[c] for c in CAUSES}
    ecart = {c: round(m[c], 1) - round(calme[c], 1) for c in CAUSES}
    principale = max(hausse, key=hausse.get)
    del15 = somme(am, "arr_del15")
    cmin = div(somme(am, "carrier_ct"), del15) * 100
    cmax = div(somme(am, "carrier_ct") + somme(am, "late_aircraft_ct"), del15) * 100

    suivi = None
    v = [r for r in lire_table(suivi_txt) if r.get("scope") == "mainline" and r.get("airport") == AP
         and int(float(r.get("month", 0) or 0)) == MOIS]
    if v:
        tot = math.fsum(somme(v, c) for c in SUIVI_COLS)
        if tot > 0 and somme(v, "NASDelay") > 0:
            suivi = {"min": div(somme(v, "Carrier_ct"), tot) * 100,
                     "max": div(somme(v, "Carrier_ct") + somme(v, "Unresolved_ct"), tot) * 100,
                     "meteo": div(somme(v, "nas_min_wx_either"), somme(v, "NASDelay")) * 100}

    # 3. PLANIFIER : une réponse type par cause (règles du groupe)
    REPONSES = {
        "carrier_ct": T("Renforcer les équipages et les équipes au sol de réserve, et vérifier la maintenance avant le mois concerné.",
                        "Reinforce standby crews and ground staff, and bring maintenance checks forward before the month."),
        "late_aircraft_ct": T("Ajouter des marges entre les rotations des avions qui passent par cet aéroport, et suivre en temps réel les avions déjà en retard pour proposer un avion ou un équipage de remplacement.",
                              "Add buffers between rotations of aircraft passing through this airport, and track late aircraft in real time to offer a replacement aircraft or crew."),
        "nas_ct": T("Delta ne contrôle pas la cause : préparer les réacheminements, coordonner avec le contrôle aérien et prévenir les passagers plus tôt.",
                    "Delta does not control the cause: prepare rebookings, coordinate with air traffic control and warn passengers earlier."),
        "weather_ct": T("Surveiller les alertes météo et préparer un plan d'annulations ciblées.",
                        "Monitor weather alerts and prepare a targeted cancellation plan."),
    }
    ordre = [c for c in sorted(CAUSES, key=lambda c: hausse[c], reverse=True) if hausse[c] > 0][:2] or [principale]
    REPONSE_METEO = T("Suivre les prévisions d'orages aux heures d'arrivée et prévenir les passagers dès l'alerte : ici, plus de la moitié du retard « système aérien » vient du mauvais temps.",
                      "Track storm forecasts at arrival times and warn passengers as soon as an alert is issued: here, over half of air-system delay comes from bad weather.")
    meteo = suivi is not None and suivi["meteo"] >= 50
    ville = nom.split(",")[0]
    CAUSE_METEO_FR = ", en grande partie liés aux conditions météorologiques" if meteo else ""
    CAUSE_METEO_EN = ", largely due to weather conditions" if meteo else ""

    # Sortie : la fiche
    mois = NOMS_MOIS[MOIS - 1]
    L = [f"# {T('Fiche opérationnelle', 'Operational briefing')}{SEP}{AP}, {mois}", f"_{nom}_", "",
         f"## 1. {T('Repérer', 'Detect')}"]
    L += [f"- {int(y)}{SEP}{N(v)}{P}" + (" ⚠" if v > SEUIL else "") for y, v in taux_an.items()]
    L += [T(f"- Moyenne du réseau Delta en {mois} : {N(reseau)} %.", f"- Delta network average in {mois}: {N(reseau)}%."),
          T(f"- **{'Perturbation récurrente' if recurrent else 'Perturbation à risque' if a_risque else 'Perturbation ponctuelle'}** : au-dessus de {SEUIL} % {n_fort} année(s) sur {len(taux_an)}.",
            f"- **{'Recurring disruption' if recurrent else 'At-risk disruption' if a_risque else 'One-off disruption'}**: above {SEUIL}% in {n_fort} year(s) out of {len(taux_an)}.")]
    if a_risque:
        L += [T("- " + ("Au-dessus du seuil les deux dernières années de suite : la tendance monte." if haut[-1] and haut[-2] else "Au-dessus du seuil la plupart des années.") + " On prépare un plan léger et on surveille.",
                "- " + ("Above the threshold in the last two years in a row: the trend is rising." if haut[-1] and haut[-2] else "Above the threshold in most years.") + " Prepare a light plan and monitor.")]
    elif not recurrent and n_fort:
        L += [T("- Année(s) hors norme : " + ", ".join(f"{int(y)} ({N(v)} %)" for y, v in taux_an.items() if v > SEUIL) + " : un événement propre à cette année, que le calendrier ne prévoit pas.",
                "- Unusual year(s): " + ", ".join(f"{int(y)} ({N(v)}%)" for y, v in taux_an.items() if v > SEUIL) + ": an event specific to that year, which the calendar cannot predict.")]
    L += ["",
          f"## 2. {T('Expliquer', 'Explain')}",
          T(f"Part des vols retardés par chaque cause en {mois}, comparée à la moyenne de l'aéroport sur tous les mois :",
            f"Share of flights delayed by each cause in {mois}, compared with the airport's average over all months:")]
    L += [f"- {CAUSES[c]}{SEP}{N(m[c])}{P} ({T('contre', 'vs')} {N(calme[c])}{P}, {'+' if ecart[c] >= 0 else ''}{N(ecart[c])} pt)" for c in CAUSES]
    L += [T(f"- Cause qui augmente le plus : **{CAUSES[principale]}**.", f"- Cause rising most: **{CAUSES[principale]}**."),
          T(f"- Part que Delta contrôle : entre {cmin:.0f} % et {cmax:.0f} % des retards.", f"- Share Delta controls: between {cmin:.0f}% and {cmax:.0f}% of delays.")
          if suivi is None else
          T(f"- Part que Delta contrôle, en suivant chaque avion : entre {suivi['min']:.0f} % et {suivi['max']:.0f} % des retards (fichier mensuel seul : {cmin:.0f} à {cmax:.0f} %).",
            f"- Share Delta controls, tracing each aircraft: between {suivi['min']:.0f}% and {suivi['max']:.0f}% of delays (monthly file alone: {cmin:.0f} to {cmax:.0f}%).")]
    if suivi is not None:
        L += [T(f"- Mauvais temps : {suivi['meteo']:.0f} % des minutes « système aérien » tombent par orage ou nuages bas.",
                f"- Bad weather: {suivi['meteo']:.0f}% of air-system minutes fall during storms or low cloud.")]
    L += ["", f"## 3. {T('Planifier (proposition à valider)', 'Plan (proposal to validate)')}"]
    if recurrent:
        L += [T(f"Perturbation récurrente : préparer ces réponses **avant** {mois}.", f"Recurring disruption: prepare these responses **before** {mois}.")]
        L += [f"- {REPONSES[c]}" for c in ordre] + ([f"- {REPONSE_METEO}"] if meteo else [])
        msg = T(f"> Madame, Monsieur, nous vous remercions de votre confiance. En {mois}, les arrivées à {ville} connaissent fréquemment des retards{CAUSE_METEO_FR}. "
                f"Nous vous invitons à prévoir une marge suffisante pour vos correspondances. En cas de retard, vous en serez informé sans délai dans l'application Fly Delta, "
                f"avec les options qui s'offrent à vous. Nous vous souhaitons un excellent voyage.",
                f"> Dear Customer, thank you for choosing Delta. In {mois}, arrivals at {ville} are frequently delayed{CAUSE_METEO_EN}. "
                f"We recommend allowing ample time for your connections. Should your flight be delayed, you will be notified promptly in the Fly Delta app, "
                f"along with the options available to you. We wish you a pleasant journey.")
        quand = T("Message préventif, à envoyer avant le départ", "Preventive message, sent before departure")
    elif a_risque:
        L += [T(f"Perturbation à risque : préparer un plan léger **avant** {mois} et surveiller de près.",
                f"At-risk disruption: prepare a light plan **before** {mois} and monitor closely.")]
        L += [f"- {REPONSES[c]}" for c in ordre] + ([f"- {REPONSE_METEO}"] if meteo else [])
        msg = T(f"> Madame, Monsieur, nous vous remercions de votre confiance. Ces dernières années, les arrivées à {ville} ont fréquemment connu des retards en {mois}{CAUSE_METEO_FR}. "
                f"Nous vous invitons à prévoir une marge suffisante pour vos correspondances. En cas de retard, vous en serez informé sans délai dans l'application Fly Delta. "
                f"Nous vous souhaitons un excellent voyage.",
                f"> Dear Customer, thank you for choosing Delta. In recent years, arrivals at {ville} have frequently been delayed in {mois}{CAUSE_METEO_EN}. "
                f"We recommend allowing ample time for your connections. Should your flight be delayed, you will be notified promptly in the Fly Delta app. "
                f"We wish you a pleasant journey.")
        quand = T("Message préventif, à envoyer si la surveillance confirme le risque", "Preventive message, sent if monitoring confirms the risk")
    else:
        L += [T("Pas de schéma qui revient chaque année : pas de plan saisonnier. Surveiller en temps réel et, si une perturbation apparaît, appliquer :",
                "No pattern that returns every year: no seasonal plan. Monitor in real time and, if a disruption appears, apply:")]
        L += [f"- {REPONSES[c]}" for c in ordre] + ([f"- {REPONSE_METEO}"] if meteo else [])
        msg = T(f"> Madame, Monsieur, nous vous informons que votre vol à destination de {ville} est retardé, et nous vous prions de bien vouloir nous en excuser. "
                f"La nouvelle heure d'arrivée et les options qui s'offrent à vous sont disponibles dans l'application Fly Delta, et nous vous tiendrons informé de toute évolution. "
                f"Nous vous remercions de votre patience et de votre compréhension.",
                f"> Dear Customer, we regret to inform you that your flight to {ville} is delayed, and we sincerely apologize for the inconvenience. "
                f"Your new arrival time and the options available to you can be found in the Fly Delta app, and we will keep you informed of any further change. "
                f"Thank you for your patience and understanding.")
        quand = T("Message à envoyer seulement si un retard est confirmé", "Message sent only once a delay is confirmed")
    L += ["", f"## 4. {T('Informer les passagers (brouillon à valider)', 'Inform passengers (draft to validate)')}", f"_{quand}_", msg,
          "", T(f"_Chiffres calculés sur le fichier BTS ({PERIODE})" + (", suivi des avions et météo : étape 8" if suivi is not None else "") + ". Réponses et message : propositions du groupe, à valider par un responsable._",
                f"_Figures computed from the BTS file ({PERIODE})" + ("; aircraft tracing and weather: step 8" if suivi is not None else "") + ". Responses and message: group proposals, to be validated by a manager._")]
    fiche = "\n".join(L)

    # Le prompt 3 (toujours en anglais), avec les chiffres calculés ci-dessus
    CAUSES_EN = {"carrier_ct": "airline", "late_aircraft_ct": "late-arriving aircraft",
                 "nas_ct": "national aviation system", "weather_ct": "extreme weather"}
    mois_en = LONG_EN[MOIS - 1]
    niveau = "recurring" if recurrent else "at risk" if a_risque else "one-off"
    D = [f"DATA – Delta Air Lines mainline, flights arriving at {nom} ({AP}), {mois_en}, BTS data {PERIODE_PROMPT}",
         "- Share of flights delayed 15 minutes or more in " + mois_en + ", by year: " + " ; ".join(f"{int(y)} = {v:.1f}%" for y, v in taux_an.items()),
         f"- Delta network average in {mois_en}: {reseau:.1f}%",
         f"- Disruption level: {niveau} (above {SEUIL}% in {n_fort} year(s) out of {len(taux_an)}). Recurring = above {SEUIL}% every year ; "
         f"at risk = above {SEUIL}% the last two years in a row or in most years ; one-off = a single year.",
         f"- Share of flights delayed by each cause in {mois_en}, compared with the airport's average over all months:"]
    D += [f"  {CAUSES_EN[c]}: {m[c]:.1f}% (average {calme[c]:.1f}%, {'+' if ecart[c] >= 0 else ''}{ecart[c]:.1f} points)" for c in CAUSES]
    D += [f"- Cause rising most: {CAUSES_EN[principale]}"]
    if suivi is not None:
        D += [f"- Share of delays Delta controls, tracing each late aircraft back to the flight that started the delay: between {suivi['min']:.0f}% and {suivi['max']:.0f}%. "
              "The range exists because some delays cannot be traced.",
              f"- Weather inside the \"national aviation system\" cause: {suivi['meteo']:.0f}% of its delay minutes happened during thunderstorms or low cloud at the airport."]
    else:
        D += [f"- Share of delays Delta controls (monthly file only): between {cmin:.0f}% and {cmax:.0f}%."]
    # Consignes du prompt pour Dify (version 2) : les chiffres (DATA) sont ceux de etape7, les consignes sont
    # resserrées après le premier test dans Dify (statistiques dans le message aux passagers, suggestions vagues,
    # 25,2 % appelé « seuil »). L'IA choisit ses actions dans la liste du groupe et part du message déjà validé.
    ACTIONS_EN = {
        "carrier_ct": "Reinforce standby crews and ground staff, and bring maintenance checks forward before the month.",
        "late_aircraft_ct": "Add buffers between rotations of aircraft passing through this airport, and track late aircraft in real time "
                            "to offer a replacement aircraft or crew.",
        "nas_ct": "Prepare rebookings, coordinate with air traffic control and warn passengers earlier (Delta does not control this cause).",
        "weather_ct": "Monitor weather alerts and prepare a targeted cancellation plan.",
    }
    actions = [f"- {ACTIONS_EN[c]} (addresses: {CAUSES_EN[c]}, {m[c]:.1f}% in {mois_en} vs {calme[c]:.1f}% on average)" for c in ordre]
    if meteo:
        actions += [f"- Track storm forecasts at arrival times and warn passengers as soon as an alert is issued "
                    f"(addresses: bad weather, {suivi['meteo']:.0f}% of air-system delay minutes)."]
    if recurrent:
        quand_en = f"Both suggestions are part of a plan prepared before {mois_en}: say \"before {mois_en}\" as the timing."
    elif a_risque:
        quand_en = f"Both suggestions are a light plan prepared before {mois_en}, plus close monitoring during {mois_en}."
    else:
        quand_en = "Both suggestions apply in real time, only if delays appear: no seasonal plan."
    francais = not EN
    langue_txt = "French (formal French, \"vous\")" if francais else "English"
    titres = ("1. Faits / 2. Interprétation / 3. Suggestions / 4. Message aux passagers / 5. Autocontrôle" if francais
              else "1. Facts / 2. Interpretation / 3. Suggestions / 4. Passenger message / 5. Self-check")
    regles = [
        "",
        f"THRESHOLD: our group's threshold for a strong disruption is {SEUIL}%. The Delta network average ({reseau:.1f}%) is only a point of "
        "comparison: never call it the threshold.",
        "",
        "APPROVED ACTIONS (written by our group; choose from this list, do not invent other actions):",
        *actions,
        "",
        "APPROVED PASSENGER MESSAGE (draft already validated by our group):",
        "\"" + msg.lstrip("> ").strip() + "\"",
        "",
        f"ROLE: You are an operations analyst at Delta's Operations and Customer Center. You write for the manager of the {AP} station.",
        "",
        f"TASK: Write your whole answer in {langue_txt}, with exactly these 5 headings: {titres}.",
        "1. FACTS – 3 to 5 bullet points. Only numbers from DATA, or a difference between two of them with the calculation shown "
        f"(for example: {max(taux_an.values()):.1f} - {reseau:.1f} = {max(taux_an.values()) - reseau:.1f} points).",
        f"2. INTERPRETATION – {'3' if suivi is not None else '2'} sentences: (1) the disruption level and why, using the threshold; (2) whether "
        "delays are mostly controllable (whole range above 50%), mostly external (whole range below 50%) or mixed (range crossing 50%), quoting the range"
        + ("; (3) whether bad weather explains more than half of the air-system delay minutes, quoting the percentage." if suivi is not None else "."),
        "3. SUGGESTIONS – exactly 2, most useful first, each on one line: \"Suggestion N: [action taken from APPROVED ACTIONS] – "
        "[timing] – [the number from DATA it addresses]\". " + quand_en +
        " If delays are mostly external, do not choose crew, staff or maintenance actions.",
        "4. PASSENGER MESSAGE – copy the APPROVED PASSENGER MESSAGE word for word (translate it if needed). Change it only if a TODAY'S EVENT "
        "block below reports an event: then add one sentence saying that flights may be disrupted today or in the coming days, and inviting "
        "passengers to check their flight in the Fly Delta app.",
        "5. SELF-CHECK – (a) every number you used and the DATA line it comes from; (b) every sentence that is not a fact from DATA "
        "(at least the two suggestions, which are recommendations).",
        "",
        "RULES:",
        "- The passenger message contains no digits and no percentages.",
        "- Do not describe anything that is not in DATA: no airport status (hub, focus city), no team, programme, tool or initiative names, "
        "no causes other than those given, nothing about capacity, costs or staffing levels, no season, holiday or tourism explanations.",
        "- No promise about what Delta is doing beyond what the approved passenger message already says.",
        "- Do not say that you verified or calculated something unless you show the calculation.",
        "- A TODAY'S EVENT block may follow: it describes today and the next 7 days only. If it says \"not applicable\", do not mention "
        "today's conditions anywhere. "
        "If it reports nothing, say so in one sentence at the end of the interpretation.",
        "",
        f"BEFORE ANSWERING, CHECK: the passenger message has no digit; {reseau:.1f}% is never called a threshold; each suggestion has an "
        "action from the list, a timing and a number; nothing is said that DATA does not support.",
    ]
    intro = ("My group recommends that Delta Air Lines use a generative AI assistant that turns operational data into short briefings for managers. "
             "The numbers below were computed by our code from official U.S. Bureau of Transportation Statistics (BTS) data.")
    prompt = "\n".join([intro, ""] + D + regles)
    return fiche, prompt


def bilan_annuel(bts, AP, EN):
    """mois = 0 : les 12 mois de l'aéroport d'un coup, pour repérer les mois à préparer l'année suivante
    (à lancer en octobre : créneaux FAA et programme d'été se décident à ce moment-là)."""
    T = lambda f, e: e if EN else f
    N = lambda x: f"{x:.1f}" if EN else f"{x:.1f}".replace(".", ",")
    P = "%" if EN else " %"
    NOMS = T("janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
             "January February March April May June July August September October November December").split()
    LONG_EN = "January February March April May June July August September October November December".split()
    d = [r for r in lire_table(bts) if str(r.get("arr_flights", "")).strip() not in VIDES]
    for r in d:
        r["year"], r["month"] = int(float(r["year"])), int(float(r["month"]))
    a = [r for r in d if r.get("airport") == AP]
    if not a:
        msg = f"Aéroport {AP} absent du fichier"
        return msg, "Reply only with this sentence: " + msg
    noms = [r.get("airport_name", "") for r in a if str(r.get("airport_name", "")).strip() not in VIDES]
    nom = noms[0] if noms else AP
    lignes = []
    for M in range(1, 13):
        am = [r for r in a if r["month"] == M]
        if not am:
            continue
        taux = {y: div(somme([r for r in am if r["year"] == y], "arr_del15"), somme([r for r in am if r["year"] == y], "arr_flights")) * 100
                for y in sorted({r["year"] for r in am})}
        dm = [r for r in d if r["month"] == M]
        reseau = div(somme(dm, "arr_del15"), somme(dm, "arr_flights")) * 100
        haut = [v > SEUIL for v in taux.values()]
        n = sum(haut)
        niveau = "recurring" if n == len(haut) else "at risk" if ((len(haut) >= 2 and haut[-1] and haut[-2]) or n > len(haut) / 2) \
            else "one-off" if n else "normal"
        prepa = (M - 4) % 12 + 1  # préparer 3 mois avant : le 1er du mois M-3
        lignes.append((M, taux, reseau, niveau, n, prepa))
    NIV = {"recurring": T("récurrente", "recurring"), "at risk": T("à risque", "at risk"),
           "one-off": T("ponctuelle", "one-off"), "normal": T("normale", "normal")}
    a_preparer = [l for l in lignes if l[3] in ("recurring", "at risk")]
    L = [f"# {T('Bilan annuel', 'Annual review')}{T(' : ', ': ')}{AP}", f"_{nom}_", "",
         T(f"Part des vols en retard de 15 minutes ou plus, par mois et par année (seuil : {SEUIL} %).",
           f"Share of flights delayed 15 minutes or more, by month and year (threshold: {SEUIL}%)."), "",
         T("| Mois | Par année | Réseau Delta | Perturbation | Préparer dès le 1er |", "| Month | By year | Delta network | Disruption | Prepare from the 1st of |"),
         "| --- | --- | --- | --- | --- |"]
    for M, taux, reseau, niveau, n, prepa in lignes:
        par_an = ", ".join(f"{y} : {N(v)}{P}" if not EN else f"{y}: {N(v)}{P}" for y, v in taux.items())
        L.append(f"| {NOMS[M - 1]} | {par_an} | {N(reseau)}{P} | {NIV[niveau]} ({n}/{len(taux)}) | "
                 + (NOMS[prepa - 1] if niveau in ("recurring", "at risk") else "–") + " |")
    L += ["", T(f"**Mois à préparer** : {', '.join(NOMS[l[0] - 1] for l in a_preparer) or 'aucun'}. Pour chacun, lancer la fiche du mois "
                "3 mois avant (le 1er), pour avoir le temps de prévoir les renforts et les marges.",
                f"**Months to prepare**: {', '.join(NOMS[l[0] - 1] for l in a_preparer) or 'none'}. For each, run the monthly briefing "
                "3 months before (on the 1st), to have time to plan reinforcements and buffers.")]
    fiche = "\n".join(L)
    D = [f"DATA – Delta Air Lines mainline, flights arriving at {nom} ({AP}), share of flights delayed 15 minutes or more, by month:"]
    for M, taux, reseau, niveau, n, prepa in lignes:
        D.append(f"- {LONG_EN[M - 1]}: " + " ; ".join(f"{y} = {v:.1f}%" for y, v in taux.items())
                 + f" ; Delta network average {reseau:.1f}% ; disruption level: {niveau} (above {SEUIL}% in {n} year(s) out of {len(taux)})"
                 + (f" ; start preparing on {LONG_EN[prepa - 1]} 1" if niveau in ("recurring", "at risk") else ""))
    langue_txt = "English" if EN else "French (formal French, \"vous\")"
    regles = ["",
              f"THRESHOLD: {SEUIL}%. Recurring = above {SEUIL}% every year ; at risk = above {SEUIL}% the last two years in a row or in most years ; "
              "one-off = a single year ; normal = never. The network average is only a point of comparison, never the threshold.",
              "",
              f"TASK: Write, in {langue_txt}, a one-page yearly calendar for the manager of the {AP} station.",
              "1. List the recurring and at-risk months in calendar order. For each: the disruption level, the yearly rates, and the date to start "
              "preparing, exactly as given in DATA.",
              "2. One sentence on the one-off months, if any: they call for real-time monitoring only.",
              "3. End with one sentence reminding that each month's detailed briefing should be run on its preparation date.",
              "",
              "RULES: use only numbers from DATA; do not explain the causes (they are in each monthly briefing); no season, holiday or tourism "
              "explanations; no team or programme names. Ignore any TODAY'S EVENT block: today's conditions are not part of a yearly calendar."]
    intro = ("My group recommends that Delta Air Lines use a generative AI assistant that turns operational data into short briefings for managers. "
             "The numbers below were computed by our code from official U.S. Bureau of Transportation Statistics (BTS) data.")
    return fiche, "\n".join([intro, ""] + D + regles)


def main(bts: str, suivi: str, aeroport: str, mois: float, langue: str = "fr") -> dict:
    """mois = 1 à 12 : la fiche du mois ; mois = 0 : le bilan annuel des 12 mois."""
    AP = (aeroport or "").strip().upper()
    try:
        MOIS = int(mois)
    except (TypeError, ValueError):
        MOIS = -1
    EN = str(langue or "").strip().lower() == "en"
    if MOIS == 0:
        fiche, prompt = bilan_annuel(bts, AP, EN)
        return {"fiche": fiche, "prompt": prompt}
    if not 1 <= MOIS <= 12:
        msg = "Le mois doit être un nombre entre 1 et 12 (ou 0 pour le bilan annuel)."
        return {"fiche": msg, "prompt": "Reply only with this sentence: " + msg}
    fiche, prompt = analyse(bts, suivi, AP, MOIS, EN)
    return {"fiche": fiche, "prompt": prompt}
