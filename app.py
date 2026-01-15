import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Hukuk Asistanı", page_icon="⚖️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        .stApp { background-color: #f8f9fa; }
        h1 { color: #002366; font-family: 'Segoe UI', sans-serif; font-weight: 700; }
        [data-testid="stSidebar"] { background-color: #002366; }
        [data-testid="stSidebar"] * { color: white !important; }
        .stButton>button { background-color: #002366; color: white; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

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

# --- WEAVIATE FEEDBACK TABLOSUNU HAZIRLA ---
def ensure_feedback_table():
    if not client.collections.exists("Feedback"):
        client.collections.create(
            name="Feedback",
            # Analiz yapacağın için vektörleştiriciyi açık bırakıyoruz
            vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(),
            properties=[
                wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="rating", data_type=wvc.config.DataType.TEXT),
            ]
        )

ensure_feedback_table()

# --- VERİYİ WEAVIATE'E GÖNDER ---
def send_to_weaviate(q, a, r):
    try:
        f_col = client.collections.get("Feedback")
        f_col.data.insert({
            "question": q,
            "answer": a,
            "rating": r
        })
        st.toast(f"Veri Weaviate'e iletildi: {r}", icon="🚀")
    except Exception as e:
        st.error(f"Weaviate kayıt hatası: {e}")

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/100/ffffff/scales.png", width=60)
    st.markdown("### Hukuk Veri Analitiği")
    st.caption("Geri bildirimler doğrudan Weaviate Feedback koleksiyonuna yazılır.")

st.title("⚖️ Profesyonel Hukuk Danışmanı")

# --- CHAT SİSTEMİ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Sorunuzu buraya yazın..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analiz ediliyor..."):
            # 1. Hukuk dökümanlarında ara
            hukuk_col = client.collections.get("HukukDoc")
            res = hukuk_col.query.hybrid(query=prompt, limit=3)
            
            context = "\n".join([o.properties['content'] for o in res.objects])
            
            # 2. Cevap üret
            ai_res = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": f"Bağlam:\n{context}\nSoru: {prompt}"}]
            )
            ans = ai_res.choices[0].message.content
            st.markdown(ans)
            
            # 3. Analiz İçin Feedback Butonları (Form içinde)
            st.write("---")
            with st.form(key=f"analiz_formu_{len(st.session_state.messages)}"):
                st.caption("Bu etkileşimi Weaviate'e analiz için kaydet:")
                c1, c2 = st.columns(2)
                with c1:
                    ok = st.form_submit_button("✅ Başarılı")
                with c2:
                    fail = st.form_submit_button("❌ Hatalı")
                
                if ok:
                    send_to_weaviate(prompt, ans, "POSITIVE")
                if fail:
                    send_to_weaviate(prompt, ans, "NEGATIVE")

    st.session_state.messages.append({"role": "assistant", "content": ans})
