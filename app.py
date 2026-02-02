import streamlit as st
import base64
import os
import requests
from io import BytesIO
from mistralai import Mistral

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="OCR MAnuscript",
    page_icon="📜",
    layout="wide"
)

# --- PROMPT DI SISTEMA (Preso dallo script originale) ---
SYSTEM_PROMPT = """
Sei un esperto paleografo e filologo specializzato in manoscritti antichi.
Il tuo compito è analizzare il testo OCR fornito, che potrebbe contenere errori di lettura o caratteri arcaici.

Esegui le seguenti operazioni:
1. Correggi evidenti errori di scansione (es. caratteri senza senso dovuti a macchie).
2. Mantieni la struttura dei paragrafi e delle righe ove sensato.
3. Se il testo è in italiano antico o latino, correggi solo la punteggiatura e normalizza le 'u'/'v' e le 'i'/'j' secondo l'uso moderno, ma NON tradurre o modernizzare le parole se non richiesto.
4. Restituisci SOLO il testo pulito, senza preamboli o commenti.
"""

# --- FUNZIONI DI SUPPORTO ---

def encode_image_from_bytes(image_bytes, mime_type="image/jpeg"):
    """
    Codifica i byte dell'immagine in base64 per l'API Mistral.
    Adattato da encode_image dello script originale.
    """
    try:
        encoded_string = base64.b64encode(image_bytes).decode('utf-8')
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        st.error(f"Errore encoding immagine: {e}")
        return None

def get_image_from_url(url):
    """Scarica un'immagine da un URL e restituisce byte e mime_type."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('content-type', 'image/jpeg')
        return response.content, content_type
    except Exception as e:
        st.error(f"Errore nel scaricare l'immagine dall'URL: {e}")
        return None, None

def process_single_image(client, image_base64, model_ocr, model_chat):
    """
    Esegue la pipeline OCR + Normalizzazione su una singola immagine.
    Logica derivata da process_manuscripts.
    """
    results = {}
    
    # 1. OCR
    try:
        ocr_response = client.ocr.process(
            model=model_ocr,
            document={
                "type": "image_url",
                "image_url": image_base64
            },
            include_image_base64=False
        )
        if ocr_response.pages:
            results['raw_ocr'] = ocr_response.pages[0].markdown
        else:
            results['error'] = "L'OCR non ha rilevato testo."
            return results
    except Exception as e:
        results['error'] = f"Errore API OCR: {str(e)}"
        return results

    # 2. Normalizzazione
    try:
        chat_response = client.chat.complete(
            model=model_chat,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Ecco il testo grezzo da normalizzare:\n\n{results['raw_ocr']}"}
            ]
        )
        results['normalized'] = chat_response.choices[0].message.content
    except Exception as e:
        results['normalized'] = f"Errore Normalizzazione: {str(e)}"
    
    return results

# --- INTERFACCIA UTENTE (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Configurazione")
    api_key_input = st.text_input("Inserisci Mistral API Key", type="password", help="La tua chiave non viene salvata.")
    
    st.info("I modelli utilizzati sono:\n- OCR: `mistral-ocr-latest`\n- Chat: `mistral-large-latest`")
    
    if st.button("Pulisci Sessione"):
        st.session_state.results = {}
        st.rerun()

# --- INTERFACCIA UTENTE (MAIN) ---
st.title("📜 Mistral Ancient Manuscript OCR")
st.markdown("Carica immagini di manoscritti antichi per ottenere trascrizione e normalizzazione filologica.")

# Gestione dello stato per memorizzare i risultati
if 'results' not in st.session_state:
    st.session_state.results = {}

# Tabs per scegliere il metodo di input
tab1, tab2 = st.tabs(["📤 Carica File", "wf URL Immagine"])

input_data = [] # Lista di tuple (nome, byte, mime_type)

with tab1:
    uploaded_files = st.file_uploader("Trascina qui le immagini (JPG, PNG)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    if uploaded_files:
        for uploaded_file in uploaded_files:
            input_data.append((uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type))

with tab2:
    url_input = st.text_input("Incolla qui l'URL dell'immagine")
    if url_input:
        img_bytes, mime = get_image_from_url(url_input)
        if img_bytes:
            input_data.append(("Immagine da URL", img_bytes, mime))
            st.image(img_bytes, caption="Anteprima URL", width=200)

# Bottone di avvio
start_processing = st.button("🚀 Avvia Analisi", type="primary", disabled=(not input_data))

if start_processing:
    if not api_key_input:
        st.error("Per favore inserisci la tua API Key nella barra laterale.")
    else:
        client = Mistral(api_key=api_key_input)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_files = len(input_data)
        
        for idx, (name, img_bytes, mime) in enumerate(input_data):
            status_text.text(f"Elaborazione di: {name}...")
            
            # Encoding
            base64_img = encode_image_from_bytes(img_bytes, mime)
            
            if base64_img:
                # Processamento
                res = process_single_image(client, base64_img, "mistral-ocr-latest", "mistral-large-latest")
                
                # Salvataggio in session state
                st.session_state.results[name] = res
            
            # Aggiorna barra progresso
            progress_bar.progress((idx + 1) / total_files)
        
        status_text.text("✅ Elaborazione completata!")

# --- VISUALIZZAZIONE RISULTATI ---
if st.session_state.results:
    st.divider()
    st.subheader("Risultati")

    for filename, data in st.session_state.results.items():
        with st.expander(f"📄 {filename}", expanded=True):
            if 'error' in data:
                st.error(data['error'])
                continue
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 👁️ OCR Grezzo")
                st.text_area("Testo rilevato", value=data.get('raw_ocr', ''), height=300, key=f"raw_{filename}")
                st.download_button(
                    label="⬇️ Scarica OCR MD",
                    data=data.get('raw_ocr', ''),
                    file_name=f"{filename}_ocr.md",
                    mime="text/markdown"
                )

            with col2:
                st.markdown("### 🧠 Normalizzato")
                st.text_area("Testo corretto", value=data.get('normalized', ''), height=300, key=f"norm_{filename}")
                st.download_button(
                    label="⬇️ Scarica Norm MD",
                    data=data.get('normalized', ''),
                    file_name=f"{filename}_norm.md",
                    mime="text/markdown"
                )