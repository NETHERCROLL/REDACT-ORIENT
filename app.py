import io
import json
import os
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from groq import Groq
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from streamlit_drawable_canvas import st_canvas
from streamlit_js_eval import get_geolocation
from streamlit_local_storage import LocalStorage

st.set_page_config(page_title="Gestionnaire de Rapports - Transport & Flotte", page_icon="🚛", layout="wide")
local_storage = LocalStorage()
HISTORIQUE_FILE = "historique.json"

@st.cache_data
def charger_historique_cache(mtime):
    if os.path.exists(HISTORIQUE_FILE):
        try:
            with open(HISTORIQUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def charger_historique():
    mtime = os.path.getmtime(HISTORIQUE_FILE) if os.path.exists(HISTORIQUE_FILE) else 0
    return charger_historique_cache(mtime)

def sauvegarder_historique(historique):
    try:
        with open(HISTORIQUE_FILE, "w", encoding="utf-8") as f:
            json.dump(historique, f, ensure_ascii=False, indent=4)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erreur sauvegarde : {e}")

if "historique_rapports" not in st.session_state:
    st.session_state["historique_rapports"] = charger_historique()

if "GROQ_API_KEY" in st.secrets:
    client_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])
else:
    st.error("Veuillez configurer la clé GROQ_API_KEY dans vos secrets Streamlit (`.streamlit/secrets.toml`).")
    st.stop()

GROQ_MODEL = "openai/gpt-oss-20b"
SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", 587))
SMTP_EMAIL = st.secrets.get("SMTP_EMAIL", "")
SMTP_PASSWORD = st.secrets.get("SMTP_PASSWORD", "")
WEBHOOK_URL = st.secrets.get("WEBHOOK_URL", "")

st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;} .stAppDeployButton {display:none;} div[data-testid="stStatusWidget"] {visibility: hidden;}</style>""", unsafe_allow_html=True)

GRAVITE_CONFIG = {
    "VERT": {"color": "#16A34A", "bg_pdf": colors.HexColor("#16A34A"), "label": "Faible / Routine"},
    "JAUNE": {"color": "#D97706", "bg_pdf": colors.HexColor("#D97706"), "label": "Moyenne / Incidents & Retards"},
    "ROUGE": {"color": "#DC2626", "bg_pdf": colors.HexColor("#DC2626"), "label": "Élevée / Urgence / Panne & Accident"}
}

def envoyer_email_rapport(destinataire, sujet, corps, pdf_data, pdf_filename):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return False, "Identifiants SMTP d'expédition absents."
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
        return False, f"Erreur e-mail : {str(e)}"

def envoyer_alerte_webhook(titre, vehicule, conducteur, gravite, message):
    if not WEBHOOK_URL:
        return
    payload = {"titre": titre, "vehicule": vehicule, "conducteur": conducteur, "gravite": gravite, "message": message, "date": datetime.now().isoformat()}
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        pass

def generer_pdf(entreprise, redacteur, email_red, vehicule, km, conducteur, ligne, gravite_key, titre, contenu, gps_coords, signature_buf):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()
    cfg_g = GRAVITE_CONFIG.get(gravite_key, GRAVITE_CONFIG["VERT"])
    cercle_html = f"<font color='{cfg_g['color']}' size=18><b>●</b></font> <font color='#334155' size=11><b>NIVEAU DE GRAVITÉ : {cfg_g['label'].upper()}</b></font>"
    story.append(Paragraph(cercle_html, styles['Normal']))
    story.append(Spacer(1, 8))
    meta_text = f"<b>Entreprise :</b> {entreprise} | <b>Rédacteur :</b> {redacteur} ({email_red})<br/><b>Véhicule :</b> {vehicule} | <b>Kilométrage :</b> {km} km<br/><b>Conducteur :</b> {conducteur} | <b>Ligne/Lieu :</b> {ligne}"
    if gps_coords:
        meta_text += f"<br/><b>Position GPS :</b> {gps_coords}"
    meta_data = [[Paragraph(meta_text, styles['Normal'])]]
    t_meta = Table(meta_data, colWidths=[540])
    t_meta.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")), ('PADDING', (0,0), (-1,-1), 8), ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1"))]))
    story.append(t_meta)
    story.append(Spacer(1, 12))
    title_style = ParagraphStyle('TitreStyle', parent=styles['Heading1'], fontSize=14, leading=18, textColor=colors.HexColor("#0F172A"), spaceAfter=10)
    story.append(Paragraph(titre.upper(), title_style))
    story.append(Spacer(1, 6))
    h2_style = ParagraphStyle('H2Style', parent=styles['Heading2'], fontSize=11, leading=14, textColor=colors.HexColor("#1E293B"), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=9.5, leading=13, spaceAfter=4)
    for line in contenu.split('\n'):
        line_str = line.strip()
        if line_str.startswith("#"):
            clean_head = line_str.replace("#", "").strip()
            story.append(Paragraph(f"<b>{clean_head}</b>", h2_style))
        elif line_str:
            story.append(Paragraph(line_str, body_style))
        else:
            story.append(Spacer(1, 2))
    if signature_buf:
        story.append(Spacer(1, 15))
        story.append(Paragraph("<b>Signature numérique de validation :</b>", body_style))
        story.append(Spacer(1, 5))
        img = RLImage(signature_buf, width=150, height=60)
        story.append(img)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

st.sidebar.title("🚛 Transport Manager")
page = st.sidebar.radio("Navigation :", ["📝 Nouveau Rapport", "📊 Tableau de Bord Flotte", "⚙️ Paramètres"])

if page == "⚙️ Paramètres":
    st.header("⚙️ Configuration de l'appareil")
    email_actuel = local_storage.getItem("email_defaut_utilisateur")
    if not email_actuel:
        st.warning("⚠️ Aucun e-mail par défaut sur cet appareil")
        email_input = st.text_input("Adresse e-mail par défaut :")
        if st.button("Enregistrer sur cet appareil"):
            if "@" in email_input and "." in email_input:
                local_storage.setItem("email_defaut_utilisateur", email_input.strip())
                st.success("Enregistré !")
                st.rerun()
            else:
                st.error("E-mail invalide.")
    else:
        st.info(f"📱 E-mail par défaut : **{email_actuel}**")
        if st.button("Changer l'e-mail"):
            local_storage.deleteItem("email_defaut_utilisateur")
            st.rerun()
    st.markdown("---")
    nbr_rapports = len(st.session_state["historique_rapports"])
    st.write(f"Rapports enregistrés : **{nbr_rapports}**")
    if nbr_rapports > 0 and st.button("🗑️ Effacer tout l'historique"):
        st.session_state["historique_rapports"] = {}
        sauvegarder_historique({})
        st.success("Historique effacé.")
        st.rerun()

elif page == "📊 Tableau de Bord Flotte":
    st.title("📊 Statistiques et Suivi d'Exploitation")
    data = list(st.session_state["historique_rapports"].values())
    if not data:
        st.info("Aucune donnée enregistrée dans l'historique.")
    else:
        df = pd.DataFrame(data)
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Rapports", len(df))
        col2.metric("Incapacité / Urgence (ROUGE)", len(df[df['gravite'] == 'ROUGE']))
        col3.metric("Anomalies (JAUNE)", len(df[df['gravite'] == 'JAUNE']))
        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("Répartition par Niveau de Gravité")
            fig1 = px.pie(df, names='gravite', color='gravite', color_discrete_map={'VERT': '#16A34A', 'JAUNE': '#D97706', 'ROUGE': '#DC2626'})
            st.plotly_chart(fig1, use_container_width=True)
        with col_chart2:
            st.subheader("Incidents par Véhicule / Immatriculation")
            if 'vehicule' in df.columns:
                fig2 = px.bar(df['vehicule'].value_counts().reset_index(), x='vehicule', y='count', labels={'vehicule': 'Véhicule', 'count': 'Nb Rapports'})
                st.plotly_chart(fig2, use_container_width=True)

elif page == "📝 Nouveau Rapport":
    st.title("📋 Rapport d'Exploitation Transport")
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("1. Informations Émetteur & Flotte")
        nom_entreprise = st.text_input("Société / Agence * :", placeholder="ex: Transport Express SA")
        nom_redacteur = st.text_input("Rédacteur / Chef d'équipe * :", placeholder="ex: Paul Martin")
        email_redacteur = st.text_input("E-mail du rédacteur :")
        immatriculation = st.text_input("Immatriculation / N° Parc Véhicule * :", placeholder="ex: AB-123-CD / Bus #304")
        km_actuel = st.number_input("Kilométrage actuel :", min_value=0, step=100)
    with col_r:
        st.subheader("2. Mission & Métadonnées")
        nom_conducteur = st.text_input("Nom du Conducteur / Chauffeur * :", placeholder="ex: Jean Dupont")
        ligne_trajet = st.text_input("Ligne / Trajet / Zone * :", placeholder="ex: Ligne Express A - Entrepôt Nord")
        type_evenement = st.selectbox("Type d'incident principal :", ["Routine / Contrôle de passage", "Panne mécanique / Immobilisation", "Accident / Accrochage", "Retard important / Infraction trafic", "Anomalie marchandises / Passagers"])
        mode_rapport = st.radio("Option :", ["Nouveau rapport", "Mise à jour d'un ancien rapport"])
        contenu_ancien = ""
        if mode_rapport == "Mise à jour d'un ancien rapport":
            if st.session_state["historique_rapports"]:
                cle_select = st.selectbox("Sélectionner le rapport :", list(st.session_state["historique_rapports"].keys()))
                contenu_ancien = st.session_state["historique_rapports"][cle_select].get("texte", "")
    st.markdown("---")
    st.subheader("3. Géolocalisation & Saisie des Faits")
    loc_col1, loc_col2 = st.columns([1, 2])
    gps_str = ""
    with loc_col1:
        if st.button("📍 Capturer Position GPS"):
            loc = get_geolocation()
            if loc and 'coords' in loc:
                gps_str = f"Lat: {loc['coords']['latitude']:.4f}, Lon: {loc['coords']['longitude']:.4f}"
                st.success(f"Capturé : {gps_str}")
    titre_rapport = st.text_input("Titre de l'intervention * :", placeholder="ex: Panne moteur - Autoroute A6")
    notes_brutes = st.text_area("Observations détaillées * :", height=120, placeholder="Décrivez clairement la situation, l'impact sur le trajet, les mesures prises...")
    brouillon_cle = "brouillon_transport_note"
    brouillon_sauve = local_storage.getItem(brouillon_cle)
    if brouillon_sauve and not notes_brutes:
        if st.button("🔄 Restaurer le brouillon hors-ligne"):
            notes_brutes = brouillon_sauve
    if st.button("💾 Sauvegarder en brouillon local"):
        local_storage.setItem(brouillon_cle, notes_brutes)
        st.toast("Brouillon sauvegardé sur cet appareil !")
    st.markdown("---")
    st.subheader("4. Signature numérique & Destinataire")
    sig_col, dest_col = st.columns(2)
    with sig_col:
        st.write("Signature sur écran tactil :")
        canvas_result = st_canvas(fill_color="rgba(255, 255, 255, 0)", stroke_width=2, stroke_color="#000000", background_color="#F8FAFC", height=100, width=280, drawing_mode="freedraw", key="canvas")
    with dest_col:
        choix_dest = st.radio("Destinataire e-mail :", ["E-mail par défaut de l'appareil", "Saisir un e-mail"])
        email_defaut_appareil = local_storage.getItem("email_defaut_utilisateur")
        if choix_dest == "E-mail par défaut de l'appareil":
            email_destinataire_final = email_defaut_appareil if email_defaut_appareil else ""
            if email_destinataire_final:
                st.info(f"Destinataire : **{email_destinataire_final}**")
            else:
                st.error("Aucun e-mail configuré dans les paramètres.")
        else:
            email_destinataire_final = st.text_input("Adresse e-mail destinataire :")
    st.markdown("---")
    if st.button("🚀 Valider, Analyser & Transmettre le Rapport"):
        if not email_destinataire_final or not nom_entreprise or not nom_redacteur or not titre_rapport or not notes_brutes or not immatriculation:
            st.warning("Veuillez remplir tous les champs obligatoires (*).")
        else:
            with st.spinner("Traitement IA Groq et structuration du rapport..."):
                prompt_user = f"""
                TÂCHE 1 : Évalue la gravité (VERT, JAUNE, ROUGE).
                - VERT = Routine, contrôle, situation normale.
                - JAUNE = Retard, anomalie mineure, révision nécessaire sans danger immédiat.
                - ROUGE = Panne critique, immobilisation, accident, urgence sécurité/fret.
                Première ligne : GRAVITE: [VERT ou JAUNE ou ROUGE]
                TÂCHE 2 : Rédige le rapport transport structuré avec titres '#'.
                Contexte : Véhicule {immatriculation}, Chauffeur {nom_conducteur}, Trajet {ligne_trajet}, Type: {type_evenement}.
                Ancien rapport : {contenu_ancien}
                Notes : {notes_brutes}
                """
                try:
                    completion = client_groq.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "system", "content": "Tu es un expert strict en logistique, transport routier et gestion de flotte."}, {"role": "user", "content": prompt_user}],
                        temperature=0.1
                    )
                    reponse_brute = completion.choices[0].message.content
                    gravite_detectee = "VERT"
                    lines = reponse_brute.split("\n")
                    first_line = lines[0].upper()
                    if "GRAVITE:" in first_line or "GRAVITÉ:" in first_line:
                        if "ROUGE" in first_line: gravite_detectee = "ROUGE"
                        elif "JAUNE" in first_line: gravite_detectee = "JAUNE"
                        elif "VERT" in first_line: gravite_detectee = "VERT"
                        texte_structure = "\n".join(lines[1:]).strip()
                    else:
                        texte_structure = reponse_brute.strip()
                    cle_rapport = f"{titre_rapport} ({datetime.now().strftime('%d/%m %H:%M')})"
                    st.session_state["historique_rapports"][cle_rapport] = {
                        "entreprise": nom_entreprise, "redacteur": nom_redacteur, "vehicule": immatriculation,
                        "conducteur": nom_conducteur, "gravite": gravite_detectee, "texte": texte_structure,
                        "date": datetime.now().isoformat()
                    }
                    sauvegarder_historique(st.session_state["historique_rapports"])
                    if gravite_detectee == "ROUGE":
                        envoyer_alerte_webhook(titre_rapport, immatriculation, nom_conducteur, gravite_detectee, notes_brutes)
                    sig_buf = None
                    if canvas_result.image_data is not None:
                        from PIL import Image
                        import numpy as np
                        img_arr = canvas_result.image_data.astype(np.uint8)
                        pil_img = Image.fromarray(img_arr)
                        sig_buf = io.BytesIO()
                        pil_img.save(sig_buf, format='PNG')
                        sig_buf.seek(0)
                    pdf_bytes = generer_pdf(
                        nom_entreprise, nom_redacteur, email_redacteur, immatriculation, km_actuel,
                        nom_conducteur, ligne_trajet, gravite_detectee, titre_rapport, texte_structure, gps_str, sig_buf
                    )
                    sujet_mail = f"[{gravite_detectee}] {titre_rapport} - Véhicule {immatriculation}"
                    corps_mail = f"Rapport transport généré par {nom_redacteur}.\nVéhicule: {immatriculation}\nConducteur: {nom_conducteur}\nGravité IA: {gravite_detectee}"
                    nom_pdf = f"Rapport_Transport_{immatriculation}_{datetime.now().strftime('%Y%m%d')}.pdf"
                    succes, message_mail = envoyer_email_rapport(email_destinataire_final, sujet_mail, corps_mail, pdf_bytes, nom_pdf)
                    if succes:
                        st.success(f"✅ {message_mail}")
                    else:
                        st.error(f"❌ {message_mail}")
                    local_storage.deleteItem(brouillon_cle)
                    st.download_button("📥 Télécharger la copie PDF", data=pdf_bytes, file_name=nom_pdf, mime="application/pdf")
                except Exception as e:
                    st.error(f"Erreur traitement : {e}")
