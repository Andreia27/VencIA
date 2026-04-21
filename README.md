# VencIA
VencIA é um projeto em Work in progress, é um Agente de IA para analise de contratos. Com potencial de escala e que permitirá equipes comerciais e vendedores, a otimizar a analise de contratos de clientes.

# 🚀 Como Rodar Localmente

**Pré-requisitos:** Python 3.10+

1. **Instalar dependências:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configurar Chaves de API:**
   Crie um arquivo `.env` e adicione suas chaves:
   ```env
   GEMINI_API_KEY="sua_chave"
   GROQ_API_KEY="sua_chave"
   OPENROUTER_API_KEY="sua_chave"
   ```

3. **Executar a aplicação:**
   ```bash
   python -m streamlit run legal_agent.py
   ```

## 🛡️ Funcionalidades
- Análise de Risco (Responsabilidade, Rescisão, Pagamento, Confidencialidade).
- Suporte multi-provedor (Gemini, Groq, OpenRouter).
- Histórico persistente com SQLite.
- ChatBot Jurix , funciona como um assistente jurídico.
