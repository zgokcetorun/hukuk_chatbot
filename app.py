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
        .stChatMessage { border-radius: 15px; padding: 10px; margin-bottom: 10px; }
        [data-testid="stSidebar"] { background-color: #002366; }
        [data-testid="stSidebar"] * { color: white !important; }
        .stButton>button { background-color: #002366; color: white; border-radius: 5px; border: none; width: 100%; }
        .stButton>button:hover { background-color: #4a4a4a; color: white; }
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

# --- KOLEKSİYON KONTROL (GELİŞTİRİLMİŞ) ---
def init_feedback_collection():
    try:
        if not client.collections.exists("Feedback"):
            client.collections.create(
                name="Feedback",
                vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(), # Vektörleştirici eklendi
                properties=[
                    wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="is_correct", data_type=wvc.config.DataType.TEXT),
                ]
            )
            return "Koleksiyon Yeni Oluşturuldu"
        return "Koleksiyon Zaten Var"
    except Exception as e:
        return f"Hata: {str(e)}"

# Uygulama başlar başlamaz çalıştır
status = init_feedback_collection()

# --- FEEDBACK FONKSİYONU ---
def save_feedback(q, r, score):
    try:
        f_col = client.collections.get("Feedback")
        f_col.data.insert({"question": q, "answer": r, "is_correct": score})
        st.toast(f"Kaydedildi: {score}", icon="✅")
    except Exception as e:
        st.error(f"Kayıt Hatası: {e}")

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/100/ffffff/scales.png", width=80)
    st.markdown("### Dijital Hukuk Ofisi")
    st.info(f"Sistem Durumu: {status}")
    
    st.divider()
    with st.expander("🔐 Admin Paneli"):
        if st.text_input("Şifre", type="password") == "hukuk2024":
            try:
                f_col = client.collections.get("Feedback")
                results = f_col.query.fetch_objects(limit=50).objects
                if not results:
                    st.write("Henüz kayıt yok.")
                for res in results:
                    st.write(f"**Soru:** {res.properties.get('question', '')[:50]}...")
                    st.write(f"**Sonuç:** {res.properties.get('is_correct', '')}")
                    st.divider()
            except Exception as e:
                st.write("Veriler okunamadı.")

st.title("⚖️ Profesyonel Hukuk Danışmanı")

# --- CHAT MANTIĞI ---
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
        with st.spinner("İnceleniyor..."):
            # 1. Arama
            collection = client.collections.get("HukukDoc")
            response = collection.query.hybrid(query=prompt, limit=4, alpha=0.5)
            
            context = ""
            sources = []
            for obj in response.objects:
                s_info = f"{obj.properties['filename']} (S. {obj.properties['page_number']})"
                sources.append(s_info)
                context += f"\n[KAYNAK: {s_info}]\n{obj.properties['content']}\n"

            # 2. Yanıt Üretme
            messages = [
                {"role": "system", "content": "Sen kıdemli bir hukuk müşavirisin. Önemli yerleri kalın yaz."},
                {"role": "user", "content": f"Bağlam:\n{context}\n\nSoru: {prompt}"}
            ]
            ai_res = ai_client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0.4)
            full_response = ai_res.choices[0].message.content
            st.markdown(full_response)
            
            # 3. Kaynaklar
            with st.expander("📍 Kaynaklar"):
                for s in set(sources): st.write(f"- {s}")

            # 4. Geri Bildirim Butonları
            st.write("---")
            c1, c2 = st.columns([0.2, 0.2])
            with c1:
                if st.button("👍 Doğru", key=f"p_{len(st.session_state.messages)}"):
                    save_feedback(prompt, full_response, "DOĞRU")
            with c2:
                if st.button("👎 Yanlış", key=f"n_{len(st.session_state.messages)}"):
                    save_feedback(prompt, full_response, "YANLIŞ")

    st.session_state.messages.append({"role": "assistant", "content": full_response})
