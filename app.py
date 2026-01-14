import streamlit as st
import weaviate
import weaviate.classes as wvc
import openai

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Hukuk Asistanı", page_icon="⚖️")
st.title("⚖️ Hukuk Chatbotu")
st.markdown("Yüklediğiniz dökümanlara dayanarak sorularınızı yanıtlarım.")

# --- BAĞLANTI VE SECRET'LAR ---
# GitHub'a yüklediğinde bunları st.secrets üzerinden alacağız
W_URL = st.secrets["WEAVIATE_URL"]
W_API = st.secrets["WEAVIATE_API_KEY"]
O_API = st.secrets["OPENAI_API_KEY"]

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=W_URL,
    auth_credentials=weaviate.auth.AuthApiKey(W_API),
    headers={"X-OpenAI-Api-Key": O_API}
)

openai.api_key = O_API

# --- CHAT ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Hangi konuda bilgi almak istersiniz?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Dökümanlar inceleniyor..."):
            # 1. Weaviate'de Arama Yap (RAG - Retrieval)
            collection = client.collections.get("HukukDoc")
            response = collection.query.near_text(
                query=prompt,
                limit=3 # En alakalı 3 sayfayı getir
            )
            
            context = ""
            for obj in response.objects:
                context += f"\n--- Kaynak: {obj.properties['filename']} (Sayfa {obj.properties['page_number']}) ---\n"
                context += obj.properties['content']

            # 2. OpenAI ile Cevap Oluştur (Augmentation)
            messages = [
                {"role": "system", "content": "Sen profesyonel bir hukuk asistanısın.
                1.Sadece sana verilen dökümanlara dayanarak cevap ver. Eğer bilgi dökümanlarda yoksa bilmediğini söyle.
                2) Hukukcu olmayanlarin da anlayacagi bir dil kullan."},
                {"role": "user", "content": f"Soru: {prompt}\n\nDökümanlar:\n{context}"}
            ]
            
            ai_response = openai.chat.completions.create(
                model="gpt-4o", # Veya gpt-3.5-turbo
                messages=messages
            )
            
            full_response = ai_response.choices[0].message.content
            st.markdown(full_response)
            
            # Kaynakları gösteren bir "expandable" alan ekleyelim
            with st.expander("Kullanılan Kaynaklar"):
                st.write(context)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

client.close()

