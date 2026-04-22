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


## Como funciona

**SEGURANÇA**
- Para acessar o sistema, o usuário deve efetuar o cadastro. Com essa funcionalidade de acesso por credencial, cada usuário só poderá ter acesso aos contratos com login e senha pessoais, desta forma, todo o histórico de analises é individual.

**EXECUTAR**
- O usuário envia um documento, neste caso um contrato.
- O documento é processado com Docling e depois enviado para a LLM, com o usuário selecionando o botão **GERAR RELATÓRIO COM IA**.
- A API litellm, configurada como um **AGENTE** realiza a analise do contrato e retorna como uma analise de riscos e sugestões de clausulas.
- O usuário também pode fazer perguntas através do chatbot **JURIX**, o assistente que retorna respostas das analises.
- Todas as analises realizadas são armazenadas no modelo de banco de dados relacional SQLite, uma funcionalidade que permite fazer buscas em uma grande quantidade de contratos.

## Personalização 
- É possivel adicionar mais funcionalidades, e alguns ainda estão em desenvolvimento e principalmente em projetos com o uso de agentes, é importante sempre checar a segurança e ajustar o uso da janela de contexto, pois em relação a analise de contratos precisamos estabelercer diretrizes e parametros adequados para não termos respostas alucinadas, inveridicas. A IA facilita e automatiza o processo de analise, mas o core da aplicação precisa estar bem estruturado e alinhado às regras do negócio.

## Observação
- Este é um projeto em desenvolvimento e em breve estará em produção, mais existem algumas observações importantes a considerar:
- Por enquanto é um modelo de SAAS, MVP.
- Podemos evoluir:
 **Frontend** :
- Como esta com cara de DEMO, e somente com streamilit acaba ficando um pouco limitado as configurações, a ideia é utilizar uma interface mais moderna com REACT por exmeplo.
 **Backend** :
- Certificar melhor a segurança e estabelecer regras de negócio ainda mais robustas e a integração com banco de dados, evoluir para MONGODB.
- Verificação de emails, para que não tenhamos usuários fake cadastrados , isso acaba consumindo a API e tokes, poderá ser testado com DEMO.
- A preocupação com o consumo de tokes é primordial, administrar a quantidade de contratos que podem ser analisados e tamanho dos documentos, máximo 5mb por exemplo, talvez 1-2 contratos por usuário ao dia e um limite de 5 por mês.
- Aplicar regras de validação destes documentos, essa função já esta configurada, para que nenhum documento seja executado, apenas
extração de texto.

## Existem outros requisitos importantes que ao longo do desemvolvimento serão avaliados para melhor desempenho do sistema e como aplicar funcionalidades integradoras com CRM por exemplo, não limitar a somente analises, mas ao modelo de negócio da area comercial, integrar informações de vendas, histórico de clientes, pesquisas com web scraping etc.

## Atualmente é uma aplicação que resolve um problema real e pode ajudar equipes de vendas na otimização de analises de contratos e nos processos internos.
  
  
    
  
