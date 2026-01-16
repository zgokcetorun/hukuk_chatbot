import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Hukuk Asistanı", page_icon="⚖️", layout="wide")

# --- CUSTOM CSS (Lacivert & Gray Theme) ---
st.markdown("""
    <style>
        /* Ana arka plan */
        .stApp {
            background-color: #f8f9fa;
        }
        
        /* Başlık stili */
        h1 {
            color: #002366; /* Lacivert */
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-weight: 700;
        }

        /* Chat mesajları tasarımı */
        .stChatMessage {
            border-radius: 15px;
            padding: 10px;
            margin-bottom: 10px;
        }

        /* Sidebar rengi */
        [data-testid="stSidebar"] {
            background-color: #002366;
        }
        [data-testid="stSidebar"] * {
            color: white !important;
        }

        /* Butonlar */
        .stButton>button {
            background-color: #002366;
            color: white;
            border-radius: 5px;
            border: none;
        }
        
        .stButton>button:hover {
            background-color: #4a4a4a; /* Gray on hover */
            color: white;
        }

        /* Expander (Referanslar) */
        .streamlit-expanderHeader {
            background-color: #e9ecef;
            border-radius: 5px;
            color: #002366 !important;
        }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR (Opsiyonel Bilgi Alanı) ---
with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/100/ffffff/scales.png", width=80)
    st.markdown("### Dijital Hukuk Ofisi")
    st.info("Bu asistan, dökümanlarınızı tarayarak hukuki görüş oluşturur.")
    st.divider()
    st.caption("Versiyon: 1.0.2")

st.title("⚖️ Profesyonel Hukuk Danışmanı")

# --- BAĞLANTI ---
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

# --- CHAT ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Sorunuzu buraya yazın..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Hukuki dökümanlar analiz ediliyor..."):
            
            collection = client.collections.get("HukukDoc")
            response = collection.query.hybrid(
                query=prompt,
                limit=4,
                alpha=0.5
            )
            
            context = ""
            sources = []
            for obj in response.objects:
                source_info = f"{obj.properties['filename']} (S. {obj.properties['page_number']})"
                sources.append(source_info)
                context += f"\n[KAYNAK: {source_info}]\n{obj.properties['content']}\n"

            system_instruction = """Sen kıdemli bir hukuk müşavirisin. 
            Görevin, aşağıdaki döküman parçalarını kullanarak kullanıcının sorusuna net, profesyonel ve yardımcı bir cevap oluşturmaktır.
            
            KURALLAR:
            1. Cevapların 'robotik' olmasın. Bir avukat gibi akıcı ve mantıklı bir kurguyla anlat.
            2. Eğer dökümanlarda cevap varsa, genel konuşma; spesifik madde veya kuralları belirt.
            3. Dökümanlarda bilgi yoksa 'Veritabanımda bu konuda net bir bilgi bulunmuyor' de.
            4. Cevabını verirken önemli kısımları kalın harflerle belirt.
            5. Cevabın sonunda varsa mutlaka ilgili kanun maddesine veya dokümana atıf yap."""

            history = st.session_state.messages[-3:]
            
            messages = [{"role": "system", "content": system_instruction}]
            for m in history:
                messages.append({"role": m["role"], "content": m["content"]})
            
            messages.append({"role": "user", "content": f"Bağlam Dökümanları:\n{context}\n\nSoru: {prompt}"})
            
            ai_response = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.4
            )
            
            full_response = ai_response.choices[0].message.content
            st.markdown(full_response)
            
            with st.expander("📍 Kullanılan Referanslar"):
                for s in set(sources):
                    st.write(f"- {s}")

    st.session_state.messages.append({"role": "assistant", "content": full_response})
