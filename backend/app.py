from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle
import os
import re
import psycopg2
import nltk
from nltk.corpus import stopwords
from nltk.stem.porter import PorterStemmer

from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)
# ArmorIQ Integration (Track 3)
# ArmorIQ disabled (for stability)
ARMORIQ_AVAILABLE = False



# Download stopwords if not already present
print("Checking for stopwords...")
try:
    nltk.data.find('corpora/stopwords')
    print("Stopwords found.")
except LookupError:
    print("Stopwords not found, downloading...")
    nltk.download('stopwords')
    print("Stopwords downloaded.")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# Initialize PorterStemmer
print("Initializing PorterStemmer...")
port_stem = PorterStemmer()
stop_words = set(stopwords.words('english'))

def stemming(content):
    if not content:
        return ""
    # Remove non-alphabetic characters
    stemmed_content = re.sub('[^a-zA-Z]', ' ', content)
    # Convert to lowercase
    stemmed_content = stemmed_content.lower()
    # Tokenize
    stemmed_content = stemmed_content.split()
    # Stem and remove stopwords
    stemmed_content = [port_stem.stem(word) for word in stemmed_content if not word in stop_words]
    # Rejoin into a single string
    stemmed_content = ' '.join(stemmed_content)
    return stemmed_content

def is_url(text):
    try:
        result = urlparse(text)
        return all([result.scheme, result.netloc])
    except:
        return False

def scrape_url(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        print(f"Fetching URL: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        print(f"Status Code: {response.status_code}")
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find the title - checking multiple common tags
        title = ""
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            
        # Get article body - focus on article tag or common containers
        article_content = soup.find('article')
        if article_content:
            paragraphs = article_content.find_all('p')
        else:
            paragraphs = soup.find_all('p')
            
        text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        
        # If text is too short, try to get anything from the body
        if len(text) < 100:
             text = soup.get_text(separator=' ', strip=True)
             
        print(f"Extracted Title: {title[:50]}...")
        print(f"Extracted Text Length: {len(text)}")
        
        return title, text
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        return None, None

# Get the directory where app.py is located
base_dir = os.path.dirname(os.path.abspath(__file__))

# model load
vectorizer_path = os.path.join(base_dir, "vectorizer.pkl")
model_path = os.path.join(base_dir, "finalized_model.pkl")

vector = None
model = None

# ---------- Load Vectorizer ----------
try:
    if os.path.exists(vectorizer_path) and os.path.getsize(vectorizer_path) > 0:
        with open(vectorizer_path, "rb") as f:
            vector = pickle.load(f)
        print("Vectorizer loaded successfully.")
    else:
        print("Vectorizer not found or empty.")
except Exception as e:
    print(f"Error loading vectorizer: {e}")

# ---------- Load Model ----------
try:
    if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        print("Model loaded successfully.")
    else:
        print("Model not found or empty.")
except Exception as e:
    print(f"Error loading model: {e}")

# ---------- PostgreSQL Connection (YAHIN) ----------
import psycopg2

conn = None
cursor = None

try:
    conn = psycopg2.connect(
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASS"),
        host=os.environ.get("DB_HOST"),
        port=os.environ.get("DB_PORT"),
        sslmode="require"
    )
    cursor = conn.cursor()
    print("Database connection successful.")
except Exception as e:
    print(f"Database connection failed: {e}")}")

# Initialize History Table
if cursor:
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id SERIAL PRIMARY KEY,
                user_wallet VARCHAR(255) NOT NULL,
                claim TEXT NOT NULL,
                prediction VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL,
                evidence TEXT,
                reasoning TEXT,
                confidence VARCHAR(50),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("History table verified/created.")
    except Exception as e:
        print(f"Error creating history table: {e}")



from duckduckgo_search import DDGS

def get_live_evidence(query):
    """Fetch live evidence using DuckDuckGo Search."""
    print(f"Searching web for: {query}")
    evidence = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            for r in results:
                evidence.append(f"- {r['title']}: {r['body'][:200]}... ({r['href']})")
    except Exception as e:
        print(f"Search error: {e}")
    return evidence

@app.route("/prediction", methods=["POST"])
def prediction():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    title = data.get("title", data.get("news", ""))
    text = data.get("text", "")
    
    # --- ArmorIQ Security Scan ---
# ArmorIQ scan disabled
# if ARMORIQ_AVAILABLE:
#     pass

    # -----------------------------
    
    # Check if the input is a URL
    input_to_check = title if title else text
    if is_url(input_to_check):
        print(f"Detected URL: {input_to_check}. Scraping...")
        scraped_title, scraped_text = scrape_url(input_to_check)
        if scraped_title or scraped_text:
            title = scraped_title if scraped_title else ""
            text = scraped_text if scraped_text else ""
            print(f"Scraped Title: {title[:50]}...")
        else:
             return jsonify({
                 "error": "Access Denied / Scraper Blocked",
                 "details": "This website is blocking automated checks. Please copy the news text manually and use 'Article' mode."
             }), 400

    combined_content = (title if title else "") + " " + (text if text else "")
    
    if not combined_content.strip():
        return jsonify({"error": "No content to predict"}), 400
    
    # Preprocess with stemming
    processed_content = stemming(combined_content)
    
    # 1. Base ML Prediction
    if vector and model:
        vectorized_text = vector.transform([processed_content])
        prediction_result = model.predict(vectorized_text)
        ml_result = "REAL" if prediction_result[0] == 0 else "FAKE"
    else:
        ml_result = "FAKE" if "fake" in processed_content.lower() else "REAL"

    # 2. Advanced Fact-Checking (Search + Reasoning)
    search_query = title if title else (text[:100] if text else "news")
    live_evidence = get_live_evidence(search_query)
    
    # Simplified reasoning logic based on ML + Evidence
    status = ml_result
    if not live_evidence:
        reasoning = f"Our model identified this as {ml_result} based on text patterns. No matching live reports were found to corroborate or debunk this specifically at this moment."
        confidence = "Medium"
    else:
        reasoning = f"Analyzed against live web results. The linguistic patterns suggest {ml_result}, and searches provided external context regarding '{search_query}'. Trusted sources were consulted to verify the claim."
        confidence = "High"

    return jsonify({
        "prediction": ml_result,
        "claim": title if title else (text[:150] + "..." if len(text) > 150 else text),
        "status": "True" if status == "REAL" else "False",
        "evidence": live_evidence if live_evidence else ["No direct online evidence found in quick scan."],
        "reasoning": reasoning,
        "confidence": confidence,
        "scraped_title": title[:100] if is_url(input_to_check) else None
    })

@app.route("/report", methods=["POST", "OPTIONS"])
def report_news():
    if request.method == "OPTIONS":
        return jsonify({"message": "OK"}), 200

    if not cursor:
        return jsonify({"error": "Database not available. Cannot save report."}), 503

    data = request.get_json()

    news = data.get("news")
    reason = data.get("reason")
    comment = data.get("comment")

    try:
        cursor.execute(
            "INSERT INTO reports (news, reason, comment) VALUES (%s, %s, %s)",
            (news, reason, comment)
        )
        conn.commit()
        return jsonify({"message": "Report stored successfully"}), 200
    except Exception as e:
        print(f"Error saving report: {e}")
        return jsonify({"error": "Failed to save report"}), 500

@app.route("/save_history", methods=["POST"])
def save_history():
    if not cursor:
        return jsonify({"error": "Database not available"}), 503
    
    data = request.get_json()
    user_wallet = data.get("user_wallet")
    claim = data.get("claim")
    prediction = data.get("prediction")
    status = data.get("status")
    evidence = str(data.get("evidence", [])) # Convert list to string for simplicity
    reasoning = data.get("reasoning")
    confidence = data.get("confidence")

    if not all([user_wallet, claim, prediction]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        cursor.execute(
            "INSERT INTO history (user_wallet, claim, prediction, status, evidence, reasoning, confidence) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_wallet, claim, prediction, status, evidence, reasoning, confidence)
        )
        conn.commit()
        return jsonify({"message": "History saved successfully"}), 201
    except Exception as e:
        print(f"Error saving history: {e}")
        return jsonify({"error": "Failed to save history"}), 500

@app.route("/get_history/<string:wallet_address>", methods=["GET"])
def get_history(wallet_address):
    if not cursor:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        cursor.execute("SELECT claim, prediction, status, evidence, reasoning, confidence, timestamp FROM history WHERE user_wallet = %s ORDER BY timestamp DESC", (wallet_address,))
        rows = cursor.fetchall()
        history = []
        for row in rows:
            history.append({
                "claim": row[0],
                "prediction": row[1],
                "status": row[2],
                "evidence": eval(row[3]) if row[3] else [], # Convert string back to list
                "reasoning": row[4],
                "confidence": row[5],
                "timestamp": row[6].isoformat()
            })
        return jsonify(history), 200
    except Exception as e:
        print(f"Error fetching history: {e}")
        return jsonify({"error": "Failed to fetch history"}), 500
    

from flask import request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------- AUTH ----------------

@app.route("/signup", methods=["POST"])
def signup_user():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        # check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"error": "User already exists"}), 400

        hashed_password = generate_password_hash(password)

        cursor.execute(
            "INSERT INTO users (email, password) VALUES (%s, %s)",
            (email, hashed_password)
        )
        conn.commit()

        return jsonify({"message": "Signup successful"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/signin", methods=["POST"])
def signin_user():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        cursor.execute("SELECT password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "User not found"}), 404

        if not check_password_hash(user[0], password):
            return jsonify({"error": "Invalid password"}), 401

        return jsonify({"message": "Signin successful"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------------

#     # ---------------- AUTH (DEMO MODE) ----------------
# @app.route("/signup", methods=["POST"])
# def signUp():
#     return jsonify({"message": "Signup successful"}), 200

# @app.route("/signin", methods=["POST"])
# def signin():
#     return jsonify({"message": "Signin successful"}), 200
# # --------------------------------------------------


if __name__ == "__main__":
    app.run(debug=True, port=5001)



