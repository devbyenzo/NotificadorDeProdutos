import json
import os
import re
import time
import logging
import schedule
import requests
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("monitor.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Variáveis de ambiente
# ─────────────────────────────────────────────
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise EnvironmentError("TOKEN e CHAT_ID precisam estar definidos no .env")


# ─────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────
@dataclass
class ConfigMonitor:
    intervalo_minutos: int
    titulo_bot: str
    emoji_alerta: str
    emoji_alto: str
    notificar_preco_alto: bool
    silencioso: bool
    botao_comprar: bool
    headless: bool
    timeout_pagina: int


@dataclass
class Produto:
    id: str
    nome: str
    categoria: str
    emoji: str
    url: str
    valor_desejado: float
    ativo: bool
    site: str


# ─────────────────────────────────────────────
# Detecção automática de loja pelo domínio
# ─────────────────────────────────────────────
def detectar_site(url: str) -> str:
    u = url.lower()
    if "amazon.com.br" in u or "amazon.com" in u:
        return "amazon"
    if "mercadolivre.com.br" in u or "mercadolibre.com" in u or "ml.com.br" in u:
        return "mercadolivre"
    if "kabum.com.br" in u:
        return "kabum"
    if "magazineluiza.com.br" in u or "magalu.com.br" in u:
        return "magalu"
    return "desconhecido"


# ─────────────────────────────────────────────
# Utilitário: tenta múltiplos seletores em sequência
# ─────────────────────────────────────────────
def tentar_seletores(driver, seletores: list[tuple[str, str]]) -> Optional[str]:
    """
    Recebe lista de (By.X, "seletor") e retorna o .text
    do primeiro que encontrar na página. Retorna None se nenhum funcionar.
    """
    for by, seletor in seletores:
        try:
            el = driver.find_element(by, seletor)
            texto = el.text.strip()
            if texto:
                return texto
        except NoSuchElementException:
            continue
    return None


def limpar_e_converter(texto: str) -> float:
    """
    Converte string de preço BR para float.
    Exemplos: 'R$ 1.299,90' -> 1299.90 | '1299' -> 1299.0
    """
    # Remove tudo exceto dígitos, ponto e vírgula
    apenas_numeros = re.sub(r"[^\d.,]", "", texto)
    # Formato BR: 1.299,90
    if "," in apenas_numeros and "." in apenas_numeros:
        apenas_numeros = apenas_numeros.replace(".", "").replace(",", ".")
    # Só vírgula: 1299,90
    elif "," in apenas_numeros:
        apenas_numeros = apenas_numeros.replace(",", ".")
    # Só ponto: 1299.90 (já ok)
    return float(apenas_numeros)


# ─────────────────────────────────────────────
# Adaptadores de scraping por loja
# ─────────────────────────────────────────────

def extrair_preco_amazon(driver: webdriver.Chrome, timeout: int) -> float:
    """
    Amazon Brasil — design system próprio com classes estáveis.
    Seletores: a-price-whole + a-price-fraction
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CLASS_NAME, "a-price-whole"))
    )
    inteiro = driver.find_element(By.CLASS_NAME, "a-price-whole").text
    decimal = driver.find_element(By.CLASS_NAME, "a-price-fraction").text

    inteiro = inteiro.replace(".", "").replace(",", "").strip()
    decimal = decimal.strip()
    return float(f"{inteiro}.{decimal}")


def extrair_preco_mercadolivre(driver: webdriver.Chrome, timeout: int) -> float:
    """
    Mercado Livre Brasil — design system Andes.
    Seletores: andes-money-amount__fraction + andes-money-amount__cents
    Pega o MENOR preço visível (desconto vs. original).
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CLASS_NAME, "andes-money-amount__fraction"))
    )

    fracoes = driver.find_elements(By.CLASS_NAME, "andes-money-amount__fraction")
    centavos_els = driver.find_elements(By.CLASS_NAME, "andes-money-amount__cents")

    precos = []
    for i, fracao in enumerate(fracoes):
        texto_inteiro = fracao.text.replace(".", "").replace(",", "").strip()
        if not texto_inteiro.isdigit():
            continue
        cents = "00"
        if i < len(centavos_els):
            tc = centavos_els[i].text.strip()
            if tc.isdigit():
                cents = tc.zfill(2)
        precos.append(float(f"{texto_inteiro}.{cents}"))

    if not precos:
        raise ValueError("Nenhum preço encontrado na página do Mercado Livre.")

    return min(precos)


def extrair_preco_kabum(driver: webdriver.Chrome, timeout: int) -> float:
    """
    KaBuM! — site React com classes geradas dinamicamente.
    Usa XPath/atributos semânticos + múltiplos seletores como fallback.

    Estratégia de seletores (ordem de prioridade):
      1. XPath por data-testid do componente de preço principal
      2. CSS por class parcial 'finalPrice' (nome semântico estável)
      3. XPath por texto "à vista" seguido do preço
      4. CSS por class 'regularPrice'
      5. XPath genérico buscando span/strong com R$ no contexto do produto
    """
    seletores_espera = [
        (By.XPATH, '//*[@data-testid="product-price"]'),
        (By.XPATH, '//*[contains(@class,"finalPrice")]'),
        (By.XPATH, '//*[contains(@class,"regularPrice")]'),
        (By.XPATH, '//span[contains(text(),"R$") and contains(@class,"price")]'),
    ]

    # Espera qualquer um dos seletores aparecer
    encontrou = False
    for by, sel in seletores_espera:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, sel))
            )
            encontrou = True
            break
        except TimeoutException:
            continue

    if not encontrou:
        # Fallback: espera genérico pela página carregar
        time.sleep(timeout)

    # Tenta extrair o preço por múltiplos seletores
    seletores_preco = [
        (By.XPATH, '//*[@data-testid="product-price"]'),
        (By.XPATH, '//*[contains(@class,"finalPrice")]'),
        (By.XPATH, '//*[contains(@class,"sc-hKgILt")]'),   # classe gerada comum no KaBuM
        (By.XPATH, '//*[contains(@class,"regularPrice")]'),
        (By.CSS_SELECTOR, 'span[class*="price" i]'),
        (By.XPATH, '//h4[contains(@class,"price")]'),
        # Busca qualquer elemento com R$ seguido de valor
        (By.XPATH, '//*[contains(text(),"R$") and not(contains(text(),"parcela"))]'),
    ]

    texto = tentar_seletores(driver, seletores_preco)

    if not texto:
        raise ValueError("Nenhum seletor de preço funcionou na página do KaBuM.")

    # Extrai o primeiro valor monetário válido do texto
    matches = re.findall(r"R\$\s*[\d.,]+", texto)
    if matches:
        return limpar_e_converter(matches[0])

    return limpar_e_converter(texto)


def extrair_preco_magalu(driver: webdriver.Chrome, timeout: int) -> float:
    """
    Magazine Luiza (Magalu) — site React/Next.js.
    Usa atributos data-testid e classes semânticas como seletores primários.

    Estratégia de seletores (ordem de prioridade):
      1. data-testid="price-value" (atributo semântico, mais estável)
      2. XPath por class parcial 'price-template__price'
      3. XPath por class parcial 'inprice'
      4. CSS por class parcial 'Price'
      5. Regex no page_source como último recurso
    """
    seletores_espera = [
        (By.XPATH, '//*[@data-testid="price-value"]'),
        (By.XPATH, '//*[contains(@class,"price-template__price")]'),
        (By.XPATH, '//*[contains(@class,"inprice")]'),
    ]

    encontrou = False
    for by, sel in seletores_espera:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, sel))
            )
            encontrou = True
            break
        except TimeoutException:
            continue

    if not encontrou:
        time.sleep(timeout)

    seletores_preco = [
        (By.XPATH, '//*[@data-testid="price-value"]'),
        (By.XPATH, '//*[contains(@class,"price-template__price")]'),
        (By.XPATH, '//*[contains(@class,"inprice")]'),
        (By.XPATH, '//*[contains(@class,"Price__price")]'),
        (By.CSS_SELECTOR, '[class*="Price"][class*="value"]'),
        (By.CSS_SELECTOR, '[class*="price"][class*="value"]'),
        # data-testid variações conhecidas do Magalu
        (By.XPATH, '//*[@data-testid="price"]'),
        (By.XPATH, '//*[@data-testid="best-price"]'),
        (By.XPATH, '//p[contains(@class,"price")]'),
    ]

    texto = tentar_seletores(driver, seletores_preco)

    # Último recurso: regex no HTML da página
    if not texto:
        log.warning("  ⚠️  Seletores DOM falharam no Magalu, tentando regex no HTML...")
        html = driver.page_source
        matches = re.findall(r'"price":\s*([\d.]+)', html)
        if matches:
            return float(matches[0])
        matches_brl = re.findall(r'R\$\s*([\d.]+,\d{2})', html)
        if matches_brl:
            return limpar_e_converter(matches_brl[0])
        raise ValueError("Nenhum seletor ou regex funcionou na página do Magalu.")

    matches = re.findall(r"R\$\s*[\d.,]+", texto)
    if matches:
        return limpar_e_converter(matches[0])

    return limpar_e_converter(texto)


# ─────────────────────────────────────────────
# Registro de adaptadores
# ─────────────────────────────────────────────
ADAPTADORES: dict[str, Callable] = {
    "amazon":       extrair_preco_amazon,
    "mercadolivre": extrair_preco_mercadolivre,
    "kabum":        extrair_preco_kabum,
    "magalu":       extrair_preco_magalu,
}

LABELS_SITE = {
    "amazon":       "Amazon",
    "mercadolivre": "Mercado Livre",
    "kabum":        "KaBuM!",
    "magalu":       "Magalu",
}


def extrair_preco(driver: webdriver.Chrome, produto: Produto, timeout: int) -> float:
    adaptador = ADAPTADORES.get(produto.site)
    if not adaptador:
        raise NotImplementedError(
            f"Site '{produto.site}' não tem adaptador. "
            f"Suportados: {', '.join(ADAPTADORES.keys())}"
        )
    return adaptador(driver, timeout)


# ─────────────────────────────────────────────
# Carregamento do JSON
# ─────────────────────────────────────────────
def carregar_json(caminho: str = "produtos.json") -> tuple[ConfigMonitor, list[Produto]]:
    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo '{caminho}' não encontrado.")

    with open(path, "r", encoding="utf-8") as f:
        dados = json.load(f)

    cfg = dados["config"]
    config = ConfigMonitor(
        intervalo_minutos=cfg.get("intervalo_minutos", 30),
        titulo_bot=cfg.get("titulo_bot", "💰 Monitor de Preços"),
        emoji_alerta=cfg.get("emoji_alerta", "🔥"),
        emoji_alto=cfg.get("emoji_alto", "📈"),
        notificar_preco_alto=cfg.get("notificar_preco_alto", False),
        silencioso=cfg.get("silencioso", False),
        botao_comprar=cfg.get("botao_comprar", True),
        headless=cfg.get("headless", True),
        timeout_pagina=cfg.get("timeout_pagina", 15),
    )

    produtos = []
    for p in dados["produtos"]:
        if not p.get("ativo", True):
            continue
        url = p["url"]
        site = p.get("site") or detectar_site(url)
        produtos.append(Produto(
            id=p["id"],
            nome=p["nome"],
            categoria=p.get("categoria", ""),
            emoji=p.get("emoji", "🛒"),
            url=url,
            valor_desejado=float(p["valor_desejado"]),
            ativo=True,
            site=site,
        ))

    return config, produtos


# ─────────────────────────────────────────────
# Formatação
# ─────────────────────────────────────────────
def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcular_economia(preco: float, limite: float) -> str:
    diff = limite - preco
    pct = (diff / limite) * 100
    return f"{formatar_brl(diff)} ({pct:.1f}% abaixo do limite)"


# ─────────────────────────────────────────────
# Mensagem HTML para o Telegram
# ─────────────────────────────────────────────
def montar_mensagem(produto: Produto, preco: float, abaixo: bool, cfg: ConfigMonitor) -> str:
    sep = "─────────────────────"
    emoji_status = cfg.emoji_alerta if abaixo else cfg.emoji_alto
    status_texto = "PREÇO ATINGIDO" if abaixo else "PREÇO AINDA ALTO"
    categoria_linha = f"🏷 <b>Categoria:</b> {produto.categoria}\n" if produto.categoria else ""
    loja_label = LABELS_SITE.get(produto.site, produto.site.title())
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

    if abaixo:
        bloco_preco = (
            f"💵 <b>Preço atual:</b> <code>{formatar_brl(preco)}</code>\n"
            f"🎯 <b>Seu limite:</b> <code>{formatar_brl(produto.valor_desejado)}</code>\n"
            f"✅ <b>Economia:</b> <i>{calcular_economia(preco, produto.valor_desejado)}</i>"
        )
        rodape = "⚡ <i>Corre que pode esgotar!</i>"
    else:
        diff = preco - produto.valor_desejado
        bloco_preco = (
            f"💵 <b>Preço atual:</b> <code>{formatar_brl(preco)}</code>\n"
            f"🎯 <b>Seu limite:</b> <code>{formatar_brl(produto.valor_desejado)}</code>\n"
            f"❌ <b>Faltam:</b> <i>{formatar_brl(diff)} para atingir seu limite</i>"
        )
        rodape = "🔔 <i>Monitorando...</i>"

    return (
        f"{cfg.titulo_bot}\n"
        f"{sep}\n"
        f"{emoji_status} <b>{status_texto}</b>\n\n"
        f"{produto.emoji} <b>{produto.nome}</b>\n"
        f"{categoria_linha}"
        f"🏪 <b>Loja:</b> {loja_label}\n"
        f"{sep}\n"
        f"{bloco_preco}\n"
        f"{sep}\n"
        f"{rodape}\n"
        f"🕐 <i>Verificado em {agora}</i>\n\n"
        f"🔗 <a href=\"{produto.url}\">Ver produto</a>"
    )


def montar_teclado_inline(url: str, site: str) -> str:
    label = LABELS_SITE.get(site, "Ver produto")
    payload = {"inline_keyboard": [[{"text": f"🛍 Comprar no {label}", "url": url}]]}
    return json.dumps(payload)


# ─────────────────────────────────────────────
# Envio via Telegram
# ─────────────────────────────────────────────
def enviar_telegram(mensagem: str, produto: Produto, cfg: ConfigMonitor) -> bool:
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "disable_notification": cfg.silencioso,
    }
    if cfg.botao_comprar:
        payload["reply_markup"] = montar_teclado_inline(produto.url, produto.site)

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error(f"Erro ao enviar para o Telegram: {e}")
        return False


def enviar_resumo_inicio(produtos: list[Produto], cfg: ConfigMonitor):
    sep = "─────────────────────"
    lista = "\n".join(
        f"  {p.emoji} <b>{p.nome}</b> "
        f"[{LABELS_SITE.get(p.site, p.site)}] "
        f"— limite <code>{formatar_brl(p.valor_desejado)}</code>"
        for p in produtos
    )
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

    mensagem = (
        f"{cfg.titulo_bot}\n"
        f"{sep}\n"
        f"🟢 <b>Monitor iniciado!</b>\n\n"
        f"📋 <b>Produtos monitorados ({len(produtos)}):</b>\n"
        f"{lista}\n\n"
        f"{sep}\n"
        f"⏱ <b>Intervalo:</b> a cada {cfg.intervalo_minutos} minuto(s)\n"
        f"🕐 <i>Iniciado em {agora}</i>"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": mensagem,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": True,
            },
            timeout=10,
        ).raise_for_status()
        log.info("Resumo de início enviado ao Telegram.")
    except requests.RequestException as e:
        log.warning(f"Falha ao enviar resumo de início: {e}")


# ─────────────────────────────────────────────
# WebDriver
# ─────────────────────────────────────────────
def criar_driver(headless: bool) -> webdriver.Chrome:
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.binary_location = os.getenv(
        "CHROME_BIN",
        "/usr/bin/chromium"
    )

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service(
        os.getenv(
            "CHROMEDRIVER_PATH",
            "/usr/bin/chromedriver"
        )
    )

    return webdriver.Chrome(
        service=service,
        options=options
    )


# ─────────────────────────────────────────────
# Verificação individual
# ─────────────────────────────────────────────
def verificar_produto(driver: webdriver.Chrome, produto: Produto, cfg: ConfigMonitor):
    loja = LABELS_SITE.get(produto.site, produto.site)
    log.info(f"  [{loja}] {produto.nome}")

    try:
        driver.get(produto.url)
        preco = extrair_preco(driver, produto, cfg.timeout_pagina)
        abaixo = preco <= produto.valor_desejado

        log.info(
            f"  💵 {formatar_brl(preco)} | Limite: {formatar_brl(produto.valor_desejado)} "
            f"| {'✅ ABAIXO' if abaixo else '❌ ALTO'}"
        )

        if abaixo or cfg.notificar_preco_alto:
            mensagem = montar_mensagem(produto, preco, abaixo, cfg)
            ok = enviar_telegram(mensagem, produto, cfg)
            log.info(f"  {'✅ Notificado!' if ok else '❌ Falha no envio.'}")

    except NotImplementedError as e:
        log.warning(f"  ⚠️  {e}")
    except Exception as e:
        log.error(f"  ❌ Erro em '{produto.nome}': {e}")


# ─────────────────────────────────────────────
# Ciclo completo
# ─────────────────────────────────────────────
def executar_ciclo():
    try:
        config, produtos = carregar_json("produtos.json")
    except Exception as e:
        log.error(f"Erro ao carregar produtos.json: {e}")
        return

    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log.info(f"\n{'='*50}")
    log.info(f"  Ciclo iniciado — {agora}")
    log.info(f"  Produtos ativos: {len(produtos)}")
    log.info(f"{'='*50}")

    driver = criar_driver(config.headless)
    try:
        for produto in produtos:
            verificar_produto(driver, produto, config)
            time.sleep(3)
    finally:
        driver.quit()

    log.info("✅ Ciclo concluído.\n")


# ─────────────────────────────────────────────
# Ponto de entrada
# ─────────────────────────────────────────────
def main():
    config, produtos = carregar_json("produtos.json")

    log.info(f"\n{'='*50}")
    log.info(f"  {config.titulo_bot}")
    log.info(f"  {len(produtos)} produto(s) ativo(s)")
    log.info(f"  Intervalo: {config.intervalo_minutos} minuto(s)")
    log.info(f"{'='*50}\n")

    enviar_resumo_inicio(produtos, config)
    executar_ciclo()

    schedule.every(config.intervalo_minutos).minutes.do(executar_ciclo)
    log.info(f"⏳ Próximo ciclo em {config.intervalo_minutos} minuto(s)...")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()