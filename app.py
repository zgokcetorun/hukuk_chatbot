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
        
        /* Kategori badge */
        .category-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 12px;
            font-weight: bold;
            margin: 5px 0;
            background-color: #002366;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

# --- KATEGORİ TANIMLARI ---
COLLECTION_MAP = {
    "kira_hukuku": {
        "collection": "HukukDoc",
        "name": "Kira Hukuku",
        "description": "Kira sözleşmeleri, kiracı-kiraya veren ilişkileri, tahliye, kira artışı, kiralama hukuku",
        "emoji": "🏠"
    },
    "is_hukuku": {
        "collection": "IsDavalari",
        "name": "İş Hukuku",
        "description": "İş sözleşmeleri, işçi-işveren ilişkileri, işten çıkarma, kıdem tazminatı, fazla mesai, çalışma hakları",
        "emoji": "💼"
    }
}

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/100/ffffff/scales.png", width=80)
    st.markdown("### Dijital Hukuk Ofisi")
    st.info("Bu asistan, dökümanlarınızı tarayarak hukuki görüş oluşturur.")
    
    st.divider()
    
    # Mevcut kategoriler
    st.markdown("#### 📚 Mevcut Kategoriler")
    for key, info in COLLECTION_MAP.items():
        st.markdown(f"{info['emoji']} **{info['name']}**")
        st.caption(info['description'])
    
    st.divider()
    
    # Manuel kategori seçimi (opsiyonel)
    st.markdown("#### ⚙️ Arama Ayarları")
    manual_mode = st.toggle("Manuel Kategori Seçimi", value=False)
    
    if manual_mode:
        selected_category = st.selectbox(
            "Kategori Seçin",
            options=["Otomatik"] + [info["name"] for info in COLLECTION_MAP.values()]
        )
    else:
        selected_category = "Otomatik"
    
    st.divider()
    st.caption("Versiyon: 2.0 (LLM Routing)")

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

# --- LLM İLE AKILLI ROUTİNG ---
def classify_query_with_llm(query):
    """LLM ile soruyu kategorize et"""
    try:
        # Kategorileri LLM'e açıkla
        category_options = "\n".join([
            f"- {key}: {info['description']}"
            for key, info in COLLECTION_MAP.items()
        ])
        
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",  # Hızlı ve ucuz
            messages=[{
                "role": "system",
                "content": f"""Sen bir hukuk sorusu sınıflandırma uzmanısın.

Kullanıcının sorusunu analiz et ve hangi hukuk kategorisine ait olduğunu belirle.

MEVCUT KATEGORİLER:
{category_options}

KURALLAR:
1. Soruyu dikkatlice oku ve hangi kategoriye ait olduğunu anla
2. Sadece kategori anahtarını döndür (örn: kira_hukuku veya is_hukuku)
3. Birden fazla kategoriye uyuyorsa, en alakalı olanı seç
4. Hiçbir kategoriye uymuyorsa "belirsiz" yaz
5. Başka hiçbir açıklama ekleme, sadece kategori adını yaz"""
            }, {
                "role": "user",
                "content": f"Soru: {query}\n\nBu soru hangi kategoriye ait?"
            }],
            temperature=0,
            max_tokens=20
        )
        
        detected = response.choices[0].message.content.strip().lower()
        
        # Geçerli kategori mi kontrol et
        if detected in COLLECTION_MAP.keys():
            return detected
        
        return None
        
    except Exception as e:
        st.error(f"❌ Kategori tespiti hatası: {e}")
        return None

def search_in_collection(query, category_key):
    """Belirli bir collection'da ara"""
    try:
        info = COLLECTION_MAP[category_key]
        collection = client.collections.get(info["collection"])
        
        response = collection.query.hybrid(
            query=query,
            limit=4,
            alpha=0.5
        )
        
        results = []
        for obj in response.objects:
            results.append({
                "content": obj.properties['content'],
                "filename": obj.properties['filename'],
                "page": obj.properties['page_number'],
                "category": info["name"],
                "emoji": info["emoji"]
            })
        
        return results
        
    except Exception as e:
        st.error(f"❌ Arama hatası ({COLLECTION_MAP[category_key]['name']}): {e}")
        return []

def search_in_all_collections(query):
    """Tüm collection'larda ara (fallback)"""
    all_results = []
    
    for category_key, info in COLLECTION_MAP.items():
        try:
            collection = client.collections.get(info["collection"])
            response = collection.query.hybrid(
                query=query,
                limit=2,  # Her collection'dan daha az
                alpha=0.5
            )
            
            for obj in response.objects:
                all_results.append({
                    "content": obj.properties['content'],
                    "filename": obj.properties['filename'],
                    "page": obj.properties['page_number'],
                    "category": info["name"],
                    "emoji": info["emoji"]
                })
                
        except Exception as e:
            st.warning(f"⚠️ {info['name']} collection'ında arama yapılamadı")
    
    return all_results

# --- CHAT ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("category_info"):
            st.markdown(message["category_info"], unsafe_allow_html=True)

if prompt := st.chat_input("Sorunuzu buraya yazın..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("🧠 Soru analiz ediliyor..."):
            
            # 1. KATEGORİ TESPİTİ (LLM İLE)
            detected_category = None
            category_info_html = ""
            
            if manual_mode and selected_category != "Otomatik":
                # Manuel seçim
                for key, info in COLLECTION_MAP.items():
                    if info["name"] == selected_category:
                        detected_category = key
                        category_info_html = f'<div class="category-badge">{info["emoji"]} {info["name"]} (Manuel)</div>'
                        break
            else:
                # LLM ile otomatik tespit
                with st.spinner("🎯 Kategori tespit ediliyor..."):
                    detected_category = classify_query_with_llm(prompt)
                    
                    if detected_category:
                        info = COLLECTION_MAP[detected_category]
                        category_info_html = f'<div class="category-badge">🎯 {info["emoji"]} {info["name"]} (AI Tespit)</div>'
                        st.markdown(category_info_html, unsafe_allow_html=True)
                    else:
                        st.info("ℹ️ Kategori belirlenemedi, tüm kategorilerde arama yapılıyor...")
            
            # 2. ARAMA YAP
            with st.spinner("📚 Belgeler taranıyor..."):
                if detected_category:
                    # Belirli kategoride ara
                    results = search_in_collection(prompt, detected_category)
                    searched_in = COLLECTION_MAP[detected_category]["name"]
                else:
                    # Tüm kategorilerde ara
                    results = search_in_all_collections(prompt)
                    searched_in = "Tüm Kategoriler"
            
            if not results:
                response_text = f"Üzgünüm, **{searched_in}** kategorisinde bu konuyla ilgili belge bulunamadı. Lütfen sorunuzu farklı kelimelerle ifade etmeyi deneyin."
                st.warning(response_text)
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response_text,
                    "category_info": category_info_html
                })
                st.stop()
            
            # 3. CONTEXT OLUŞTUR
            context = ""
            sources = []
            for result in results:
                source_info = f"{result['emoji']} {result['filename']} (S. {result['page']}) - {result['category']}"
                sources.append(source_info)
                context += f"\n[KAYNAK: {source_info}]\n{result['content']}\n"

            # 4. AI YANIT OLUŞTUR
            with st.spinner("✍️ Cevap hazırlanıyor..."):
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
                    if m["role"] != "system":
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
                    for s in sources:
                        st.write(f"- {s}")

        st.session_state.messages.append({
            "role": "assistant", 
            "content": full_response,
            "category_info": category_info_html
        })
