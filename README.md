# RaspagemEnv

Aplicação desenvolvida em Python para estudos de automação, raspagem de dados e utilização de variáveis de ambiente para gerenciamento seguro de configurações e credenciais.

## 📖 Sobre o Projeto

O objetivo deste projeto é demonstrar a implementação de scripts Python que realizam operações de coleta e processamento de dados, mantendo informações sensíveis fora do código-fonte através do uso de arquivos `.env`.

Essa abordagem segue boas práticas de desenvolvimento, facilitando a manutenção, segurança e portabilidade da aplicação.

## ✨ Funcionalidades

- Configuração por variáveis de ambiente
- Estrutura simples e organizada
- Separação de dados sensíveis do código
- Base para estudos de automação e integração
- Fácil expansão para novos recursos

## 🛠️ Tecnologias Utilizadas

- Python 3.x
- python-dotenv
- Requests
- Ambiente Virtual (venv)

## 📂 Estrutura do Projeto

```text
RaspagemEnv/
│
├── main.py
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

## 🚀 Instalação

Clone o repositório:

```bash
git clone https://github.com/devbyenzo/RaspagemEnv.git
```

Acesse o diretório:

```bash
cd RaspagemEnv
```

Crie um ambiente virtual:

```bash
python -m venv venv
```

Ative o ambiente virtual:

### Windows

```bash
venv\Scripts\activate
```

### Linux/macOS

```bash
source venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

## ⚙️ Configuração

Crie um arquivo `.env` na raiz do projeto:

```env
API_KEY=sua_chave_aqui
TOKEN=seu_token_aqui
```

## ▶️ Execução

```bash
python main.py
```

## 🎯 Objetivo de Aprendizado

Este projeto foi desenvolvido com foco em:

- Manipulação de variáveis de ambiente
- Boas práticas de segurança
- Estruturação de aplicações Python
- Automação de tarefas
- Consumo e processamento de dados

## 📌 Observação

Este repositório possui finalidade educacional e foi criado para fins de estudo e aperfeiçoamento técnico.

## 👨‍💻 Autor

@devbyenzo

- GitHub: https://github.com/devbyenzo
- LinkedIn: https://www.linkedin.com/in/devbyenzo/
