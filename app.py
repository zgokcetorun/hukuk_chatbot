import streamlit as st
import weaviate
import weaviate.classes as wvc
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
import json
import re

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
        
        /* İçtihat butonları - daha belirgin */
        [data-testid="stSidebar"] .stButton>button {
            background-color: transparent;
            color: white;
            border: 3px solid white;
            border-radius: 8px;
            font-weight: bold;
            padding: 12px;
            transition: all 0.3s ease;
        }
        
        [data-testid="stSidebar"] .stButton>button:hover {
            background-color: white;
            color: #002366;
            border: 3px solid white;
            transform: scale(1.02);
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
        
        /* Kanun maddeleri vurgusu */
        .stMarkdown hr {
            margin: 20px 0;
            border: none;
            border-top: 2px solid #002366;
        }
        
        .stMarkdown strong {
            color: #002366;
        }
        
        /* Kanun maddeleri emoji'si */
        .stMarkdown h2:has(+ ul) {
            color: #002366;
            font-size: 1.1em;
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
    
    # İçtihat Araması Butonları
    st.markdown("#### ⚖️ İçtihat Araması")
    
    yargitay_button = st.button(
        "⚖️ Yargıtay Kararlarında Ara",
        use_container_width=True,
        help="Yargıtay kararlarında ara"
    )
    
    danistay_button = st.button(
        "🏛️ Danıştay Kararlarında Ara",
        use_container_width=True,
        help="Danıştay kararlarında ara"
    )
    
    # Buton durumu göstergesi
    if yargitay_button:
        st.info("🔍 Yargıtay kararlarında aranacak (Yakında aktif)")
    
    if danistay_button:
        st.info("🔍 Danıştay kararlarında aranacak (Yakında aktif)")
    
    st.divider()
    st.caption("Versiyon: 3.2 (İçtihat Butonları - UI)")

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

# --- KANUN LİNKLERİ OTOMATİK TESPİT ---
def extract_law_links(response_text):
    """Cevaptaki kanun maddelerini tespit et ve link oluştur"""
    
    # Kanun veritabanı
    law_database = {
        "tbk": {
            "patterns": [r"tbk", r"türk borçlar kanunu", r"borçlar kanunu", r"6098"],
            "name": "Türk Borçlar Kanunu (TBK - 6098 Sayılı)",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6098&MevzuatTur=1&MevzuatTertip=5",
            "pdf": "https://www.mevzuat.gov.tr/File/GeneratePdf?mevzuatNo=6098&mevzuatTur=KanunHukmu&mevzuatTertip=5"
        },
        "is_kanunu": {
            "patterns": [r"iş kanunu", r"4857"],
            "name": "İş Kanunu (4857 Sayılı)",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=4857&MevzuatTur=1&MevzuatTertip=5",
            "pdf": "https://www.mevzuat.gov.tr/File/GeneratePdf?mevzuatNo=4857&mevzuatTur=KanunHukmu&mevzuatTertip=5"
        },
        "medeni": {
            "patterns": [r"medeni kanun", r"tmk", r"4721"],
            "name": "Türk Medeni Kanunu (4721 Sayılı)",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=4721&MevzuatTur=1&MevzuatTertip=5",
            "pdf": "https://www.mevzuat.gov.tr/File/GeneratePdf?mevzuatNo=4721&mevzuatTur=KanunHukmu&mevzuatTertip=5"
        },
        "hmk": {
            "patterns": [r"hmk", r"hukuk muhakemeleri", r"6100"],
            "name": "Hukuk Muhakemeleri Kanunu (6100 Sayılı)",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6100&MevzuatTur=1&MevzuatTertip=5",
            "pdf": "https://www.mevzuat.gov.tr/File/GeneratePdf?mevzuatNo=6100&mevzuatTur=KanunHukmu&mevzuatTertip=5"
        },
        "tck": {
            "patterns": [r"tck", r"ceza kanunu", r"türk ceza kanunu", r"5237"],
            "name": "Türk Ceza Kanunu (5237 Sayılı)",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=5237&MevzuatTur=1&MevzuatTertip=5",
            "pdf": "https://www.mevzuat.gov.tr/File/GeneratePdf?mevzuatNo=5237&mevzuatTur=KanunHukmu&mevzuatTertip=5"
        }
    }
    
    found_laws = []
    text_lower = response_text.lower()
    
    # Her kanunu kontrol et
    for law_key, law_info in law_database.items():
        for pattern in law_info["patterns"]:
            if re.search(pattern, text_lower):
                if law_key not in [l["key"] for l in found_laws]:
                    found_laws.append({
                        "key": law_key,
                        "name": law_info["name"],
                        "url": law_info["url"],
                        "pdf": law_info["pdf"]
                    })
                break
    
    return found_laws

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
- Açıklama içinde kanun maddelerine atıfta bulun (örn: "TBK Madde 299'a göre...")
- Belirlediğin kategoriyi cevabında belirtme (otomatik gösteriyoruz)

ÇOK ÖNEMLİ FORMAT:
Cevabını şu şekilde yapılandır:

[Ana açıklama burada - akıcı bir şekilde, kanun maddelerine atıflar yaparak]

Örneğin: "Kiracı olarak **TBK Madde 299**'da belirtilen haklara sahipsiniz. Bu maddeye göre..."

---

**📜 İlgili Kanun Maddeleri:**
- [SADECE yukarıdaki açıklamada bahsettiğin maddeleri buraya tekrar listele]
- [YENİ madde ekleme, sadece yukarıda kullandıklarını yaz]
- [Her maddeyi ayrı satırda yaz, örn: "Türk Borçlar Kanunu Madde 299"]
- [Eğer hiç kanun maddesi kullanmadıysan bu bölümü boş bırak]

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
            
            # Referansları göster
            used_results = [r for r in all_results if r["category_key"] == detected_category] if detected_category else all_results[:4]
            
            with st.expander("📍 Kullanılan Referanslar"):
                for r in used_results:
                    st.write(f"- {r['emoji']} {r['filename']} (S. {r['page']}) - {r['category']}")
            
            # OTOMATİK KANUN LİNKİ TESPİTİ
            law_links = extract_law_links(full_response)
            
            if law_links:
                with st.expander("🔗 Bahsedilen Kanunlar - Tam Metin"):
                    st.markdown("**Yanıtta bahsedilen kanunların tam metinleri:**")
                    st.markdown("")
                    
                    for law in law_links:
                        st.markdown(f"📖 **{law['name']}**")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"[📄 Tam Metin Oku (mevzuat.gov.tr)]({law['url']})")
                        with col2:
                            st.markdown(f"[⬇️ PDF İndir]({law['pdf']})")
                        st.markdown("---")
                    
                    st.info("💡 **İpucu:** Linke tıkladıktan sonra sayfada Ctrl+F (veya Cmd+F) yaparak bahsedilen madde numarasını arayabilirsiniz.")

        st.session_state.messages.append({
            "role": "assistant", 
            "content": full_response,
            "category_info": category_info_html
        })
