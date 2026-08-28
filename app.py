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

# Page Configuration
st.set_page_config(page_title="Logiciel de Gestion de Rapports IA", page_icon="📋", layout="wide")

# ==========================================
# 1. INITIALISATION DES SESSIONS & HISTORIQUE
# ==========================================
if "historique_rapports" not in st.session_state:
    st.session_state["historique_rapports"] = {}

if "email_defaut" not in st.session_state:
    st.session_state["email_defaut"] = ""

# Clé API Groq
if "GROQ_API_KEY" in st.secrets:
    client_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])
else:
    st.error("Veuillez configurer la clé GROQ_API_KEY dans vos secrets Streamlit (`.streamlit/secrets.toml`).")
    st.stop()

GROQ_MODEL = "openai/gpt-oss-20b"

# ==========================================
# 2. CONFIGURATION SMTP (EXPÉDITEUR E-MAIL)
# ==========================================
# Récupération des secrets SMTP s'ils existent
SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", 587))
SMTP_EMAIL = st.secrets.get("SMTP_EMAIL", "")
SMTP_PASSWORD = st.secrets.get("SMTP_PASSWORD", "")

st.sidebar.title("⚙️ Configuration E-mail")

# Configuration de l'adresse par défaut destinataire
if not st.session_state["email_defaut"]:
    st.sidebar.warning("⚠️ E-mail destinataire par défaut requis")
    email_input = st.sidebar.text_input("Adresse e-mail destinataire par défaut :")
    if st.sidebar.button("Enregistrer l'adresse par défaut"):
        if "@" in email_input and "." in email_input:
            st.session_state["email_defaut"] = email_input.strip()
            st.sidebar.success("Adresse par défaut enregistrée !")
            st.rerun()
        else:
            st.sidebar.error("Veuillez entrer une adresse e-mail valide.")
else:
    st.sidebar.info(f"📧 Destinataire par défaut : **{st.session_state['email_defaut']}**")
    if st.sidebar.button("Modifier l'e-mail par défaut"):
        st.session_state["email_defaut"] = ""
        st.rerun()

# Config des balises de gravité
GRAVITE_CONFIG = {
    "VERT (Tout va bien)": {
        "color": "#16A34A", 
        "bg_pdf": colors.HexColor("#16A34A"), 
        "label": "SITUATION NORMALE / TOUT VA BIEN", 
        "emoji": "🟢"
    },
    "JAUNE (Gravité mineure)": {
        "color": "#D97706", 
        "bg_pdf": colors.HexColor("#D97706"), 
        "label": "ATTENTION / GRAVITÉ MINEURE", 
        "emoji": "🟡"
    },
    "ROUGE (Gravité majeure)": {
        "color": "#DC2626", 
        "bg_pdf": colors.HexColor("#DC2626"), 
        "label": "ALERTE / GRAVITÉ MAJEURE", 
        "emoji": "🔴"
    }
}

st.title("📋 Logiciel Professionnel de Rédaction de Rapports")

# ==========================================
# 3. FONCTION D'ENVOI REEL DE L'E-MAIL
# ==========================================
def envoyer_email_rapport(destinataire, sujet, corps, pdf_data, pdf_filename):
    """Envoie un e-mail réel avec le PDF en pièce jointe via SMTP."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return False, "Les identifiants d'expédition SMTP (SMTP_EMAIL et SMTP_PASSWORD) ne sont pas configurés dans secrets.toml."
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = destinataire
        msg['Subject'] = sujet

        # Corps du message
        msg.attach(MIMEText(corps, 'plain'))

        # Pièce jointe PDF
        part = MIMEApplication(pdf_data, Name=pdf_filename)
        part['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
        msg.attach(part)

        # Connexion au serveur SMTP et envoi
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
    st.subheader("2. Paramètres & Transmission")
    gravite_selectionne = st.selectbox("Niveau de gravité du rapport * :", list(GRAVITE_CONFIG.keys()))
    
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
            st.info("L'IA ajoutera les nouvelles informations dans l'ancien rapport.")

st.markdown("---")
st.subheader("3. Contenu et Destinataire")

titre_rapport = st.text_input("Titre du rapport * :", placeholder="ex: Rapport d'inspection du chantier Nord")

notes_brutes = st.text_area(
    "Informations et faits à inclure dans le rapport * :", 
    height=150, 
    placeholder="Entrez ici les faits bruts. L'IA les classera sous de grands titres sans rien inventer."
)

# Destinataire E-mail
st.subheader("📬 Destinataire de l'envoi")
choix_destinataire = st.radio("Sélection du destinataire :", ["E-mail par défaut", "Saisir un autre destinataire"], horizontal=True)

if choix_destinataire == "E-mail par défaut":
    email_destinataire_final = st.session_state["email_defaut"]
    st.write(f"Directement envoyé à : **{email_destinataire_final if email_destinataire_final else 'Non configuré'}**")
else:
    email_destinataire_final = st.text_input("Saisissez l'adresse e-mail du destinataire :")

# ==========================================
# 5. GÉNÉRATION PDF (REPORTLAB)
# ==========================================
def generer_pdf(entreprise, redacteur, email_red, gravite_key, titre, contenu):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    cfg_g = GRAVITE_CONFIG[gravite_key]

    # Balise de gravité
    banner_data = [[Paragraph(f"<font color='white' size=14><b>{cfg_g['emoji']} GRAVITÉ : {cfg_g['label']}</b></font>", styles['Normal'])]]
    t_banner = Table(banner_data, colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), cfg_g['bg_pdf']),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 12))

    # Émetteur
    meta_text = f"<b>Entreprise :</b> {entreprise}<br/><b>Rédacteur :</b> {redacteur}"
    if email_red:
        meta_text += f"<br/><b>E-mail :</b> {email_red}"
        
    meta_data = [[Paragraph(meta_text, styles['Normal'])]]
    t_meta = Table(meta_data, colWidths=[540])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1"))
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 15))

    # Titre
    title_style = ParagraphStyle('TitreStyle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor("#1E293B"), spaceAfter=12)
    story.append(Paragraph(titre.upper(), title_style))
    story.append(Spacer(1, 10))

    # Corps
    h2_style = ParagraphStyle('H2Style', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor("#0F172A"), spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6)

    for line in contenu.split('\n'):
        line_str = line.strip()
        if line_str.startswith("#"):
            clean_head = line_str.replace("#", "").strip()
            story.append(Paragraph(f"<b>{clean_head}</b>", h2_style))
        elif line_str:
            story.append(Paragraph(line_str, body_style))
        else:
            story.append(Spacer(1, 4))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ==========================================
# 6. EXÉCUTION & ENVOI REEL
# ==========================================
if st.button("🚀 Générer et Envoyer le Rapport"):
    if not email_destinataire_final:
        st.error("Veuillez renseigner un destinataire e-mail valide.")
    elif not nom_entreprise or not nom_redacteur or not titre_rapport or not notes_brutes:
        st.warning("Veuillez remplir tous les champs obligatoires (*).")
    else:
        with st.spinner(f"Rédaction par l'IA (Groq) et préparation du PDF..."):
            
            if mode_rapport == "Modifier un ancien rapport (Mise à jour)" and contenu_ancien:
                prompt_system = "Tu es un assistant strict de rédaction de rapports."
                prompt_user = f"Consigne : Ne rajoute AUCUNE information inventée.\nExistant :\n{contenu_ancien}\nNouvelles infos :\n{notes_brutes}\nTâche : Intègre sous des grands titres avec '#'."
            else:
                prompt_system = "Tu es un assistant strict de rédaction de rapports."
                prompt_user = f"Consigne : Ne rajoute AUCUNE information inventée.\nInfos :\n{notes_brutes}\nTâche : Organise sous de grands titres avec '#' (ex: # 1. CONTEXTE)."

            try:
                completion = client_groq.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": prompt_system},
                        {"role": "user", "content": prompt_user}
                    ],
                    temperature=0.2
                )
                
                texte_structure = completion.choices[0].message.content

                # Sauvegarde historique
                st.session_state["historique_rapports"][titre_rapport] = {
                    "entreprise": nom_entreprise,
                    "redacteur": nom_redacteur,
                    "gravite": gravite_selectionne,
                    "texte": texte_structure
                }

                # Génération du fichier PDF
                pdf_bytes = generer_pdf(
                    nom_entreprise, 
                    nom_redacteur, 
                    email_redacteur, 
                    gravite_selectionne, 
                    titre_rapport, 
                    texte_structure
                )

                # --- ENVOI DE L'E-MAIL REEL ---
                sujet_mail = f"[{gravite_selectionne.split(' ')[0]}] {titre_rapport} - {nom_entreprise}"
                corps_mail = f"Bonjour,\n\nVeuillez trouver ci-joint le rapport '{titre_rapport}' rédigé par {nom_redacteur} ({nom_entreprise}).\n\nNiveau de gravité : {gravite_selectionne}\n\nCordialement,"
                nom_fichier_pdf = f"Rapport_{titre_rapport.replace(' ', '_')}.pdf"

                succes, message_mail = envoyer_email_rapport(
                    email_destinataire_final,
                    sujet_mail,
                    corps_mail,
                    pdf_bytes,
                    nom_fichier_pdf
                )

                if succes:
                    st.success(f"✅ {message_mail} (Envoyé à {email_destinataire_final})")
                else:
                    st.error(f"❌ Le PDF a été généré mais l'e-mail n'a pas pu être envoyé : {message_mail}")

                # Proposer le téléchargement manuel en alternative
                st.download_button(
                    label="📥 Télécharger aussi le Rapport en PDF sur ce PC",
                    data=pdf_bytes,
                    file_name=nom_fichier_pdf,
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Erreur lors du traitement : {e}")
