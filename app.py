import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI
import time

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Hukuk AI | Profesyonel Panel", 
    page_icon="⚖️", 
    layout="wide"
)

# --- GRİ VE LACİVERT TEMA (CUSTOM CSS) ---
st.markdown("""
    <style>
    /* Ana Arkaplan */
    .stApp {
        background-color: #F5F5F5; /* Açık Gri */
    }
    
    /* Yan Menü (Sidebar) */
    [data-testid="stSidebar"] {
        background-color: #1B263B; /* Koyu Lacivert */
        color: white;
    }
    
    /* Sidebar Metinleri */
    [data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] h3 {
        color: #E0E0E0 !important;
    }

    /* Chat Mesaj Kutuları */
    .stChatMessage {
        border-radius: 12px;
        border: 1px solid #D1D5DB;
    }
    
    /* Asistan Mesajı (Lacivert Tonlu) */
    [data-testid="stChatMessage"]:nth-child(even) {
        background-color: #E2E8F0; /* Hafif Mavi-Gri */
        border-left: 5px solid #1B263B; /* Lacivert vurgu */
    }

    /* Başlık ve Butonlar */
    h1 {
        color: #1B263B;
        font-family: 'Georgia', serif;
    }
    
    .stButton>button {
        background-color: #1B263B;
        color: white;
        border-radius: 8px;
        border: none;
    }
    
    .stButton>button:hover {
        background-color: #415A77;
        color: white;
    }
    </style>
    """, unsafe_allow_stdio=True)

# --- CREDENTIALS & CLIENTS ---
W_URL = st.secrets["WEAVIATE_URL"]
W_API = st.secrets["WEAVIATE_API_KEY"]
O_API = st.secrets["OPENAI_API_KEY"]

ai_client = OpenAI(api_key=O_API)

@st.cache_resource
def get_weaviate_client():
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=W_URL,
        auth_credentials=weaviate.auth.AuthApiKey(W_API),
        headers={"X-OpenAI-Api-Key": O_API}
    )

client = get_weaviate_client()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### ⚖️ Hukuk Asistanı v2.0")
    st.write("Profesyonel Mevzuat Tarama Sistemi")
    st.divider()
    
    # Durum Göstergesi
    st.caption("SİSTEM DURUMU")
    st.success("Veritabanı Aktif" if client.is_ready() else "Bağlantı Kesildi")
    
    st.divider()
    
    # Sohbeti İndir Özelliği
    if "messages" in st.session_state and len(st.session_state.messages) > 0:
        chat_text = ""
        for m in st.session_state.messages:
            chat_text += f"{m['role'].upper()}: {m['content']}\n\n"
        
        st.download_button(
            label="📄 Sohbeti TXT Olarak İndir",
            data=chat_text,
            file_name="hukuk_danismanlik_notlari.txt",
            mime="text/plain",
            use_container_width=True
        )

    if st.button("Sohbeti Sıfırla", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- ANA EKRAN ---
st.title("⚖️ Mevzuat ve Döküman Analizi")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Mesaj Geçmişi
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Kullanıcı Girişi
if prompt := st.chat_input("Hukuki dökümanlarda ara..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        with st.spinner("İlgili maddeler taranıyor..."):
            # 1. VERİ GETİRME
            collection = client.collections.get("HukukDoc")
            response = collection.query.hybrid(query=prompt, limit=5, alpha=0.5)
            
            context = ""
            sources = []
            for obj in response.objects:
                info = f"{obj.properties['filename']} (S. {obj.properties['page_number']})"
                sources.append(info)
                context += f"\n--- {info} ---\n{obj.properties['content']}\n"

            # 2. PROMPT
            messages = [
                {"role": "system", "content": "Sen kıdemli bir avukatsın. Gri ve ağırbaşlı bir üslup kullan. Sadece sağlanan bağlamı kullan."},
                {"role": "user", "content": f"Dökümanlar:\n{context}\n\nSoru: {prompt}"}
            ]

            # 3. STREAMING (Akışkan Yanıt)
            stream = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.2,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)

            # 4. REFERANSLAR (LACİVERT KART)
            if sources:
                with st.expander("🔍 İncelenen Kaynak Maddeler"):
                    for s in set(sources):
                        st.markdown(f"**• {s}**")

    st.session_state.messages.append({"role": "assistant", "content": full_response})
