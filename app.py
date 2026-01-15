import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Hukuk AI | Profesyonel Mevzuat Paneli",
    page_icon="⚖️",
    layout="wide"
)

# --- 2. PROFESSIONAL NAVY & GREY THEME ---
# Using a cleaner approach to avoid the markdown syntax error
st.markdown("""
    <style>
    /* Main Background: Light Grey */
    .stApp {
        background-color: #F5F5F5;
    }
    
    /* Sidebar: Navy Blue */
    [data-testid="stSidebar"] {
        background-color: #1B263B !important;
    }
    
    /* Sidebar Text: Light Grey for readability */
    [data-testid="stSidebar"] .stMarkdown p, 
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 {
        color: #E0E0E0 !important;
    }

    /* Titles */
    h1 {
        color: #1B263B;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
    }

    /* Assistant Chat Bubble: Blue-Grey tint */
    [data-testid="stChatMessage"]:nth-child(even) {
        background-color: #E2E8F0 !important;
        border-left: 5px solid #1B263B !important;
        border-radius: 10px;
    }
    
    /* User Chat Bubble: Clean White */
    [data-testid="stChatMessage"]:nth-child(odd) {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D5DB;
        border-radius: 10px;
    }

    /* Buttons */
    .stButton>button {
        background-color: #1B263B;
        color: white;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_stdio=True)

# --- 3. CONNECTION SETUP ---
# Ensure these keys are set in your Streamlit Secrets or Environment Variables
try:
    W_URL = st.secrets["WEAVIATE_URL"]
    W_API = st.secrets["WEAVIATE_API_KEY"]
    O_API = st.secrets["OPENAI_API_KEY"]
except KeyError as e:
    st.error(f"Secret Key Eksik: {e}. Lütfen .streamlit/secrets.toml dosyasını kontrol edin.")
    st.stop()

ai_client = OpenAI(api_key=O_API)

@st.cache_resource
def get_weaviate_client():
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=W_URL,
        auth_credentials=weaviate.auth.AuthApiKey(W_API),
        headers={"X-OpenAI-Api-Key": O_API}
    )

client = get_weaviate_client()

# --- 4. SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.markdown("## ⚖️ Hukuk Kontrol Paneli")
    st.divider()
    
    # Connection Status
    if client.is_ready():
        st.success("Sistem Çevrimiçi")
    else:
        st.error("Veritabanı Bağlantısı Yok")
    
    st.divider()
    st.info("Bu sistem, yüklenen hukuk dökümanları üzerinden 'Hybrid Search' yaparak analiz üretir.")

    # Export Chat Feature
    if "messages" in st.session_state and len(st.session_state.messages) > 0:
        chat_history = ""
        for m in st.session_state.messages:
            chat_history += f"{m['role'].upper()}: {m['content']}\n\n"
        
        st.download_button(
            label="📄 Sohbeti Rapor Olarak İndir",
            data=chat_history,
            file_name="hukuk_analiz_raporu.txt",
            mime="text/plain",
            use_container_width=True
        )

    if st.button("Sohbet Geçmişini Sil", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- 5. CHAT INTERFACE ---
st.title("⚖️ Profesyonel Hukuk Danışmanı")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Show previous messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input Logic
if prompt := st.chat_input("Sorunuzu buraya yazın (Örn: İş kanunu tazminat süreleri...)"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate Response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        with st.spinner("İlgili mevzuat taranıyor..."):
            # A. VECTOR RETRIEVAL (The "Brain")
            collection = client.collections.get("HukukDoc")
            search_results = collection.query.hybrid(
                query=prompt, 
                limit=4, 
                alpha=0.5 # Balance between vector (meaning) and keyword matching
            )
            
            context = ""
            source_list = []
            for obj in search_results.objects:
                s_meta = f"{obj.properties['filename']} (Sayfa {obj.properties['page_number']})"
                source_list.append(s_meta)
                context += f"\n--- KAYNAK: {s_meta} ---\n{obj.properties['content']}\n"

            # B. SYSTEM PROMPT
            messages = [
                {
                    "role": "system", 
                    "content": "Sen kıdemli bir avukat ve hukuk müşavirisin. "
                               "Sana verilen döküman parçalarını kullanarak profesyonel, "
                               "mantıklı ve kesin cevaplar ver. "
                               "Cevaplarında önemli maddeleri **kalın** yaz ve liste kullan. "
                               "Dökümanda olmayan bilgiyi uydurma."
                },
                {"role": "user", "content": f"Bağlam:\n{context}\n\nSoru: {prompt}"}
            ]

            # C. STREAMING RESPONSE
            stream = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)

            # D. SOURCE CITATIONS
            if source_list:
                with st.expander("📍 Kullanılan Referanslar"):
                    for s in sorted(list(set(source_list))):
                        st.markdown(f"• {s}")

    # Add to session state
    st.session_state.messages.append({"role": "assistant", "content": full_response})
