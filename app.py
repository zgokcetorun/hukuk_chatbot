import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="Hukuk AI | Mevzuat Paneli",
    page_icon="⚖️",
    layout="wide"
)

# --- 2. PROFESYONEL TEMA (GRİ & LACİVERT) ---
# Hata almamak için CSS bloğunu dikkatlice yapılandırdık
st.markdown("""
    <style>
    /* Ana Arkaplan: Açık Gri */
    .stApp {
        background-color: #F8F9FA;
    }
    
    /* Yan Menü: Koyu Lacivert */
    [data-testid="stSidebar"] {
        background-color: #1B263B !important;
    }
    
    /* Yan Menü Yazıları: Beyaz/Gri */
    [data-testid="stSidebar"] .stMarkdown p, 
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 {
        color: #E0E0E0 !important;
    }

    /* Başlıklar */
    h1 {
        color: #1B263B;
        font-family: 'Helvetica', sans-serif;
    }

    /* Asistan Mesaj Kutusu: Mavi-Gri tonu */
    [data-testid="stChatMessage"]:nth-child(even) {
        background-color: #E2E8F0 !important;
        border-left: 5px solid #1B263B !important;
    }
    
    /* Kullanıcı Mesaj Kutusu: Beyaz */
    [data-testid="stChatMessage"]:nth-child(odd) {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D5DB;
    }
    </style>
    """, unsafe_allow_stdio=True)

# --- 3. BAĞLANTI AYARLARI ---
# Secrets kontrolü
try:
    W_URL = st.secrets["WEAVIATE_URL"]
    W_API = st.secrets["WEAVIATE_API_KEY"]
    O_API = st.secrets["OPENAI_API_KEY"]
except KeyError as e:
    st.error(f"Eksik Anahtar: {e}. Lütfen Streamlit Dashboard üzerinden Secrets ayarlarını yapın.")
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

# --- 4. YAN PANEL (SIDEBAR) ---
with st.sidebar:
    st.markdown("## ⚖️ Hukuk Kontrol Paneli")
    st.divider()
    
    if client.is_ready():
        st.success("Sistem Çevrimiçi")
    else:
        st.error("Bağlantı Hatası")
    
    st.divider()
    
    # Sohbeti Dışa Aktar
    if "messages" in st.session_state and len(st.session_state.messages) > 0:
        chat_text = ""
        for m in st.session_state.messages:
            chat_text += f"{m['role'].upper()}: {m['content']}\n\n"
        
        st.download_button(
            label="📄 Sohbeti TXT Olarak İndir",
            data=chat_text,
            file_name="hukuk_analiz.txt",
            mime="text/plain",
            use_container_width=True
        )

    if st.button("Geçmişi Temizle", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- 5. SOHBET ARAYÜZÜ ---
st.title("⚖️ Profesyonel Hukuk Danışmanı")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Mesajları Ekrana Bas
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Soru Girişi
if prompt := st.chat_input("Hukuki sorunuzu buraya yazın..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        with st.spinner("Dökümanlar taranıyor..."):
            # A. HİBRİT ARAMA (Anlamsal + Kelime Bazlı)
            collection = client.collections.get("HukukDoc")
            results = collection.query.hybrid(query=prompt, limit=4, alpha=0.5)
            
            context = ""
            sources = []
            for obj in results.objects:
                meta = f"{obj.properties['filename']} (S. {obj.properties['page_number']})"
                sources.append(meta)
                context += f"\n[KAYNAK: {meta}]\n{obj.properties['content']}\n"

            # B. AI YANIT ÜRETİMİ (STREAMING)
            messages = [
                {"role": "system", "content": "Sen kıdemli bir hukuk müşavirisin. Sadece verilen dökümanlara dayanarak profesyonelce cevap ver. Maddeler kullan."},
                {"role": "user", "content": f"Bağlam:\n{context}\n\nSoru: {prompt}"}
            ]

            stream = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)

            # C. KAYNAK GÖSTERİMİ
            if sources:
                with st.expander("📍 Referans Alınan Kaynaklar"):
                    for s in set(sources):
                        st.write(f"- {s}")

    st.session_state.messages.append({"role": "assistant", "content": full_response})
