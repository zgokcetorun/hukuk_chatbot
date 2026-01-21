import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
import json

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
        "keywords": ["kira", "kiracı", "kiraya veren", "tahliye", "kira bedeli", "kiralama", "kira sözleşmesi", "kira artışı", "depozito", "ev sahibi"],
        "emoji": "🏠"
    },
    "is_hukuku": {
        "collection": "IsDavalari",
        "name": "İş Hukuku",
        "keywords": ["işçi", "işveren", "iş sözleşmesi", "işten çıkarma", "kıdem", "fazla mesai", "iş akdi", "çalışan", "istifa", "tazminat", "işe iade", "patron", "kovdu", "işsiz"],
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
    
    st.divider()
    st.caption("Versiyon: 3.0 (Ultra Fast - Single LLM)")

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

# --- HIZLI KEYWORD ROUTİNG ---
def classify_query_fast(query):
    """Keyword tabanlı hızlı routing"""
    query_lower = query.lower()
    
    scores = {}
    for key, info in COLLECTION_MAP.items():
        score = sum(1 for keyword in info["keywords"] if keyword in query_lower)
        scores[key] = score
    
    # En yüksek skoru bul
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    
    return None

# --- PARALEL ARAMA ---
def search_single_collection(collection_name, query, limit):
    """Tek collection'da ara"""
    try:
        collection = client.collections.get(collection_name)
        response = collection.query.hybrid(query=query, limit=limit, alpha=0.5)
        return response.objects
    except:
        return []

def search_parallel(query, category_keys):
    """Paralel arama (daha hızlı)"""
    results = []
    
    with ThreadPoolExecutor(max_workers=len(category_keys)) as executor:
        futures = {}
        
        for key in category_keys:
            info = COLLECTION_MAP[key]
            future = executor.submit(
                search_single_collection, 
                info["collection"], 
                query, 
                4 if len(category_keys) == 1 else 2
            )
            futures[future] = key
        
        for future in futures:
            key = futures[future]
            info = COLLECTION_MAP[key]
            objects = future.result()
            
            for obj in objects:
                results.append({
                    "content": obj.properties['content'],
                    "filename": obj.properties['filename'],
                    "page": obj.properties['page_number'],
                    "category": info["name"],
                    "category_key": key,
                    "emoji": info["emoji"]
                })
    
    return results

# --- TEK LLM ÇAĞRISI İLE ROUTİNG + CEVAP ---
def get_answer_with_smart_routing(query, all_results, history):
    """Tek LLM çağrısında hem kategori tespit hem cevap"""
    
    # Tüm kategorilerden context hazırla
    contexts_by_category = {}
    for result in all_results:
        cat_key = result["category_key"]
        if cat_key not in contexts_by_category:
            contexts_by_category[cat_key] = []
        contexts_by_category[cat_key].append(result)
    
    # Her kategoriden context oluştur
    full_context = ""
    for cat_key, results in contexts_by_category.items():
        info = COLLECTION_MAP[cat_key]
        full_context += f"\n\n=== {info['emoji']} {info['name'].upper()} KATEGORİSİ ===\n"
        for r in results[:2]:  # Her kategoriden max 2 belge
            full_context += f"[KAYNAK: {r['filename']} S.{r['page']}]\n{r['content'][:600]}...\n\n"
    
    # Sistem prompt'u (tek seferde hem routing hem cevap)
    system_instruction = f"""Sen kıdemli bir hukuk müşavirisin. 

GÖREVİN 2 AŞAMALI:

1. ADIM - KATEGORİ TESPİTİ:
Kullanıcının sorusunu analiz et ve hangi kategoriye ait olduğunu belirle.
Mevcut kategoriler: {', '.join([f"{info['emoji']} {key}" for key, info in COLLECTION_MAP.items()])}

2. ADIM - CEVAP OLUŞTURMA:
Belirlediğin kategorideki belgelerden yararlanarak soruyu yanıtla.

KURALLAR:
- Cevabın robotik olmasın, avukat gibi akıcı anlat
- Önemli kısımları **kalın** yaz
- Spesifik madde/kural varsa belirt
- Cevabın sonunda kaynaklara atıf yap
- Belirlediğin kategoriyi cevabında belirtme (otomatik gösteriyoruz)

ÇOK ÖNEMLİ: Soruya en uygun kategorideki belgeleri kullan. Diğer kategorilerdeki belgeleri görmezden gel."""

    # Chat history
    messages = [{"role": "system", "content": system_instruction}]
    for m in history[-2:]:  # Son 2 mesaj
        if m["role"] != "system":
            messages.append({"role": m["role"], "content": m["content"]})
    
    messages.append({
        "role": "user", 
        "content": f"{full_context}\n\nSORU: {query}"
    })
    
    # TEK LLM ÇAĞRISI
    return ai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.4,
        stream=True
    )

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
        # ==================== 1. HIZLI ROUTİNG (Keyword) ====================
        detected_category = classify_query_fast(prompt)
        
        if detected_category:
            categories_to_search = [detected_category]
            info = COLLECTION_MAP[detected_category]
            category_info_html = f'<div class="category-badge">⚡ {info["emoji"]} {info["name"]}</div>'
        else:
            # Keyword bulamazsa tüm kategorilerde ara
            categories_to_search = list(COLLECTION_MAP.keys())
            category_info_html = '<div class="category-badge">📚 Tüm Kategoriler</div>'
        
        st.markdown(category_info_html, unsafe_allow_html=True)
        
        # ==================== 2. PARALEL ARAMA ====================
        with st.spinner("📚 Belgeler taranıyor..."):
            all_results = search_parallel(prompt, categories_to_search)
        
        if not all_results:
            response_text = "Üzgünüm, bu konuyla ilgili belge bulunamadı."
            st.warning(response_text)
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response_text,
                "category_info": category_info_html
            })
            st.stop()
        
        # ==================== 3. TEK LLM ÇAĞRISI (Routing + Cevap) ====================
        with st.spinner("✍️ Yanıt hazırlanıyor..."):
            ai_response = get_answer_with_smart_routing(
                prompt, 
                all_results, 
                st.session_state.messages
            )
            
            # Streaming yanıt
            response_placeholder = st.empty()
            full_response = ""
            
            for chunk in ai_response:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)
            
            # Referansları göster (kullanılan kategorideki belgeler)
            used_results = [r for r in all_results if r["category_key"] == detected_category] if detected_category else all_results[:4]
            
            with st.expander("📍 Kullanılan Referanslar"):
                for r in used_results:
                    st.write(f"- {r['emoji']} {r['filename']} (S. {r['page']}) - {r['category']}")

        st.session_state.messages.append({
            "role": "assistant", 
            "content": full_response,
            "category_info": category_info_html
        })
