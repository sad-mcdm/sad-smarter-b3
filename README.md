# B3 SmarterInvestor — Sistema de Apoio à Decisão (SAD)

O **B3 SmarterInvestor** é um Sistema de Apoio à Decisão (SAD) voltado para a análise multicritério e estatística de ativos da bolsa brasileira (B3). O sistema combina o método clássico de decisão **SMARTER (Edwards & Barron, 1994)** com análise de correlação estatística histórica para sugerir ativos subavaliados e gerar recomendações de investimento personalizáveis.

---

## 🛠️ Tecnologias Utilizadas

*   **Backend:** Python 3.x com **Flask** (Framework Web), Flask-SQLAlchemy (Mapeamento Objeto-Relacional) e Flask-Migrate (Gerenciamento de Migrações).
*   **Banco de Dados:** SQLite (padrão de desenvolvimento) para armazenar dados cadastrais e séries temporais de indicadores e preços.
*   **Integração de Dados:** Coletor automático consumindo a API [brapi.dev](https://brapi.dev/) para cotações e indicadores financeiros em tempo real e históricos.
*   **Frontend:** HTML5, CSS3 personalizado e JavaScript (Vanilla) com **Chart.js** para renderização de gráficos interativos (Séries temporais de valor global, dispersão e correlação).

---

## 📐 Como Funciona o Coração do Sistema?

O motor do SAD está dividido em três componentes principais localizados na pasta `services/`:

### 1. Motor de Decisão Multicritério (SMARTER) — `services/smarter_engine.py`
O SMARTER é um método de Apoio Multicritério à Decisão (MCDA) que simplifica a elicitação de pesos pelos decisores. Ele funciona em 3 etapas:
1.  **Ordenação dos Critérios:** O usuário simplesmente ordena os indicadores (ex: 1º ROE, 2º P/L, 3º Dividend Yield).
2.  **Pesos ROC (Rank Order Centroid):** O sistema converte automaticamente a ordem de preferência em pesos matemáticos rigorosos através da fórmula dos centroides de ordem:
    $$w_i = \frac{1}{N} \sum_{j=i}^{N} \frac{1}{j}$$
3.  **Normalização por Escala de Intervalo:** Os valores brutos dos indicadores são normalizados para a escala $[0, 1]$ usando os limites históricos globais (mínimos e máximos de toda a base histórica do banco):
    *   **Critérios de Benefício** (maior é melhor, ex: ROE): $v = \frac{x - min}{max - min}$
    *   **Critérios de Custo** (menor é melhor, ex: P/L): $v = \frac{max - x}{max - min}$
4.  **Valor Global $V(a, t)$:** O sistema calcula a soma ponderada dos valores normalizados de cada alternativa (empresa) em cada período histórico $t$, gerando uma série temporal de atratividade.

### 2. Analisador Estatístico — `services/statistical_analyzer.py`
Para dar inteligência financeira ao modelo, o sistema calcula a correlação entre a atratividade teórica do SMARTER e o comportamento real de preços da ação:
*   Compara a variação do Valor Global ($\Delta V$) contra a variação do preço da ação ($\Delta Price$) em janelas temporais configuráveis (ex: 90 dias).
*   Calcula o **Coeficiente de Correlação de Pearson ($r$)** para cada ativo.
*   **Pontuação de Recomendação (Recommendation Score):** Identifica ativos onde a correlação é alta e positiva (o preço tende a acompanhar os fundamentos) ou onde há uma divergência (ex: o valor da empresa subiu, mas o preço caiu), indicando uma potencial oportunidade de compra.

### 3. Coletor de Dados — `services/data_collector.py`
*   Automatiza a carga de tickers cadastrados e executa requisições assíncronas/cronometradas para buscar preços históricos diários e relatórios de demonstrativos financeiros.

---

## 📁 Estrutura de Pastas do Projeto

```text
sad-smarter-b3/
│
├── app.py                # Ponto de entrada (Application Factory do Flask)
├── config.py             # Configurações de ambiente (desenvolvimento, testes)
├── check_db.py           # Utilitário de inspeção e status do banco de dados
├── seed_historical.py    # Script para popular dados históricos fictícios/teste
├── requirements.txt      # Dependências do Python
│
├── models/               # Modelos de dados (SQLAlchemy)
│   ├── company.py            # Cadastro de empresas (tickers, setores)
│   ├── sector.py             # Segmentos de atuação
│   ├── indicator.py          # Definições dos indicadores (P/L, ROE, etc.)
│   ├── indicator_history.py  # Histórico temporal dos indicadores das empresas
│   ├── price_history.py      # Histórico de preços das ações
│   └── recommendation.py     # Resultados de V(a, t) e análises de correlação
│
├── services/             # Lógica de negócio do SAD
│   ├── smarter_engine.py     # Motor matemático do método SMARTER
│   ├── statistical_analyzer.py # Correlações de Pearson e scores de recomendação
│   └── data_collector.py     # Integração com a API brapi.dev
│
├── routes/               # Controladores da API (Endpoints REST)
│   └── api.py                # Endpoints de consulta de dados e simulações
│
└── templates/ & static/  # Interface de usuário (HTML/CSS/JS)
```

---

## 🚀 Instalação e Execução

### Pré-requisitos
*   Python 3.10 ou superior instalado.

### Passo 1: Clone o Repositório e crie o Ambiente Virtual
```bash
git clone https://github.com/sad-mcdm/sad-smarter-b3.git
cd sad-smarter-b3
python -m venv .venv
```

### Passo 2: Ative o Ambiente Virtual
*   **Windows (PowerShell):**
    ```powershell
    .venv\Scripts\Activate.ps1
    ```
*   **Windows (Prompt de Comando):**
    ```cmd
    .venv\Scripts\activate.bat
    ```
*   **Linux/macOS:**
    ```bash
    source .venv/bin/activate
    ```

### Passo 3: Instale as Dependências
```bash
pip install -r requirements.txt
```

### Passo 4: Configure as Variáveis de Ambiente
Copie o arquivo `.env.example` para `.env`:
```bash
cp .env.example .env
```
Abra o arquivo `.env` e configure suas variáveis. Caso possua uma chave da API do `brapi.dev`, preencha o campo `BRAPI_TOKEN` (opcional).

### Passo 5: Inicialize e Popule o Banco de Dados
Para criar as tabelas e popular o sistema com dados iniciais de indicadores e preços históricos para testes, execute:
```bash
python seed_historical.py
```

### Passo 6: Execute a Aplicação
```bash
python app.py
```
Acesse a aplicação no seu navegador em **`http://localhost:5000`**.

---

## 📊 Endpoints Principais da API

O sistema expõe rotas REST que facilitam integrações com outras aplicações:

*   `GET /api/companies`: Lista as empresas cadastradas no sistema.
*   `GET /api/indicators`: Retorna todos os indicadores disponíveis para a análise.
*   `POST /api/decision`: Cria um novo problema de decisão.
*   `PUT /api/decision/<problem_id>/criteria`: Salva a ordenação de preferência dos critérios e gera os pesos ROC.
*   `PUT /api/decision/<problem_id>/alternatives`: Define as ações candidatas para análise.
*   `POST /api/decision/<problem_id>/calculate`: Roda a engine do SMARTER e calcula os valores globais.
*   `GET /api/recommendations/<problem_id>`: Retorna o ranking consolidado baseado nos resultados de correlação estatística.
