import streamlit as st
import csv
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
HAVERFORD_CSV_PATH = "haverford_ranks.csv"

# --- PAGE SETUP ---
st.set_page_config(page_title="Latin Curriculum Analytics", layout="centered")
st.title("🏛️ Latin Corpus Vocabulary Profiler")
st.write("Upload your Deucalion Lemmatizer CSV file to evaluate curriculum parameters and verify the 95% comprehension rule.")

# --- HELPER FUNCTIONS ---
@st.cache_data
def load_haverford_db(csv_path):
    """
    Loads your Haverford dataset up to rank 5000 only. 
    Resolves homograph collisions and filters out ultra-rare words.
    """
    rank_map = {}
    try:
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=',')
            for row in reader:
                if row.get("lemma") and row.get("bridge_rank"):
                    lemma = row["lemma"].lower().strip()
                    try:
                        new_rank = int(row["bridge_rank"])
                        
                        # DATA STRATEGY EXCLUSION: Only keep words in the Top 5000 core
                        if new_rank <= 5000:
                            # HOMOGRAPH PROTECTION: Always preserve the most common rank
                            if lemma in rank_map:
                                if new_rank < rank_map[lemma]:
                                    rank_map[lemma] = new_rank
                            else:
                                rank_map[lemma] = new_rank
                                
                    except ValueError:
                        continue
    except FileNotFoundError:
        st.error(f"Error: Database file '{csv_path}' not found in web server directory.")
    return rank_map

# --- CORE WEB INTERFACE AND LOGIC ---
rank_db = load_haverford_db(HAVERFORD_CSV_PATH)
uploaded_csv = st.file_uploader("Upload your Deucalion Lemmatizer CSV file", type=["csv"])

if uploaded_csv is not None and rank_db:
    csv_text = uploaded_csv.read().decode("utf-8-sig").splitlines()
    
    first_line = csv_text[0] if csv_text else ""
    delimiter_char = '\t' if '\t' in first_line else ','
    
    reader = csv.DictReader(csv_text, delimiter=delimiter_char)
    headers = reader.fieldnames if reader.fieldnames else []
    
    deuc_lemma_col = next((h for h in headers if h.lower().strip() == 'lemma'), None)
    deuc_pos_col = next((h for h in headers if h.lower().strip() in ['pos', 'part of speech']), None)
    deuc_token_col = next((h for h in headers if h.lower().strip() in ['form', 'word', 'token']), None)

    if not deuc_lemma_col and len(headers) >= 2:
        deuc_lemma_col = headers[1]
    if not deuc_token_col and len(headers) >= 1:
        deuc_token_col = headers[0]

    if deuc_lemma_col:
        # Re-balanced categories based on a hard 5,000 threshold
        categories = {
            "Core A1-B1\n(Rank 1-1000)": 0,
            "Bridge B2 Target\n(Rank 1001-4000)": 0,
            "Advanced Threshold\n(Rank 4001-5000)": 0,
            "Rare Vocabulary\n(Outside Top 5000)": 0
        }
        
        total_tokens = 0
        rare_words_list = []
        
        for row in reader:
            lemma = row.get(deuc_lemma_col, "").lower().strip()
            token = row.get(deuc_token_col, "").strip()
            pos = row.get(deuc_pos_col, "").upper().strip() if deuc_pos_col else ""
            
            if pos == "PUNC" or lemma == "punc" or not lemma:
                continue
                
            if "界" in lemma:
                lemma = lemma.split("界")[0]
                
            total_tokens += 1
            
            # Check rank map; if filtered out or missing, it returns 99999
            rank = rank_db.get(lemma, 99999)
            
            # Neuter-to-Masculine fallback safety check for adjective listings
            if rank == 99999 and lemma.endswith("um"):
                lemma_alt = lemma[:-2] + "us"
                rank = rank_db.get(lemma_alt, 99999)
                
            if rank <= 1000:
                categories["Core A1-B1\n(Rank 1-1000)"] += 1
            elif rank <= 4000:
                categories["Bridge B2 Target\n(Rank 1001-4000)"] += 1
            elif rank <= 5000:
                categories["Advanced Threshold\n(Rank 4001-5000)"] += 1
            else:
                categories["Rare Vocabulary\n(Outside Top 5000)"] += 1
                rare_words_list.append((token, lemma))

        if total_tokens > 0:
            labels = list(categories.keys())
            counts = list(categories.values())
            percentages = [(c / total_tokens) * 100 for c in counts]

            st.success(f"Analysis Complete! Processed {total_tokens:,} valid tokens inside 5k core framework.")
            
            # Metrics computation using list index slices
            comprehension_95_score = percentages[0] + percentages[1]
            rare_vocab_score = percentages[3]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="95% Rule Comprehension Score (Ranks 1-4000)", value=f"{comprehension_95_score:.1f}%")
            with col2:
                st.metric(label="Rare Vocabulary Rate (Outside 5k)", value=f"{rare_vocab_score:.1f}%")
                
            if comprehension_95_score >= 95.0:
                st.balloons()
                st.success("✅ This text complies with the 95% comprehension rule for your B2 curriculum!")
            else:
                st.warning("⚠️ This text falls below the 95% rule for pure independent reading. Requires classroom vocabulary bridging.")

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
        else:
            st.error("❌ No rows could be parsed. Check column content configuration layout.")
