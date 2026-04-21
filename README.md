# VencIA

Este é um Analisador de Contratos Jurídicos desenvolvido em Python utilizando Streamlit e IA (Gemini, Groq, OpenRouter).

VencIA é um projeto em Work in progress, um Agente de IA para analise de contratos. Com potencial de escala e que permitirá equipes comerciais e vendedores, a otimizar a analise de contratos de clientes.

**Todo o projeto esta sendo desenvolvido utilizando IDE do GEMINI, O ANTIGRAVITY**.

**Por ser uma aplicação em Work in progress, as funcionalidades estão sendo testadas, mas incialmente é possivel criar qualquer app utilizando o antigravity. Ele permite utilizar vários modelos de LLM´s embutidos, incluindo o ANTROPIC**. 

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

## Componentes principais 
- **Docling** para processamento dos documentos, neste caso contratos de clientes em formato PDF e DOCX.
- **litellm** para mais flexibilidade dos modelos LLM´s: Facilidade para alternar entre diferentes LLMs (Gemini,GPT,llama, Antropic, Mistral etc)
- **Chainlit** para criação da interface de chat, chamado de Jurix, assistente de IA para pesquisas.
- **Langchain** como interface para estruturação da aplicação:
- **Orquestrar LLMs**: facilita chamadas a modelos como APIs de IA
- **Criar “chains”**: sequências de passos (ex: entrada → processamento → resposta)
- **Gerenciar memória**: mantém contexto de conversas
- **Integrar ferramentas**: banco de dados, APIs, arquivos, etc.
- **Criar agentes**: sistemas que tomam decisões e usam ferramentas automaticamente.
- **Streamlit** para interface direto em Python (inputs, botões, upload de arquivos).

  
    
  
