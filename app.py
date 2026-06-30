import streamlit as st
import csv
import requests
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
HAVERFORD_CSV_PATH = "haverford_ranks.csv"
# Pointing directly to the parent web layer endpoint to avoid hidden API 404 pathing bugs
DEUCALION_API_URL = "https://psl.eu"

# --- PAGE SETUP ---
st.set_page_config(page_title="Latin Curriculum Analytics", layout="centered")
st.title("🏛️ Latin Corpus Vocabulary Profiler")
st.write("Upload a candidate reading text to evaluate its B2 curriculum relevance and verify the 95% comprehension rule.")

# --- HELPER FUNCTIONS ---
@st.cache_data
def load_haverford_db(csv_path):
    rank_map = {}
    try:
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=',')
            for row in reader:
                if row.get("lemma") and row.get("bridge_rank"):
                    lemma = row["lemma"].lower().strip()
                    try:
                        rank_map[lemma] = int(row["bridge_rank"])
                    except ValueError:
                        continue
    except FileNotFoundError:
        st.error(f"Error: Database file '{csv_path}' not found in web server directory.")
    return rank_map

def lemmatize_via_deucalion(raw_text):
    """
    Chunks large texts, executes a form POST request directly to the 
    main endpoint layer, and collects token dict arrays.
    """
    paragraphs = raw_text.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0
    
    for p in paragraphs:
        if current_length + len(p) > 2000 and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [p]
            current_length = len(p)
        else:
            current_chunk.append(p)
            current_length += len(p)
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    combined_tokens = []
    progress_bar = st.progress(0)
    
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
            
        progress_bar.progress((i + 1) / len(chunks), text=f"Processing text chunk {i+1} of {len(chunks)}...")
        
        # Packaging the payload exactly as the text-box form engine maps data
        payload = {"data": chunk}
        try:
            # Adding an explicit headers signature mimics browser interface interaction
            headers = {"Accept": "application/json"}
            response = requests.post(DEUCALION_API_URL, data=payload, headers=headers, timeout=45)
            
            if response.status_code == 200:
                chunk_data = response.json()
                if isinstance(chunk_data, list):
                    combined_tokens.extend(chunk_data)
            else:
                # Secondary Fallback: Try targeting the base engine api subroute if form rejects direct json requests
                alt_url = "https://psl.eu"
                alt_response = requests.post(alt_url, json={"text": chunk, "format": "json"}, timeout=30)
                if alt_response.status_code == 200:
                    alt_data = alt_response.json()
                    tokens_list = alt_data.get("tokens", alt_data)
                    if isinstance(tokens_list, list):
                        combined_tokens.extend(tokens_list)
        except Exception:
            continue
            
    progress_bar.empty()
    return combined_tokens if combined_tokens else None

# --- CORE WEB INTERFACE AND LOGIC ---
rank_db = load_haverford_db(HAVERFORD_CSV_PATH)
uploaded_file = st.file_uploader("Choose a raw Latin text file (.txt)", type=["txt"])

if uploaded_file is not None and rank_db:
    raw_latin_text = uploaded_file.read().decode("utf-8")
    
    with st.spinner("Analyzing text tokens via Deucalion LASLA models... Please wait."):
        parsed_tokens = lemmatize_via_deucalion(raw_latin_text)
        
    if parsed_tokens:
        categories = {
            "Core A1-B1\n(Rank 1-1000)": 0,
            "Bridge B2 Target\n(Rank 1001-4000)": 0,
            "Advanced Threshold\n(Rank 4001-5000)": 0,
            "Rare Vocabulary\n(Outside Top 5000)": 0
        }
        
        total_tokens = 0
        rare_words_list = []
        
        for item in parsed_tokens:
            # Handle variable capitalization keys between Deucalion web layers ('POS' vs 'pos')
            lemma = item.get("lemma", item.get("lemma", "")).lower().strip()
            pos = item.get("POS", item.get("pos", ""))
            token = item.get("form", item.get("word", ""))
            
            if pos == "PUNC" or not lemma or lemma == "punc":
                continue
                
            if "界" in lemma:
                lemma = lemma.split("界")
                
            total_tokens += 1
            rank = rank_db.get(lemma, 9999)
            
            if rank <= 1000:
                categories["Core A1-B1\n(Rank 1-1000)"] += 1
            elif rank <= 4000:
                categories["Bridge B2 Target\n(Rank 1001-4000)"] += 1
            elif rank <= 5000:
                categories["Advanced Threshold\n(Rank 4001-5000)"] += 1
            else:
                categories["Rare Vocabulary\n(Outside Top 5000)"] += 1
                rare_words_list.append((token, lemma))

        labels = list(categories.keys())
        counts = list(categories.values())
        percentages = [(c / total_tokens) * 100 for c in counts] if total_tokens else

        st.success(f"Analysis Complete! Processed {total_tokens:,} valid word tokens.")
        
        comprehension_95_score = percentages + percentages
        rare_vocab_score = percentages
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="95% Rule Comprehension Score", value=f"{comprehension_95_score:.1f}%")
        with col2:
            st.metric(label="Rare Vocabulary Rate", value=f"{rare_vocab_score:.1f}%")
            
        if comprehension_95_score >= 95.0:
            st.balloons()
            st.success("✅ This text complies with the 95% comprehension rule for your B2 curriculum!")
        else:
            st.warning("⚠️ Warning: This text fails the 95% rule. Vocabulary density is too complex for independent reading.")

        colors = ['#2ecc71', '#3498db', '#f1c40f', '#e74c3c']
        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(labels, percentages, color=colors, edgecolor='grey', width=0.5)
        
        for bar, percent in zip(bars, percentages):
            yval = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, yval + 1, f"{percent:.1f}%", ha='center', va='bottom', fontweight='bold')
            
        ax.set_ylabel("Percentage of Total Running Tokens (%)")
        ax.set_ylim(0, 100)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        st.pyplot(fig)
        
        if rare_words_list:
            with st.expander("🔍 View Rare Words Outside Top 5000 (Requires Pre-Teaching or Glossing)"):
                unique_rare = sorted(list(set([f"{t} ({l})" for t, l in rare_words_list])))
                st.write(", ".join(unique_rare[:200]))
