import streamlit as st
try:
    import google.generativeai as genai
except ModuleNotFoundError:
    st.error("⚠️ O módulo 'google-generativeai' não foi encontrado. Por favor, certifique-se de estar usando o ambiente virtual (venv) executando o script `run_dashboard.ps1`.")
    st.stop()

import PyPDF2
from docx import Document
import pandas as pd
import sqlite3
import os
import io
import yaml
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import litellm
import html as html_lib
from auth import hash_password, verify_password, validate_password_strength, validate_email_format, verify_token

# ── Módulos do Agente ──────────────────────────────────────────────────────
from memory.agent_memory import AgentMemory
from agent.react_agent import run_react_agent, TOOL_DESCRIPTIONS

# Load environment variables
load_dotenv()

# Configure API Keys for LiteLLM
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")
os.environ["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")

# ── LiteLLM Configuration ──────────────────────────────────────────────────
# Disable telemetry to avoid [WinError 233] on Windows pipes
litellm.telemetry = False
litellm.drop_params = True
litellm.success_callback = []
litellm.failure_callback = []
# litellm.set_verbose = True # Uncomment for deep debugging

# Configure Gemini Native (optional fallback)
if os.environ["GEMINI_API_KEY"]:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

PROMPTS_DIR = Path(__file__).parent / "prompts"


# ── DATABASE SETUP ─────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('legal_history.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  client TEXT,
                  date TEXT,
                  type TEXT,
                  result TEXT,
                  file_name TEXT,
                  status TEXT DEFAULT 'Pendente',
                  notes TEXT)''')
    for col in [
        "ALTER TABLE history ADD COLUMN status TEXT DEFAULT 'Pendente'",
        "ALTER TABLE history ADD COLUMN notes TEXT",
        "ALTER TABLE history ADD COLUMN user_id INTEGER",
    ]:
        try:
            c.execute(col)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def init_users_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email_confirmed INTEGER DEFAULT 0,
            confirmation_token TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Migration: adicionar colunas novas se tabela já existe
    for col_sql in [
        "ALTER TABLE users ADD COLUMN email_confirmed INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN confirmation_token TEXT",
        "ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP",
    ]:
        try:
            c.execute(col_sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def criar_usuario(nome, email, senha):
    """Cria novo usuário com senha hashada via bcrypt e valida e-mail."""
    if not validate_email_format(email):
        return False, "Formato de e-mail inválido"

    # Validar força da senha
    is_valid, msg = validate_password_strength(senha)
    if not is_valid:
        return False, msg

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        hashed = hash_password(senha)
        c.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (nome, email, hashed)
        )
        conn.commit()
        return True, "OK"
    except sqlite3.IntegrityError:
        return False, "Email já cadastrado"
    except Exception as e:
        return False, f"Erro ao criar conta: {str(e)}"
    finally:
        conn.close()


def validar_login(email, senha):
    """Valida login verificando senha contra hash bcrypt armazenado."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute(
        "SELECT id, name, email, password FROM users WHERE email = ?",
        (email,)
    )
    user = c.fetchone()
    conn.close()

    if not user:
        return None

    if verify_password(senha, user[3]):
        return user  # (id, name, email, password_hash)
    return None


# ── SECURITY HELPERS ──────────────────────────────────────────────────────

def safe_html(text: str) -> str:
    """Escapa HTML no conteúdo para prevenir XSS."""
    return html_lib.escape(str(text))


def validate_upload(uploaded_file) -> tuple:
    """
    Valida tipo MIME real e tamanho do arquivo upload.
    Returns: (is_valid: bool, message: str)
    """
    MAX_SIZE = 5 * 1024 * 1024  # 5MB

    if uploaded_file.size > MAX_SIZE:
        size_mb = uploaded_file.size / (1024 * 1024)
        return False, f"Arquivo excede o limite de 5MB ({size_mb:.1f}MB)"

    # Verificar magic bytes (assinatura real do arquivo)
    header = uploaded_file.read(8)
    uploaded_file.seek(0)

    if uploaded_file.name.endswith('.pdf') and not header.startswith(b'%PDF'):
        return False, "Arquivo não é um PDF válido (assinatura incorreta)"
    if uploaded_file.name.endswith('.docx') and not header.startswith(b'PK'):
        return False, "Arquivo não é um DOCX válido (assinatura incorreta)"

    return True, "OK"


def save_to_history(client, contract_type, result, file_name, status='Pendente', user_id=None):
    conn = sqlite3.connect('legal_history.db')
    c = conn.cursor()
    date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.execute(
        "INSERT INTO history (user_id, client, date, type, result, file_name, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, client, date, contract_type, result, file_name, status)
    )
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_analysis_status(analysis_id, status, notes=None):
    conn = sqlite3.connect('legal_history.db')
    c = conn.cursor()
    if notes:
        c.execute("UPDATE history SET status = ?, notes = ? WHERE id = ?", (status, notes, analysis_id))
    else:
        c.execute("UPDATE history SET status = ? WHERE id = ?", (status, analysis_id))
    conn.commit()
    conn.close()


def get_history(user_id=None):
    conn = sqlite3.connect('legal_history.db')
    if user_id is not None:
        df = pd.read_sql_query(
            "SELECT * FROM history WHERE user_id = ? ORDER BY id DESC",
            conn,
            params=(user_id,)
        )
    else:
        df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
    conn.close()
    return df


def reset_db(user_id=None):
    conn = sqlite3.connect('legal_history.db')
    c = conn.cursor()
    if user_id is not None:
        c.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
    else:
        c.execute("DROP TABLE IF EXISTS history")
    conn.commit()
    conn.close()
    if user_id is None:
        init_db()


# ── PROMPT LOADER ──────────────────────────────────────────────────────────
def load_prompt(filename: str) -> str:
    """Carrega um template de prompt do arquivo YAML em /prompts/."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        st.error(f"Arquivo de prompt não encontrado: {path}")
        return ""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("template", "")


def render_prompt(template: str, **kwargs) -> str:
    """Renderiza um template substituindo {variáveis}."""
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template


# ── UI STYLING ─────────────────────────────────────────────────────────────
def apply_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Outfit:wght@400;700&display=swap');

    :root {
        --primary: #2563eb;
        --primary-dark: #1e40af;
        --bg: #f8fafc;
        --card-bg: rgba(255, 255, 255, 0.8);
        --text: #0f172a;
        --react-bg: #0f172a;
        --react-accent: #6366f1;
    }

    .stApp {
        background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
        font-family: 'Inter', sans-serif;
    }

    .glass-card {
        background: var(--card-bg);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.3);
        border-radius: 24px;
        padding: 2rem;
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05), 0 8px 10px -6px rgba(0,0,0,0.05);
        margin-bottom: 2rem;
    }

    h1, h2, h3 { font-family: 'Outfit', sans-serif; color: #1e293b; font-weight: 700; }

    .stButton>button {
        background: linear-gradient(90deg, var(--primary) 0%, var(--primary-dark) 100%);
        color: white; border: none; border-radius: 12px;
        padding: 0.75rem 1.5rem; font-weight: 700;
        transition: all 0.3s ease;
        box-shadow: 0 10px 15px -3px rgba(37,99,235,0.3);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 20px 25px -5px rgba(37,99,235,0.4);
    }

    /* ── ReAct Badge ─────────────────────── */
    .react-badge {
        display: inline-flex; align-items: center; gap: 6px;
        background: linear-gradient(90deg, #6366f1, #8b5cf6);
        color: white; font-size: 0.7rem; font-weight: 700;
        padding: 3px 10px; border-radius: 20px; letter-spacing: 0.08em;
        text-transform: uppercase; margin-left: 8px;
    }

    /* ── ReAct Scratchpad ────────────────── */
    .scratchpad-container {
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.25rem;
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        line-height: 1.7;
        color: #94a3b8;
        max-height: 400px;
        overflow-y: auto;
    }
    .scratchpad-thought  { color: #fbbf24; }
    .scratchpad-action   { color: #34d399; }
    .scratchpad-obs      { color: #60a5fa; }
    .scratchpad-final    { color: #f472b6; font-weight: bold; }

    /* ── Tool Pills ──────────────────────── */
    .tool-pill {
        display: inline-block;
        background: rgba(99,102,241,0.15);
        color: #6366f1; border: 1px solid rgba(99,102,241,0.3);
        border-radius: 999px; padding: 2px 10px;
        font-size: 0.75rem; font-weight: 600; margin: 2px;
    }

    /* ── Chat ────────────────────────────── */
    .chat-bubble {
        padding: 1.2rem; border-radius: 20px; margin-bottom: 1.5rem;
        max-width: 80%; font-size: 0.95rem; line-height: 1.6;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); position: relative;
    }
    .chat-user {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white; margin-left: auto; border-bottom-right-radius: 4px;
    }
    .chat-assistant {
        background: #ffffff; color: var(--text);
        border-bottom-left-radius: 4px;
        border: 1px solid #e2e8f0; margin-right: auto;
    }
    .assistant-label {
        font-size: 0.75rem; font-weight: 700; color: #64748b;
        margin-bottom: 4px; margin-left: 5px;
        text-transform: uppercase; letter-spacing: 0.05em;
    }

    /* ── Status ──────────────────────────── */
    .status-pulse {
        width: 10px; height: 10px; background: #10b981;
        border-radius: 50%; display: inline-block; margin-right: 8px;
        box-shadow: 0 0 0 rgba(16,185,129,0.4); animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%   { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16,185,129,.7); }
        70%  { transform: scale(1);    box-shadow: 0 0 0 10px rgba(16,185,129,0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16,185,129,0); }
    }

    .scrollable-doc {
        background: white; padding: 2rem; border-radius: 12px;
        border: 1px solid #e2e8f0; font-size: 0.95rem; line-height: 1.6;
        color: #334155; height: 1000px; overflow-y: auto;
        white-space: pre-wrap; box-shadow: inset 0 2px 4px 0 rgba(0,0,0,0.05);
    }
    .analysis-container { height: 1000px; overflow-y: auto; padding-right: 10px; }

    .chat-header {
        background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
        color: white; padding: 0.75rem 1.25rem;
        border-radius: 12px 12px 0 0;
        display: flex; justify-content: space-between; align-items: center;
        font-weight: 600; margin-bottom: 0px;
    }
    .chat-buttons-row { background: #334155; padding: 0 1rem 0.5rem 1rem; margin-top: -1px; }
    .chat-container {
        background: rgba(255,255,255,0.95);
        border: 1px solid #e2e8f0; border-radius: 0 0 12px 12px;
        padding: 1rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-top: 0px;
    }

    /* ── Memory Card ─────────────────────── */
    .memory-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #334155; border-radius: 12px;
        padding: 0.75rem 1rem; margin-bottom: 0.5rem;
        font-size: 0.8rem; color: #94a3b8;
    }
    .memory-card strong { color: #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)


# ── LLM CORE ──────────────────────────────────────────────────────────────
def call_llm(provider, model_name, messages):
    try:
        if provider == "Gemini":
            full_model = f"gemini/{model_name}"
        elif provider == "Groq":
            full_model = f"groq/{model_name}"
        elif provider == "OpenRouter":
            full_model = f"openrouter/{model_name}"
        else:
            full_model = model_name

        response = litellm.completion(model=full_model, messages=messages, temperature=0.2)
        
        # Log usage to terminal if available
        if hasattr(response, 'usage'):
            usage = {
                'prompt': response.usage.prompt_tokens,
                'completion': response.usage.completion_tokens,
                'total': response.usage.total_tokens
            }
            # Print to terminal for developer monitoring
            print(f"\n[TOKEN USAGE] Model: {full_model}")
            print(f"  - Prompt:     {usage['prompt']}")
            print(f"  - Completion: {usage['completion']}")
            print(f"  - Total:      {usage['total']}\n")
            
            st.session_state.last_usage = usage
            
        return response.choices[0].message.content
    except Exception as e:
        return f"Erro ao chamar o modelo ({provider}): {str(e)}"


# ── TEXT EXTRACTION ────────────────────────────────────────────────────────
def extract_text(uploaded_file):
    """
    Extrai texto de documentos PDF/DOCX.
    Usa IBM Docling para extração estruturada (Markdown) com fallback para PyPDF2/docx.
    """
    # Lógica de reserva (Fallback) caso o Docling falhe
    def fallback_extract():
        uploaded_file.seek(0)
        if uploaded_file.name.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            return "".join(page.extract_text() or "" for page in pdf_reader.pages)
        elif uploaded_file.name.endswith('.docx'):
            doc = Document(uploaded_file)
            return "\n".join(para.text for para in doc.paragraphs)
        return ""

    try:
        from docling.document_converter import DocumentConverter
        from pathlib import Path
        import os

        # Salvar buffer em arquivo temporário (Docling requer path físico)
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / uploaded_file.name
        
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # Converter usando Docling
        converter = DocumentConverter()
        result = converter.convert(str(temp_path))
        markdown_text = result.document.export_to_markdown()
        
        # Limpeza
        if temp_path.exists():
            os.remove(temp_path)
            
        return markdown_text
        
    except Exception as e:
        # Se Docling falhar (ex: falta de memória ou erro de import), usa o método padrão
        print(f"[EXTRACTOR] Docling não disponível ou erro no processamento: {str(e)}")
        return fallback_extract()


# ── SCRATCHPAD RENDERER ────────────────────────────────────────────────────
def render_scratchpad_html(scratchpad: str) -> str:
    """Converte o scratchpad de texto do ReAct em HTML colorido."""
    import html as html_lib
    lines = scratchpad.split("\n")
    html_lines = []
    for line in lines:
        safe = html_lib.escape(line)
        if safe.startswith("Thought:"):
            html_lines.append(f'<span class="scratchpad-thought">{safe}</span>')
        elif safe.startswith("Action:"):
            html_lines.append(f'<span class="scratchpad-action">{safe}</span>')
        elif safe.startswith("Action Input:"):
            html_lines.append(f'<span class="scratchpad-action" style="opacity:0.8">{safe}</span>')
        elif safe.startswith("Observation:"):
            html_lines.append(f'<span class="scratchpad-obs">{safe}</span>')
        elif safe.startswith("Final Answer:"):
            html_lines.append(f'<span class="scratchpad-final">{safe}</span>')
        else:
            html_lines.append(safe)
    return '<br>'.join(html_lines)


# ── TELA DE LOGIN ────────────────────────────────────────────────────────
def render_login_screen():
    st.markdown("""
    <style>
    [data-testid="stSidebar"], [data-testid="stHeader"] { display: none !important; }
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(to right, #e2e2e2, #c9d6ff) !important;
        font-family: 'Montserrat', sans-serif !important;
    }
    [data-testid="column"]:nth-of-type(2) {
        background-color: #fff;
        border-radius: 30px;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.35);
        padding: 40px 20px;
        margin-top: 5vh;
        text-align: center;
    }
    [data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    [data-testid="stMarkdownContainer"] { text-align: center; }
    div[data-baseweb="input"] {
        background-color: #eee;
        border: none;
        border-radius: 8px;
    }
    div[data-baseweb="input"] input {
        background-color: transparent !important;
        padding: 10px 15px;
        font-size: 13px;
    }
    [data-testid="stFormSubmitButton"] > button {
        background-color: #512da8 !important;
        color: #fff !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px;
        text-transform: uppercase !important;
        padding: 10px 45px !important;
        font-size: 12px !important;
        border: none !important;
        box-shadow: none !important;
        margin-top: 15px;
        width: 100%;
        cursor: pointer;
    }
    div[data-testid="stTabs"] button { flex: 1; font-weight: bold; }
    .social-icons-login { display: flex; justify-content: center; gap: 15px; margin: 15px 0; }
    .s-icon {
        border: 1px solid #ccc; border-radius: 20%;
        display: inline-flex; justify-content: center; align-items: center;
        width: 40px; height: 40px; color: #333; text-decoration: none; font-size: 18px;
    }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown('<h1 style="font-weight:700;font-size:28px;color:#333;margin-bottom:5px;">VencIA Agent Legal</h1>', unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔒 Login", "📝 Criar Conta"])

        with tab_login:
            st.markdown('<h2 style="color:#333;">Acessar</h2>', unsafe_allow_html=True)
            st.markdown('''
            <div class="social-icons-login">
                <a href="#" class="s-icon"><i class="fa-brands fa-google"></i></a>
                <a href="#" class="s-icon"><i class="fa-brands fa-microsoft"></i></a>
            </div>
            <span style="font-size:12px;color:#666;">ou use seu email e senha</span>
            ''', unsafe_allow_html=True)
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("Email", placeholder="Email", label_visibility="collapsed")
                senha = st.text_input("Senha", type="password", placeholder="Senha", label_visibility="collapsed")
                st.markdown('<a href="#" style="font-size:13px;color:#333;text-decoration:none;display:block;margin:10px 0;">Esqueceu sua Senha?</a>', unsafe_allow_html=True)
                if st.form_submit_button("LOGIN"):
                    user = validar_login(email, senha)
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.user = user[1]  # nome
                        st.session_state.user_id = user[0]  # id (multi-tenancy)
                        st.rerun()
                    else:
                        st.error("Email ou senha inválidos")

        with tab_register:
            st.markdown('<h2 style="color:#333;">Criar Conta</h2>', unsafe_allow_html=True)
            st.markdown('''
            <div class="social-icons-login">
                <a href="#" class="s-icon"><i class="fa-brands fa-google"></i></a>
                <a href="#" class="s-icon"><i class="fa-brands fa-microsoft"></i></a>
            </div>
            <span style="font-size:12px;color:#666;">ou use seu email para cadastro</span>
            ''', unsafe_allow_html=True)
            with st.form("register_form", clear_on_submit=True):
                nome = st.text_input("Nome", placeholder="Nome", label_visibility="collapsed")
                email_r = st.text_input("Email", placeholder="Email", label_visibility="collapsed")
                senha_r = st.text_input("Senha", type="password", placeholder="Senha", label_visibility="collapsed")
                if st.form_submit_button("CRIAR CONTA"):
                    if not nome or not email_r or not senha_r:
                        st.error("❌ Preencha todos os campos")
                    else:
                        success, msg = criar_usuario(nome, email_r, senha_r)
                        if success:
                            st.success("✅ Conta criada com sucesso! Faça login para continuar.")
                        else:
                            st.error(f"❌ {msg}")


# ── MAIN APP ───────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="VencIA Agent Legal | Analisador de Contratos",
        page_icon="⚖️",
        layout="wide"
    )

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # ── Handle JWT Token from FastAPI Handoff ──
    query_params = st.query_params
    if "token" in query_params:
        token = query_params["token"]
        payload = verify_token(token)
        if payload:
            st.session_state.logged_in = True
            st.session_state.user = payload.get("name", "Usuário")
            st.session_state.user_id = payload.get("user_id")
            # Clear token from URL for security
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Token Inválido ou Expirado. Faça login novamente.")

    if not st.session_state.logged_in:
        st.markdown("""
            <div style="text-align: center; margin-top: 100px;">
                <h2>🚨 Acesso Restrito</h2>
                <p>Você precisa estar autenticado no portal para acessar o Dashboard.</p>
                <a href="http://localhost:8080" target="_self">
                    <button style="background-color: #1a56db; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer;">
                        Ir para Tela de Login
                    </button>
                </a>
                <p style="font-size: 12px; color: #888; margin-top: 20px;">Redirecionando automaticamente em 3 segundos...</p>
            </div>
            <script>
                setTimeout(function() {
                    window.location.href = "http://localhost:8080";
                }, 3000);
            </script>
        """, unsafe_allow_html=True)
        st.stop()

    apply_custom_css()
    init_db()
    init_users_db()

    # ── Sidebar ────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"### <div class='status-pulse'></div> VencIA Agent Legal",
            unsafe_allow_html=True
        )
        st.caption("Especialista em Contratos B2B")
        st.divider()

        st.subheader("🧠 Configuração de IA")
        provider = st.selectbox("Provedor", ["Groq", "Gemini", "OpenRouter"])

        if provider == "Groq":
            model_name = st.selectbox(
                "Modelo", ["llama-3.3-70b-versatile", "llama-4-scout-17b", "llama-3.1-8b-instant"]
            )
        elif provider == "Gemini":
            model_name = st.selectbox(
                "Modelo", ["gemini-2.0-flash", "gemini-2.5-flash-preview-04-17", "gemini-pro-latest"]
            )
        elif provider == "OpenRouter":
            model_name = st.selectbox(
                "Modelo",
                ["meta-llama/llama-3.3-70b-instruct:free", "google/gemma-2-9b-it:free",
                 "mistralai/mistral-7b-instruct:free"]
            )



        st.divider()

            
        st.divider()
        menu = st.radio(
            "Navegação",
            ["Novo Dossiê", "Histórico de Análises", "🧠 Memória do Agente"],
            label_visibility="collapsed"
        )

        st.divider()
        st.info(f"💡 **Dica:** Provedor **{provider}** ativo.")

        st.divider()
        st.subheader("🗑️ Limpar Banco")
        if st.button("Limpar Histórico de Análises", type="secondary"):
            st.session_state.confirm_reset = True

        if st.session_state.get('confirm_reset'):
            st.warning("⚠️ Tem certeza? Isso apagará todas as análises permanentes.")
            col_res1, col_res2 = st.columns(2)
            if col_res1.button("✅ Sim", key="confirm_yes"):
                reset_db(user_id=st.session_state.get('user_id'))
                st.session_state.confirm_reset = False
                st.session_state.pop('last_analysis', None)
                st.session_state.pop('messages', None)
                st.session_state.pop('agent_session_id', None)
                st.success("Histórico resetado!")
                st.rerun()
            if col_res2.button("❌ Não", key="confirm_no"):
                st.session_state.confirm_reset = False
                st.rerun()

        st.divider()
        st.subheader("🚪 Minha Conta")
        st.write(f"Logado como: **{st.session_state.get('user', 'Usuário')}**")
        if st.button("Sair (Logoff)", type="primary"):
            st.session_state.logged_in = False
            st.session_state.pop("user", None)
            st.session_state.pop("user_id", None)
            st.markdown('<script>window.location.href = "http://localhost:8080";</script>', unsafe_allow_html=True)
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # PÁGINA: NOVO DOSSIÊ
    # ══════════════════════════════════════════════════════════════════════
    if menu == "Novo Dossiê":
        st.markdown("<h1>🛡️ Novo Dossiê Jurídico</h1>", unsafe_allow_html=True)
        st.write("Carregue um contrato para análise.")

        col1, col2 = st.columns([2, 1])

        with col1:
            with st.container():
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                client_name = c1.text_input("Cliente / Fornecedor", placeholder="Ex: Acme Corp Ltda")
                contract_type = c2.selectbox(
                    "Tipo de Contrato",
                    ["Prestação de Serviços", "NDA (Confidencialidade)",
                     "Aditivo Contratual", "Licenciamento de Software"]
                )
                uploaded_file = st.file_uploader("Upload do Documento (PDF ou DOCX)", type=["pdf", "docx"])


                # ── Rodapé do Card com Botões Alinhados à Direita ──────────────
                st.markdown('<div style="margin-top: 2rem;"></div>', unsafe_allow_html=True)
                footer_col1, footer_col2, footer_col3 = st.columns([2, 0.5, 1])
                
                with footer_col2:
                    if st.button("Cancelar", key="cancel_analysis", use_container_width=True):
                        st.rerun()

                with footer_col3:
                    if st.button("🚀 Gerar Análise de Risco", key="generate_analysis", use_container_width=True):
                        if uploaded_file and client_name:
                            # ── Validação de Segurança do Upload ──
                            is_valid, val_msg = validate_upload(uploaded_file)
                            if not is_valid:
                                st.error(f"❌ {val_msg}")
                                st.stop()
                            spinner_msg = f"⚖️ Jurix ({provider}) está raciocinando sobre o documento..."
                            with st.spinner(spinner_msg):
                                text = extract_text(uploaded_file)
                                if text:
                                    # ── Gerar session_id de memória ────────────────
                                    session_id = AgentMemory.make_session_id(client_name)
                                    st.session_state.agent_session_id = session_id
                                    memory = AgentMemory(session_id=session_id, user_id=st.session_state.get('user_id'))

                                    # ── MODO AGENTE (prompt YAML com CoT embutido) ──
                                    analyst_template = load_prompt("system_analyst.yaml")
                                    system_prompt = render_prompt(
                                        analyst_template,
                                        contract_text=text[:30000],
                                        contract_type=contract_type,
                                        client_name=client_name
                                    )
                                    messages = [
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": "Execute a análise jurídica completa."}
                                    ]
                                    result = call_llm(provider, model_name, messages)

                                    # ── Salvar no histórico e memória ──────────────
                                    st.session_state.last_analysis = result
                                    st.session_state.contract_text = text
                                    st.session_state.client_name = client_name
                                    st.session_state.contract_type = contract_type
                                    st.session_state.last_id = save_to_history(
                                        client_name, contract_type, result, uploaded_file.name,
                                        user_id=st.session_state.get('user_id')
                                    )
                                    st.session_state.validation_submitted = False
                                    memory.add_message(
                                        "user",
                                        f"[Análise solicitada] Contrato: {uploaded_file.name}",
                                        metadata={"history_id": st.session_state.last_id}
                                    )
                                    memory.add_message(
                                        "assistant",
                                        result[:2000],  # Resumo para memória
                                        metadata={"history_id": st.session_state.last_id, "full": False}
                                    )
                                    st.success("Análise concluída com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Não foi possível extrair texto do arquivo.")
                        else:
                            st.warning("Preencha o nome do cliente e faça o upload do arquivo.")
                
                st.markdown('</div>', unsafe_allow_html=True)


        # ── Resultados ─────────────────────────────────────────────────────
        if 'last_analysis' in st.session_state:
            st.divider()
            res_col1, res_col2 = st.columns([1, 1])

            with res_col1:
                st.markdown("### 📝 Documento Original")
                st.markdown(
                    f'<div class="scrollable-doc">{safe_html(st.session_state.contract_text)}</div>',
                    unsafe_allow_html=True
                )

            with res_col2:
                st.markdown("### 🔍 Parecer Jurídico")
                st.markdown(
                    f'<div class="analysis-container">{st.session_state.last_analysis}</div>',
                    unsafe_allow_html=True
                )

                # ── Validação Interativa ────────────────────────────────────
                st.divider()
                st.markdown("### ✅ Validação Final")

                if st.session_state.get('validation_submitted'):
                    st.success("✅ Resposta de validação registrada com sucesso!")
                else:
                    v_col1, v_col2 = st.columns(2)
                    if v_col1.button("👍 Sim (Validar)", use_container_width=True):
                        update_analysis_status(st.session_state.last_id, "Validado")
                        st.session_state.validation_submitted = True
                        st.rerun()

                    if v_col2.button("👎 Não (Reavaliar)", use_container_width=True):
                        st.session_state.show_revaluation = True

                    if st.session_state.get('show_revaluation'):
                        reval_notes = st.text_area(
                            "O que precisa ser reavaliado?",
                            placeholder="Descreva aqui os pontos que deseja ajustar..."
                        )
                        if st.button("🚀 Iniciar Nova Análise com Reavaliação"):
                            with st.spinner("⚖️ Reavaliando contrato com base nas suas notas..."):
                                reval_messages = [
                                    {"role": "system", "content": load_prompt("system_analyst.yaml")},
                                    {"role": "user", "content": f"=== CONTRATO ===\n{st.session_state.contract_text}"},
                                    {"role": "assistant", "content": st.session_state.last_analysis},
                                    {"role": "user", "content": (
                                        f"REAVALIAÇÃO SOLICITADA: {reval_notes}\n\n"
                                        "Por favor, refaça a análise incorporando estas observações. "
                                        "Mantenha o formato original."
                                    )}
                                ]
                                new_result = call_llm(provider, model_name, reval_messages)
                                st.session_state.last_analysis = new_result
                                update_analysis_status(st.session_state.last_id, "Reavaliado", reval_notes)
                                conn = sqlite3.connect('legal_history.db')
                                c_conn = conn.cursor()
                                c_conn.execute(
                                    "UPDATE history SET result = ? WHERE id = ?",
                                    (new_result, st.session_state.last_id)
                                )
                                conn.commit()
                                conn.close()
                                st.session_state.show_revaluation = False
                                st.success("Nova análise gerada com sucesso!")
                                st.rerun()

                # ── Chat Jurix com Memória ─────────────────────────────────
                st.markdown("---")
                if "chat_visible" not in st.session_state:
                    st.session_state.chat_visible = True
                if "chat_minimized" not in st.session_state:
                    st.session_state.chat_minimized = False

                if st.session_state.chat_visible:
                    st.markdown("<br>", unsafe_allow_html=True)
                    col_t1, col_t2, col_t3 = st.columns([8.5, 0.75, 0.75])
                    with col_t1:
                        st.markdown(
                            """
                            <div style="font-family:'Outfit', sans-serif; font-size:1.4rem; font-weight:700; color:#0f172a; display:flex; align-items:center; gap:8px;">
                                <div style="background:linear-gradient(135deg, #2563eb, #1e40af); border-radius:8px; padding:6px 10px; color:white; font-size:1rem; box-shadow:0 4px 6px rgba(37,99,235,0.2);">🤖</div>
                                Jurix Assistant
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                    with col_t2:
                        label = "🔼" if st.session_state.chat_minimized else "🔽"
                        if st.button(label, key="min_chat", use_container_width=True):
                            st.session_state.chat_minimized = not st.session_state.chat_minimized
                            st.rerun()
                    with col_t3:
                        if st.button("❌", key="close_chat", use_container_width=True):
                            st.session_state.chat_visible = False
                            st.session_state.messages = []
                            st.rerun()

                    if not st.session_state.chat_minimized:
                        # Chat Container Nativo (Limpo e Minimalista com Glassmorphism leve via CSS)
                        with st.container(border=True):
                            st.markdown("""
                            <style>
                                /* Input Field Styling - Highlight Suave em Azul */
                                .stChatInputContainer {
                                    border-radius: 16px !important;
                                    border: 1px solid #cbd5e1 !important;
                                    transition: all 0.3s ease;
                                    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02) !important;
                                }
                                .stChatInputContainer:focus-within {
                                    border: 1px solid #2563eb !important;
                                    box-shadow: 0 0 0 3px rgba(37,99,235,0.15) !important;
                                }
                            </style>
                            """, unsafe_allow_html=True)
                        if "messages" not in st.session_state:
                            st.session_state.messages = []

                        jurix_avatar = "assets/jurix_avatar.png" if os.path.exists("assets/jurix_avatar.png") else "🤖"
                        
                        # Mensagem de Boas vindas inicial
                        if len(st.session_state.messages) == 0:
                            with st.chat_message("assistant", avatar=jurix_avatar):
                                st.markdown("Olá! Sou o Jurix. Analisei o contrato. Em que posso te ajudar com as cláusulas hoje?")

                        # Loop do histórico visual
                        for message in st.session_state.messages:
                            avatar = jurix_avatar if message["role"] == "assistant" else "🧑‍💼"
                            with st.chat_message(message["role"], avatar=avatar):
                                st.markdown(message["content"])

                        if prompt := st.chat_input("Tire dúvidas sobre este contrato..."):
                            st.session_state.messages.append({"role": "user", "content": prompt})

                            # Recuperar memória persistente da sessão
                            session_id = st.session_state.get(
                                'agent_session_id',
                                AgentMemory.make_session_id(
                                    st.session_state.get('client_name', 'sessao')
                                )
                            )
                            memory = AgentMemory(session_id=session_id, user_id=st.session_state.get('user_id'))
                            history_text = memory.get_history_as_text(limit=10)

                            with st.spinner("Jurix está pensando..."):
                                chat_template = load_prompt("chat_jurix.yaml")
                                if chat_template:
                                    chat_prompt = render_prompt(
                                        chat_template,
                                        contract_text=st.session_state.contract_text[:8000],
                                        history=history_text,
                                        question=prompt,
                                        client_name=st.session_state.get('client_name', 'N/A')
                                    )
                                    messages = [{"role": "user", "content": chat_prompt}]
                                else:
                                    # Fallback
                                    messages = [
                                        {"role": "system", "content": (
                                            f"Você é Jurix, assistente jurídico. "
                                            f"Contexto do contrato: {st.session_state.contract_text[:8000]}"
                                        )},
                                        {"role": "user", "content": prompt}
                                    ]
                                response = call_llm(provider, model_name, messages)
                                st.session_state.messages.append(
                                    {"role": "assistant", "content": response}
                                )
                                # Persistir na memória
                                memory.add_message("user", prompt)
                                memory.add_message("assistant", response)
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("🙏 Obrigado por utilizar o Jurix! O atendimento foi encerrado.")
                    if st.button("Reabrir Chat para novas dúvidas"):
                        st.session_state.chat_visible = True
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # PÁGINA: HISTÓRICO DE ANÁLISES
    # ══════════════════════════════════════════════════════════════════════
    elif menu == "Histórico de Análises":
        st.title("📂 Pipeline de Histórico")
        st.write("Consulte análises anteriores e decisões registradas.")

        history_df = get_history(user_id=st.session_state.get('user_id'))
        if not history_df.empty:
            st.markdown("### 📋 Resumo das Análises")
            table_df = history_df[['id', 'client', 'date', 'type', 'status', 'notes']].copy()
            table_df.columns = ['Nº', 'Cliente', 'Data', 'Tipo', 'Status', 'Notas/Reavaliação']
            st.dataframe(table_df, use_container_width=True)

            st.divider()
            st.markdown("### 🔍 Detalhes Individuais")
            for index, row in history_df.iterrows():
                with st.expander(
                    f"📄 {row['client']} - {row['type']} ({row['date']}) — Status: {row['status']}"
                ):
                    st.markdown(
                        f'<div class="analysis-container">{row["result"]}</div>',
                        unsafe_allow_html=True
                    )
                    if row['notes']:
                        st.warning(f"**Solicitação de Reavaliação:** {row['notes']}")
        else:
            st.info("Nenhum registro encontrado no histórico.")

    # ══════════════════════════════════════════════════════════════════════
    # PÁGINA: MEMÓRIA DO AGENTE
    # ══════════════════════════════════════════════════════════════════════
    elif menu == "🧠 Memória do Agente":
        st.title("🧠 Memória Conversacional do Agente")
        st.write("Gerencie as sessões de memória persistente do Jurix.")

        sessions = AgentMemory.list_sessions(user_id=st.session_state.get('user_id'))

        if not sessions:
            st.info("Nenhuma sessão de memória encontrada. Inicie uma análise para criar a primeira sessão.")
        else:
            st.markdown(f"**{len(sessions)} sessão(ões) ativa(s) no banco de memória.**")

            # Tabela de sessões
            sessions_df = pd.DataFrame(sessions)
            sessions_df.columns = ["Session ID", "Mensagens", "Última Interação"]
            st.dataframe(sessions_df, use_container_width=True)

            st.divider()
            st.markdown("### 🔍 Inspecionar Sessão")
            session_ids = [s["session_id"] for s in sessions]
            selected_session = st.selectbox("Selecione uma sessão", session_ids)

            if selected_session:
                memory = AgentMemory(session_id=selected_session, user_id=st.session_state.get('user_id'))
                history = memory.get_history(limit=50)

                st.caption(f"Session ID: `{selected_session}` | {len(history)} mensagem(s)")

                for msg in history:
                    role = msg["role"]
                    content = msg["content"]
                    if role == "user":
                        st.markdown(
                            f'<div class="chat-bubble chat-user" style="max-width:100%">{safe_html(content)}</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown('<div class="assistant-label">Jurix</div>', unsafe_allow_html=True)
                        st.markdown(
                            f'<div class="chat-bubble chat-assistant" style="max-width:100%">{safe_html(content)}</div>',
                            unsafe_allow_html=True
                        )

                st.divider()
                if st.button("🗑️ Limpar esta sessão de memória", type="secondary"):
                    memory.clear()
                    st.success(f"Sessão `{selected_session}` limpa.")
                    st.rerun()


if __name__ == "__main__":
    main()
