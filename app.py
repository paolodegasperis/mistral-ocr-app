import streamlit as st
import base64
import requests
from mistralai import Mistral

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Mistral OCR 3 - Manuscriptor",
    page_icon="📜",
    layout="wide"
)

# --- PROMPT DI SISTEMA ---
SYSTEM_PROMPT = """
Sei un esperto paleografo e filologo specializzato in manoscritti antichi.
Il tuo compito è analizzare il testo OCR fornito, che potrebbe contenere errori di lettura o caratteri arcaici.

Esegui le seguenti operazioni:
1. Correggi evidenti errori di scansione o di encoding.
2. Mantieni rigorosamente la struttura dei paragrafi e la divisione delle pagine se indicata.
3. Se il testo è in italiano antico o latino, correggi solo la punteggiatura e normalizza le 'u'/'v' e le 'i'/'j' secondo l'uso moderno, ma NON tradurre o modernizzare le parole se non richiesto.
4. Restituisci SOLO il testo pulito.
"""

# --- FUNZIONI DI SUPPORTO ---

def encode_file_to_base64(file_bytes, mime_type):
    """
    Codifica i byte del file (immagine o PDF) in base64 per l'API Mistral.
    """
    try:
        encoded_string = base64.b64encode(file_bytes).decode('utf-8')
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        st.error(f"Errore encoding file: {e}")
        return None

def get_file_from_url(url):
    """Scarica un file da un URL e restituisce byte e mime_type."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('content-type', 'application/pdf') # Default to pdf if unknown
        # Correzione comune per header imprecisi
        if url.lower().endswith('.pdf'):
            content_type = 'application/pdf'
        elif url.lower().endswith(('.jpg', '.jpeg')):
            content_type = 'image/jpeg'
        elif url.lower().endswith('.png'):
            content_type = 'image/png'
            
        return response.content, content_type
    except Exception as e:
        st.error(f"Errore nel scaricare il file dall'URL: {e}")
        return None, None

def process_document(client, file_base64, model_ocr, model_chat):
    """
    Esegue OCR su documenti multipagina (PDF) o immagini singole.
    """
    results = {}
    
    # 1. OCR (Mistral OCR 3 supporta nativamente i PDF via base64)
    try:
        ocr_response = client.ocr.process(
            model=model_ocr,
            document={
                "type": "image_url", # Nota: l'API usa 'image_url' anche per i data URL dei PDF
                "image_url": file_base64
            },
            include_image_base64=False
        )
        
        full_markdown = ""
        page_count = len(ocr_response.pages)
        
        if page_count > 0:
            # Iteriamo su tutte le pagine del PDF/Immagine
            for i, page in enumerate(ocr_response.pages):
                header = f"\n\n--- Pagina {i+1} ---\n\n"
                full_markdown += header + page.markdown
            
            results['raw_ocr'] = full_markdown
            results['pages_count'] = page_count
        else:
            results['error'] = "L'OCR ha completato l'analisi ma non ha rilevato testo."
            return results

    except Exception as e:
        results['error'] = f"Errore API OCR: {str(e)}"
        return results

    # 2. Normalizzazione
    # Nota: Se il PDF è enorme (es. 100+ pagine), potresti voler normalizzare pagina per pagina
    # per evitare limiti di contesto. Qui assumiamo manoscritti di lunghezza ragionevole.
    try:
        chat_response = client.chat.complete(
            model=model_chat,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Ecco la trascrizione grezza (composta da {results.get('pages_count', 1)} pagine):\n\n{results['raw_ocr']}"}
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
    
    st.info("Modelli attivi:\n- OCR Engine: `mistral-ocr-latest` (OCR 3)\n- Normalizer: `mistral-large-latest`")
    
    if st.button("Pulisci Sessione"):
        st.session_state.results = {}
        st.rerun()

# --- INTERFACCIA UTENTE (MAIN) ---
st.title("OCR 3 - Trascrizione testi tramite modelli Mistral")
st.markdown("Carica immagini o **PDF completi** di manoscritti antichi per trascrizione e normalizzazione.")

if 'results' not in st.session_state:
    st.session_state.results = {}

tab1, tab2 = st.tabs(["📤 Carica File (Img/PDF)", "🌐 URL File"])

input_data = [] # Lista di tuple (nome, byte, mime_type)

with tab1:
    # Aggiunto 'pdf' ai tipi supportati
    uploaded_files = st.file_uploader("Trascina qui i file", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)
    if uploaded_files:
        for uploaded_file in uploaded_files:
            input_data.append((uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type))

with tab2:
    url_input = st.text_input("Incolla qui l'URL (Immagine o PDF)")
    if url_input:
        file_bytes, mime = get_file_from_url(url_input)
        if file_bytes:
            name_from_url = url_input.split("/")[-1] or "documento_web"
            input_data.append((name_from_url, file_bytes, mime))
            st.success(f"File scaricato: {mime} ({len(file_bytes)/1024:.1f} KB)")

start_processing = st.button("🚀 Avvia Analisi OCR 3", type="primary", disabled=(not input_data))

if start_processing:
    if not api_key_input:
        st.error("Chiave API mancante nella barra laterale.")
    else:
        client = Mistral(api_key=api_key_input)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_files = len(input_data)
        
        for idx, (name, file_bytes, mime) in enumerate(input_data):
            status_text.text(f"Elaborazione OCR 3 su: {name}...")
            
            # Gestione Mime Type corretta per PDF
            if mime == "application/pdf":
                base64_file = encode_file_to_base64(file_bytes, "application/pdf")
            else:
                # Fallback per immagini (o se il mime non è rilevato correttamente)
                base64_file = encode_file_to_base64(file_bytes, mime if mime else "image/jpeg")
            
            if base64_file:
                res = process_document(client, base64_file, "mistral-ocr-latest", "mistral-large-latest")
                st.session_state.results[name] = res
            
            progress_bar.progress((idx + 1) / total_files)
        
        status_text.text("✅ Elaborazione completata!")

# --- VISUALIZZAZIONE RISULTATI ---
if st.session_state.results:
    st.divider()
    st.subheader("Risultati")

    for filename, data in st.session_state.results.items():
        with st.expander(f"📄 {filename} ({data.get('pages_count', 0)} pagine)", expanded=True):
            if 'error' in data:
                st.error(data['error'])
                continue
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 👁️ OCR Grezzo (Unito)")
                st.text_area("Markdown OCR", value=data.get('raw_ocr', ''), height=400, key=f"raw_{filename}")
                st.download_button(
                    label="⬇️ Scarica OCR Completo",
                    data=data.get('raw_ocr', ''),
                    file_name=f"{filename}_ocr_full.md",
                    mime="text/markdown"
                )

            with col2:
                st.markdown("### 🧠 Normalizzazione")
                st.text_area("Testo Normalizzato", value=data.get('normalized', ''), height=400, key=f"norm_{filename}")
                st.download_button(
                    label="⬇️ Scarica Norm. Completa",
                    data=data.get('normalized', ''),
                    file_name=f"{filename}_norm_full.md",
                    mime="text/markdown"
                )