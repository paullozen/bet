# 📊 Bet365 Scraper & Dashboard (Node.js)

Este projeto é um sistema completo de raspagem de dados (scraping) e análise para a plataforma Bet365 (Futebol Virtual), migrado inteiramente para o ecossistema **Node.js**.

O sistema coleta resultados de jogos ("Ambos Marcam", Plarares, etc.) em tempo real, salva em CSV e fornece uma interface web para controle e visualização.

## 🚀 Funcionalidades

- **Scraping em Tempo Real**: Coleta dados de múltiplos campeonatos simultaneamente (Euro Cup, Premier League, Sul Americano, Copa do Mundo).
- **Arquitetura Multi-Abas (Workers)**: Cada campeonato roda em seu próprio contexto isolado (aba) para máxima performance e isolamento de falhas.
- **Calibração Automática**: O sistema identifica automaticamente o horário atual dos jogos para iniciar a coleta sem duplicidade.
- **Coleta Incremental**: Apenas novos jogos são processados após a calibração inicial.
- **Modo Lookback**: Capacidade de buscar jogos passados (até X horas atrás) caso o sistema seja iniciado tardiamente.
- **Dashboard Web**: Interface moderna para:
  - Iniciar/Parar o scraping.
  - Visualizar logs em tempo real via WebSocket.
  - Configurar parâmetros (credenciais, intervalos, campeonatos).
  - Visualizar histórico de dados (tabelas CSV).
- **Persistência**: Dados salvos em arquivos CSV diários na pasta `historico`.

## 🛠️ Stack Tecnológica

- **Runtime**: Node.js
- **Backend**: Express.js
- **Real-time**: Socket.io
- **Scraping**: Playwright (Chrome/Chromium)
- **Data Handling**: csv-writer, fs-extra, dayjs

## 📂 Estrutura do Projeto

```
betjs/
├── scraper.js        # Lógica central dos robôs de scraping (Playwright)
├── server.js         # Servidor Web (API + Socket.io) + Orquestrador
├── config.json       # Arquivo de configuração (URL, credenciais, delays)
├── public/           # Frontend do Dashboard (HTML/CSS/JS)
├── historico/        # Armazenamento dos CSVs gerados (matches_DD-MM-YYYY.csv)
├── anchor_time/      # Controle de estado para evitar re-processamento
└── package.json      # Dependências e Scripts
```

## ⚙️ Instalação

1.  Certifique-se de ter o **Node.js** instalado.
2.  Instale as dependências:
    ```bash
    npm install
    ```
3.  (Opcional) Instale os navegadores do Playwright se for a primeira vez:
    ```bash
    npx playwright install
    ```

## ▶️ Como Usar

1.  Inicie o servidor e o dashboard:

    ```bash
    npm start
    ```

    Ou para desenvolvimento (com reload automático):

    ```bash
    npm run dev
    ```

2.  Acesse o dashboard no navegador:
    **http://localhost:3000**

3.  No Dashboard:
    - Clique em **Iniciar** para rodar o scraper.
    - Acompanhe o log na tela preta estilo terminal.
    - Acesse a aba **Configurações** para ajustar usuário/senha da Bet365 (se necessário para acesso completo).

## 📝 Configuração (`config.json`)

O arquivo é gerado automaticamente, mas pode ser editado via Dashboard ou manualmente:

- `TARGET_URL`: URL da página de resultados.
- `COMPETITIONS`: Lista de campeonatos a monitorar.
- `DELAY_MIN` / `DELAY_MAX`: Intervalo de espera aleatório (humanização).
- `POLLING_INTERVAL`: Tempo de espera entre verificações quando não há novos jogos.

## ⚠️ Notas Reponsabilidade

Este software é apenas para fins de estudo e análise de dados. O uso de bots pode infringir os termos de serviço de sites de terceiros. Use com responsabilidade.
