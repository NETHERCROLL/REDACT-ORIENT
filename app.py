import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import streamlit as st
from groq import Groq
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from streamlit_local_storage import LocalStorage

# Page Configuration
st.set_page_config(page_title="Logiciel de Gestion de Rapports IA", page_icon="📋", layout="wide")

# Initialisation du module de stockage local du navigateur
local_storage = LocalStorage()

# ==========================================
# 1. GESTION DE L'E-MAIL DANS LE NAVIGATEUR (LOCALSTORAGE)
# ==========================================
# Récupération de l'e-mail sauvegardé dans le navigateur de cet appareil
email_sauvegarde = local_storage.getItem("email_defaut_utilisateur")

if "email_defaut" not in st.session_state:
    st.session_state["email_defaut"] = email_sauvegarde if email_sauvegarde else ""

if "historique_rapports" not in st.session_state:
    st.session_state["historique_rapports"] = {}

# Configuration de la clé API Groq
if "GROQ_API_KEY" in st.secrets:
    client_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])
else:
    st.error("Veuillez configurer la clé GROQ_API_KEY dans vos secrets Streamlit (`.streamlit/secrets.toml`).")
    st.stop()

GROQ_MODEL = "openai/gpt-oss-20b"

# Configuration SMTP d'expédition
SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", 587))
SMTP_EMAIL = st.secrets.get("SMTP_EMAIL", "")
SMTP_PASSWORD = st.secrets.get("SMTP_PASSWORD", "")

# ==========================================
# 2. BARRE LATÉRALE - CONFIGURATION DESTINATAIRE INDIVIDUEL
# ==========================================
st.sidebar.title("⚙️ Configuration Appareil")

# Détection de l'e-mail dans le stockage local
email_actuel = local_storage.getItem("email_defaut_utilisateur")

if not email_actuel:
    st.sidebar.warning("⚠️ Aucun e-mail par défaut sur cet appareil")
    email_input = st.sidebar.text_input("Adresse e-mail par défaut pour cet appareil :")
    if st.sidebar.button("Enregistrer sur cet appareil"):
        if "@" in email_input and "." in email_input:
            local_storage.setItem("email_defaut_utilisateur", email_input.strip())
            st.session_state["email_defaut"] = email_input.strip()
            st.sidebar.success("Enregistré dans la mémoire de votre appareil !")
            st.rerun()
        else:
            st.sidebar.error("Veuillez entrer une adresse e-mail valide.")
else:
    st.sidebar.info(f"📱 E-mail par défaut sur cet appareil :\n**{email_actuel}**")
    if st.sidebar.button("Changer l'e-mail sur cet appareil"):
        local_storage.deleteItem("email_defaut_utilisateur")
        st.session_state["email_defaut"] = ""
        st.rerun()

# Configuration visuelle des 3 niveaux de gravité
GRAVITE_CONFIG = {
    "VERT": {
        "color": "#16A34A",
        "bg_pdf": colors.HexColor("#16A34A"),
        "label": "Gravité Faible / Normal"
    },
    "JAUNE": {
        "color": "#D97706",
        "bg_pdf": colors.HexColor("#D97706"),
        "label": "Gravité Moyenne / Attention"
    },
    "ROUGE": {
        "color": "#DC2626",
        "bg_pdf": colors.HexColor("#DC2626"),
        "label": "Gravité Élevée / Urgence"
    }
}

st.title("📋 Logiciel Professionnel de Rédaction de Rapports")
st.caption("Évaluation automatique du niveau de gravité par l'IA")

# ==========================================
# 3. FONCTION D'ENVOI E-MAIL SMTP
# ==========================================
def envoyer_email_rapport(destinataire, sujet, corps, pdf_data, pdf_filename):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return False, "Identifiants SMTP d'expédition absents dans secrets.toml."
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = destinataire
        msg['Subject'] = sujet

        msg.attach(MIMEText(corps, 'plain'))

        part = MIMEApplication(pdf_data, Name=pdf_filename)
        part['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
        msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, destinataire, msg.as_string())
        server.quit()
        return True, "E-mail envoyé avec succès !"
    except Exception as e:
        return False, f"Erreur d'envoi d'e-mail : {str(e)}"

# ==========================================
# 4. FORMULAIRE ET DONNÉES ENTRANTES
# ==========================================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("1. Informations de l'Émetteur")
    nom_entreprise = st.text_input("Nom de l'entreprise * :", placeholder="ex: Groupe Construction SA")
    nom_redacteur = st.text_input("Nom et Prénom du rédacteur * :", placeholder="ex: Jean Dupont")
    email_redacteur = st.text_input("Adresse e-mail du rédacteur (optionnel) :", placeholder="ex: j.dupont@entreprise.com")

with col_right:
    st.subheader("2. Paramètres du Rapport")
    mode_rapport = st.radio("Type de transmission / Action :", ["Nouveau rapport", "Modifier un ancien rapport (Mise à jour)"])

    rapport_existant_cle = None
    contenu_ancien = ""
    if mode_rapport == "Modifier un ancien rapport (Mise à jour)":
        if not st.session_state["historique_rapports"]:
            st.warning("Aucun rapport sauvegardé dans l'historique.")
        else:
            rapport_existant_cle = st.selectbox(
                "Sélectionnez le rapport à mettre à jour :", 
                list(st.session_state["historique_rapports"].keys())
            )
            contenu_ancien = st.session_state["historique_rapports"][rapport_existant_cle]["texte"]
            st.info("L'IA intégrera les nouvelles remarques dans le rapport précédent.")

st.markdown("---")
st.subheader("3. Contenu et Destinataire")

titre_rapport = st.text_input("Titre du rapport * :", placeholder="ex: Rapport d'inspection du chantier Nord")

notes_brutes = st.text_area(
    "Informations et faits à inclure dans le rapport * :", 
    height=150, 
    placeholder="Saisissez vos observations. L'IA analysera la gravité et classera vos remarques sous de grands titres."
)

# Choix du destinataire e-mail
st.subheader("📬 Destinataire")
choix_destinataire = st.radio("Sélection du destinataire :", ["E-mail par défaut de cet appareil", "Saisir un autre destinataire"], horizontal=True)

email_defaut_appareil = local_storage.getItem("email_defaut_utilisateur")

if choix_destinataire == "E-mail par défaut de cet appareil":
    email_destinataire_final = email_defaut_appareil if email_defaut_appareil else ""
    if email_destinataire_final:
        st.success(f"Sera envoyé à l'adresse enregistrée sur votre appareil : **{email_destinataire_final}**")
    else:
        st.error("Aucun e-mail n'est configuré dans le panneau de gauche pour cet appareil.")
else:
    email_destinataire_final = st.text_input("Saisissez l'adresse e-mail du destinataire :")

# ==========================================
# 5. GÉNÉRATION PDF (CERCLE DE GRAVITÉ EN HAUT À GAUCHE)
# ==========================================
def generer_pdf(entreprise, redacteur, email_red, gravite_key, titre, contenu):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    cfg_g = GRAVITE_CONFIG.get(gravite_key, GRAVITE_CONFIG["VERT"])

    # --- 1. PUCE DE GRAVITÉ EN HAUT À GAUCHE ---
    cercle_html = f"<font color='{cfg_g['color']}' size=20><b>●</b></font> <font color='#334155' size=11><b>GRAVITÉ : {cfg_g['label'].upper()}</b></font>"
    story.append(Paragraph(cercle_html, styles['Normal']))
    story.append(Spacer(1, 10))

    # --- 2. INFORMATIONS ÉMETTEUR ---
    meta_text = f"<b>Entreprise :</b> {entreprise}<br/><b>Rédacteur :</b> {redacteur}"
    if email_red:
        meta_text += f"<br/><b>E-mail :</b> {email_red}"
        
    meta_data = [[Paragraph(meta_text, styles['Normal'])]]
    t_meta = Table(meta_data, colWidths=[540])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1"))
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 15))

    # --- 3. TITRE DU RAPPORT ---
    title_style = ParagraphStyle('TitreStyle', parent=styles['Heading1'], fontSize=15, leading=19, textColor=colors.HexColor("#0F172A"), spaceAfter=12)
    story.append(Paragraph(titre.upper(), title_style))
    story.append(Spacer(1, 8))

    # --- 4. CORPS DU RAPPORT ---
    h2_style = ParagraphStyle('H2Style', parent=styles['Heading2'], fontSize=11, leading=15, textColor=colors.HexColor("#1E293B"), spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=9.5, leading=13.5, spaceAfter=5)

    for line in contenu.split('\n'):
        line_str = line.strip()
        if line_str.startswith("#"):
            clean_head = line_str.replace("#", "").strip()
            story.append(Paragraph(f"<b>{clean_head}</b>", h2_style))
        elif line_str:
            story.append(Paragraph(line_str, body_style))
        else:
            story.append(Spacer(1, 3))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ==========================================
# 6. EXÉCUTION, ANALYSE IA ET ENVOI AUTOMATIQUE
# ==========================================
if st.button("🚀 Générer et Envoyer le Rapport"):
    if not email_destinataire_final:
        st.error("Veuillez renseigner ou enregistrer un e-mail destinataire valide.")
    elif not nom_entreprise or not nom_redacteur or not titre_rapport or not notes_brutes:
        st.warning("Veuillez remplir tous les champs obligatoires (*).")
    else:
        with st.spinner("Analyse automatique de la gravité et structuration du rapport via Groq..."):
            
            if mode_rapport == "Modifier un ancien rapport (Mise à jour)" and contenu_ancien:
                prompt_user = f"""
                TÂCHE 1 : Évalue le niveau de gravité global des faits rapportés (choisis UNIQUEMENT entre: VERT, JAUNE, ROUGE).
                - VERT = Situation normale, entretien de routine, légères remarques sans danger.
                - JAUNE = Dysfonctionnement mineur, retard, problème nécessitant attention sans danger immédiat.
                - ROUGE = Danger, accident, urgence absolue, panne majeure, non-conformité grave.

                La TOUTE PREMIÈRE LIGNE de ta réponse doit être EXACTEMENT sous cette forme :
                GRAVITE: [VERT ou JAUNE ou ROUGE]

                TÂCHE 2 : Rédige le rapport mis à jour sans inventer aucun fait ni chiffre.
                Classé sous des grands titres utilisant le symbole '#' (ex: # 1. RAPPEL DES FAITS, # 2. MISES À JOUR).

                Rapport existant :
                {contenu_ancien}

                Nouvelles observations :
                {notes_brutes}
                """
            else:
                prompt_user = f"""
                TÂCHE 1 : Évalue le niveau de gravité global des faits ci-dessous (choisis UNIQUEMENT entre: VERT, JAUNE, ROUGE).
                - VERT = Situation normale, entretien de routine, absence de risque.
                - JAUNE = Problème mineur, anomalie, point d'attention.
                - ROUGE = Risque grave, urgence, accident, panne critique.

                La TOUTE PREMIÈRE LIGNE de ta réponse doit être EXACTEMENT sous cette forme :
                GRAVITE: [VERT ou JAUNE ou ROUGE]

                TÂCHE 2 : Organise les informations de façon professionnelle sans rien inventer.
                Utilise des grands titres avec le symbole '#' (ex: # 1. CONTEXTE ET OBSERVATIONS).

                Notes brutes :
                {notes_brutes}
                """

            try:
                completion = client_groq.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": "Tu es un expert strict en gestion de risques et rédaction de rapports d'activité."},
                        {"role": "user", "content": prompt_user}
                    ],
                    temperature=0.1
                )
                
                reponse_brute = completion.choices[0].message.content

                # Extraction de la gravité
                gravite_detectee = "VERT"
                lines = reponse_brute.split("\n")
                first_line = lines[0].upper()
                
                if "GRAVITE:" in first_line or "GRAVITÉ:" in first_line:
                    if "ROUGE" in first_line:
                        gravite_detectee = "ROUGE"
                    elif "JAUNE" in first_line:
                        gravite_detectee = "JAUNE"
                    elif "VERT" in first_line:
                        gravite_detectee = "VERT"
                    texte_structure = "\n".join(lines[1:]).strip()
                else:
                    texte_structure = reponse_brute.strip()

                # Sauvegarde historique dans la session
                st.session_state["historique_rapports"][titre_rapport] = {
                    "entreprise": nom_entreprise,
                    "redacteur": nom_redacteur,
                    "gravite": gravite_detectee,
                    "texte": texte_structure
                }

                # Affichage Cercle de Gravité en haut à gauche
                cfg_g = GRAVITE_CONFIG[gravite_detectee]
                st.markdown(
                    f"<div style='display: flex; align-items: center; margin-bottom: 15px;'>"
                    f"<span style='color: {cfg_g['color']}; font-size: 28px; margin-right: 8px;'>●</span>"
                    f"<span style='font-weight: bold; color: #334155; font-size: 16px;'>GRAVITÉ DÉTECTÉE : {cfg_g['label'].upper()}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

                st.markdown(f"**Entreprise :** {nom_entreprise} | **Rédacteur :** {nom_redacteur}")
                st.markdown("---")
                st.markdown(texte_structure)

                # Génération du PDF
                pdf_bytes = generer_pdf(
                    nom_entreprise, 
                    nom_redacteur, 
                    email_redacteur, 
                    gravite_detectee, 
                    titre_rapport, 
                    texte_structure
                )

                # Envoi de l'e-mail
                sujet_mail = f"[{gravite_detectee}] {titre_rapport} - {nom_entreprise}"
                corps_mail = f"Bonjour,\n\nVeuillez trouver ci-joint le rapport '{titre_rapport}' rédigé par {nom_redacteur} ({nom_entreprise}).\n\nGravité évaluée par l'IA : {cfg_g['label']}\n\nCordialement,"
                nom_fichier_pdf = f"Rapport_{titre_rapport.replace(' ', '_')}.pdf"

                succes, message_mail = envoyer_email_rapport(
                    email_destinataire_final,
                    sujet_mail,
                    corps_mail,
                    pdf_bytes,
                    nom_fichier_pdf
                )

                if succes:
                    st.success(f"✅ {message_mail} (Envoyé automatiquement à {email_destinataire_final})")
                else:
                    st.error(f"❌ {message_mail}")

                st.download_button(
                    label="📥 Télécharger la copie PDF sur cet appareil",
                    data=pdf_bytes,
                    file_name=nom_fichier_pdf,
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Erreur lors du traitement : {e}")
