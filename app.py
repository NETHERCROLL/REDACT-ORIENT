import io
import streamlit as st
from groq import Groq
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Page Configuration
st.set_page_config(page_title="Logiciel de Gestion de Rapports IA (Groq)", page_icon="📋", layout="wide")

# ==========================================
# 1. INITIALISATION DES SESSIONS & HISTORIQUE
# ==========================================
if "historique_rapports" not in st.session_state:
    st.session_state["historique_rapports"] = {}

if "email_defaut" not in st.session_state:
    st.session_state["email_defaut"] = ""

# Configuration du client Groq API
if "GROQ_API_KEY" in st.secrets:
    client_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])
else:
    st.error("Veuillez configurer la clé GROQ_API_KEY dans vos secrets Streamlit (`.streamlit/secrets.toml`).")
    st.stop()

# Nom du modèle spécifié
GROQ_MODEL = "openai/gpt-oss-20b"

# ==========================================
# 2. CONFIGURATION PREMIÈRE UTILISATION (EMAIL)
# ==========================================
st.sidebar.title("⚙️ Configuration Logiciel")

if not st.session_state["email_defaut"]:
    st.sidebar.warning("⚠️ Configuration initiale requise")
    email_input = st.sidebar.text_input("Adresse e-mail par défaut pour l'envoi des rapports :")
    if st.sidebar.button("Enregistrer l'adresse par défaut"):
        if "@" in email_input and "." in email_input:
            st.session_state["email_defaut"] = email_input.strip()
            st.sidebar.success("Adresse par défaut enregistrée !")
            st.rerun()
        else:
            st.sidebar.error("Veuillez entrer une adresse e-mail valide.")
else:
    st.sidebar.info(f"📧 E-mail par défaut : **{st.session_state['email_defaut']}**")
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
st.caption(f"Moteur IA : **Groq ({GROQ_MODEL})**")

# ==========================================
# 3. FORMULAIRE ET DONNÉES ENTRANTES
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
    
    # Choix Nouveau / Ancien Rapport
    mode_rapport = st.radio("Type de transmission / Action :", ["Nouveau rapport", "Modifier un ancien rapport (Mise à jour)"])

    rapport_existant_cle = None
    contenu_ancien = ""
    if mode_rapport == "Modifier un ancien rapport (Mise à jour)":
        if not st.session_state["historique_rapports"]:
            st.warning("Aucun rapport sauvegardé dans l'historique pour le moment.")
        else:
            rapport_existant_cle = st.selectbox(
                "Sélectionnez le rapport à mettre à jour :", 
                list(st.session_state["historique_rapports"].keys())
            )
            contenu_ancien = st.session_state["historique_rapports"][rapport_existant_cle]["texte"]
            st.info("Le contenu existant sera conservé et l'IA y ajoutera les nouvelles informations.")

st.markdown("---")
st.subheader("3. Contenu et Destinataire")

titre_rapport = st.text_input("Titre du rapport * :", placeholder="ex: Rapport d'inspection du chantier Nord")

notes_brutes = st.text_area(
    "Informations et faits à inclure dans le rapport * :", 
    height=150, 
    placeholder="Entrez ici les faits, observations, chiffres ou anomalies constatés. L'IA les classera sous de grands titres sans rien inventer."
)

# Gestion du Destinataire E-mail
st.subheader("📬 Destinataire du rapport")
liste_destinataires = ["E-mail par défaut", "Saisir un autre destinataire"]
choix_destinataire = st.radio("Sélection du destinataire :", liste_destinataires, horizontal=True)

if choix_destinataire == "E-mail par défaut":
    email_destinataire_final = st.session_state["email_defaut"] if st.session_state["email_defaut"] else "Non configuré"
    st.text(f"Envoyé à : {email_destinataire_final}")
else:
    email_destinataire_final = st.text_input("Saisissez l'adresse e-mail du destinataire spécifique :")

# ==========================================
# 4. MOTEUR DE GÉNÉRATION PDF (REPORTLAB)
# ==========================================
def generer_pdf(entreprise, redacteur, email_red, gravite_key, titre, contenu):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    cfg_g = GRAVITE_CONFIG[gravite_key]

    # --- 1. BALISE DE GRAVITÉ (LA PREMIÈRE CHOSE QU'ON VOIT) ---
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

    # --- 2. INFORMATIONS RÉDACTEUR & ENTREPRISE (JUSTE APRÈS LA BALISE) ---
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

    # --- 3. TITRE DU RAPPORT ---
    title_style = ParagraphStyle(
        'TitreStyle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=12
    )
    story.append(Paragraph(titre.upper(), title_style))
    story.append(Spacer(1, 10))

    # --- 4. CORPS DU RAPPORT (GRANDS TITRES PAR L'IA) ---
    h2_style = ParagraphStyle(
        'H2Style',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        spaceAfter=6
    )

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
    return buffer

# ==========================================
# 5. TRAITEMENT ET GÉNÉRATION VIA GROQ API
# ==========================================
if st.button("🚀 Générer et Enregistrer le Rapport"):
    if not st.session_state["email_defaut"] and choix_destinataire == "E-mail par défaut":
        st.error("Veuillez d'abord enregistrer un e-mail par défaut dans la barre latérale.")
    elif not nom_entreprise or not nom_redacteur or not titre_rapport or not notes_brutes:
        st.warning("Veuillez remplir tous les champs obligatoires (*).")
    else:
        with st.spinner(f"Analyse et structuration du rapport via Groq ({GROQ_MODEL})..."):
            
            # Directives strictes : Grands titres, aucune hallucination
            if mode_rapport == "Modifier un ancien rapport (Mise à jour)" and contenu_ancien:
                prompt_system = "Tu es un assistant strict de rédaction de rapports professionnels."
                prompt_user = f"""
                CONSIGNE ABSOLUE : Ne rajoute AUCUNE information qui n'est pas présente dans les notes fournies. N'invente aucun fait, chiffre ou détail.

                Voici le rapport existant :
                ---
                {contenu_ancien}
                ---

                Voici les NOUVELLES INFORMATIONS à intégrer :
                ---
                {notes_brutes}
                ---

                Tâche : Rédige le rapport mis à jour. Conserve la structure existante, intègre les nouvelles informations sous des grands titres pertinents (ex: # 1. CONTEXTE, # 2. FAITS OBSERVÉS, # 3. MISES À JOUR ET NOUVEAUX ÉLÉMENTS). Utilise le symbole '#' pour marquer chaque grand titre.
                """
            else:
                prompt_system = "Tu es un assistant strict de rédaction de rapports professionnels."
                prompt_user = f"""
                CONSIGNE ABSOLUE : Ne rajoute AUCUNE information qui n'est pas présente dans les notes fournies. N'invente aucun fait, chiffre ou détail.

                Informations brutes fournies par l'utilisateur :
                ---
                {notes_brutes}
                ---

                Tâche : Organise l'ensemble de ces informations de manière claire et professionnelle en les classant sous de GRANDS TITRES (ex: # 1. RÉSUMÉ DES FAITS, # 2. OBSERVATIONS DÉTAILLÉES, # 3. ACTIONS RECOMMANDÉES).
                Utilise le symbole '#' pour marquer chaque grand titre.
                """

            try:
                # Appel API Groq
                completion = client_groq.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": prompt_system},
                        {"role": "user", "content": prompt_user}
                    ],
                    temperature=0.2 # Faible température pour éviter toute invention
                )
                
                texte_structure = completion.choices[0].message.content

                # Sauvegarde dans l'historique
                st.session_state["historique_rapports"][titre_rapport] = {
                    "entreprise": nom_entreprise,
                    "redacteur": nom_redacteur,
                    "gravite": gravite_selectionne,
                    "texte": texte_structure
                }

                # Affichage écran
                st.success("Rapport généré et sauvegardé dans l'historique !")
                
                # --- APERÇU VISUEL ---
                cfg_g = GRAVITE_CONFIG[gravite_selectionne]
                st.markdown(
                    f"<div style='background-color: {cfg_g['color']}; color: white; padding: 12px; border-radius: 6px; text-align: center; font-size: 18px; font-weight: bold; margin-bottom: 10px;'>"
                    f"{cfg_g['emoji']} GRAVITÉ : {cfg_g['label']}"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
                st.markdown(f"**Entreprise :** {nom_entreprise} | **Rédacteur :** {nom_redacteur} " + (f"({email_redacteur})" if email_redacteur else ""))
                st.markdown("---")
                st.markdown(texte_structure)

                # Génération du PDF
                pdf_bytes = generer_pdf(
                    nom_entreprise, 
                    nom_redacteur, 
                    email_redacteur, 
                    gravite_selectionne, 
                    titre_rapport, 
                    texte_structure
                )

                col_dl, col_mail = st.columns(2)
                
                with col_dl:
                    st.download_button(
                        label="📥 Télécharger le Rapport en PDF",
                        data=pdf_bytes,
                        file_name=f"Rapport_{titre_rapport.replace(' ', '_')}.pdf",
                        mime="application/pdf"
                    )

                with col_mail:
                    st.info(f"📬 Prêt pour envoi à : **{email_destinataire_final}**")

            except Exception as e:
                st.error(f"Erreur lors de l'appel à l'API Groq : {e}")