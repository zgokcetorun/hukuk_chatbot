import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI # Yeni versiyon kullanımı

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Hukuk Asistanı", page_icon="⚖️", layout="wide")
st.title("⚖️ Profesyonel Hukuk Danışmanı")

# --- BAĞLANTI ---
W_URL = st.secrets["WEAVIATE_URL"]
W_API = st.secrets["WEAVIATE_API_KEY"]
O_API = st.secrets["OPENAI_API_KEY"]

# OpenAI istemcisini başlat
ai_client = OpenAI(api_key=O_API)

# Weaviate bağlantısını cache'leyelim (Performans için)
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

# Mesaj geçmişini göster
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Sorunuzu buraya yazın (Örn: Kira artış oranı nedir?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Hukuki dökümanlar taranıyor ve analiz ediliyor..."):
            
            # 1. HİBRİT ARAMA (Vektör + Keyword)
            # Bu yöntem çok daha spesifik sonuçlar getirir
            collection = client.collections.get("HukukDoc")
            response = collection.query.hybrid(
                query=prompt,
                limit=4, # 4 parça daha iyi bağlam sağlar
                alpha=0.5 # 0.5 hem anlama hem kelime eşleşmesine bakar
            )
            
            context = ""
            sources = []
            for obj in response.objects:
                source_info = f"{obj.properties['filename']} (S. {obj.properties['page_number']})"
                sources.append(source_info)
                context += f"\n[KAYNAK: {source_info}]\n{obj.properties['content']}\n"

            # 2. GELİŞMİŞ SİSTEM PROMPTU (Botun karakterini burada belirliyoruz)
            system_instruction = """Sen kıdemli bir hukuk müşavirisin. 
            Görevin, aşağıdaki döküman parçalarını kullanarak kullanıcının sorusuna net, profesyonel ve yardımcı bir cevap oluşturmaktır.
            
            KURALLAR:
            1. Cevapların 'robotik' olmasın. Bir avukat gibi akıcı ve mantıklı bir kurguyla anlat.
            2. Eğer dökümanlarda cevap varsa, genel konuşma; spesifik madde veya kuralları belirt.
            3. Dökümanlarda bilgi yoksa 'Veritabanımda bu konuda net bir bilgi bulunmuyor' de ve yanlış bilgi uydurma.
            4. Cevabını verirken önemli kısımları kalın harflerle belirt.
            5. Cevabın sonunda varsa mutlaka ilgili kanun maddesine veya dokümana atıf yap."""

            # 3. CHAT GEÇMİŞİNİ DAHİL ET (Memory)
            # Son 3 mesajı alarak bağlamı koruyoruz
            history = st.session_state.messages[-3:]
            
            messages = [{"role": "system", "content": system_instruction}]
            for m in history:
                messages.append({"role": m["role"], "content": m["content"]})
            
            # Güncel soruyu context ile besle
            messages.append({"role": "user", "content": f"Bağlam Dökümanları:\n{context}\n\nSoru: {prompt}"})
            
            # 4. CEVAP ÜRETİMİ
            ai_response = ai_client.chat.completions.create(
                model="gpt-4o", # Daha zeki cevaplar için 4o şart
                messages=messages,
                temperature=0.4 # Daha tutarlı ve ciddi cevaplar için düşürdük
            )
            
            full_response = ai_response.choices[0].message.content
            st.markdown(full_response)
            
            # Kaynakları şık bir şekilde göster
            with st.expander("📍 Kullanılan Referanslar"):
                for s in set(sources):
                    st.write(f"- {s}")

    st.session_state.messages.append({"role": "assistant", "content": full_response})

# Sayfa kapandığında bağlantıyı kapatma (Streamlit'te opsiyoneldir)
