# RaspagemEnv

Sistema de automação desenvolvido em Python para processamento e distribuição periódica de informações de produtos através de integração com APIs de mensageria.

## Overview

O projeto foi desenvolvido com foco em automação de tarefas, manipulação de dados estruturados e integração com serviços externos. A aplicação realiza a leitura de uma base de produtos em formato JSON, processa as informações e realiza envios automáticos para um destinatário configurado.

As configurações sensíveis são armazenadas em variáveis de ambiente, seguindo boas práticas de segurança e desenvolvimento.

## Features

* Leitura de produtos através de arquivos JSON
* Configuração via variáveis de ambiente (.env)
* Envio automatizado de mensagens
* Processamento periódico de dados
* Estrutura modular e extensível
* Gerenciamento seguro de credenciais
* Fácil adaptação para diferentes provedores de mensagens

## Technologies

* Python 3.10+
* JSON
* Requests
* Python Dotenv

## Project Structure

```text
RaspagemEnv/
├── main.py
├── produtos.json
├── .env
├── requirements.txt
├── .gitignore
└── README.md
```

## Installation

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

### Linux / macOS

```bash
source venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

## Environment Variables

Crie um arquivo `.env` na raiz do projeto:

```env
BOT_TOKEN=your_bot_token
CHAT_ID=your_chat_id
```

## Example Product Structure

```json
[
  {
    "name": "Example Product",
    "price": 199.90,
    "url": "https://example.com/product"
  }
]
```

## Running

```bash
python main.py
```

## Use Cases

* Monitoramento de produtos
* Alertas automatizados
* Distribuição de informações em grupos ou chats
* Estudos de automação e integração com APIs
* Processamento de dados estruturados

## Security

Informações sensíveis devem ser armazenadas exclusivamente através de variáveis de ambiente. O arquivo `.env` não deve ser versionado ou compartilhado publicamente.

## License

This project is available for educational and learning purposes.
