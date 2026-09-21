"""
Orion Cloud Kitchen - Saude Operacional
Roda via GitHub Actions a cada 15 minutos
"""

import json, time, os, requests
from datetime import datetime, date

# Credenciais via variaveis de ambiente (GitHub Secrets)
SUPABASE_URL   = os.environ.get("SUPABASE_URL", "https://ogpfjrxawqerhoitcoxz.supabase.co")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ncGZqcnhhd3FlcmhvaXRjb3h6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk1NzMzODAsImV4cCI6MjEwNTE0OTM4MH0.eEEYrx-yOsbgjf4hOccAxP1ernzLUajzkbQByZo1vFI")
SUPABASE_TABLE = "saude_operacional"

URL_ORION_LOGIN  = "https://admin.orioncloudkitchens.com.br"
URL_ORION_VENDAS = "https://admin.orioncloudkitchens.com.br/admin/reports/orders"
ORION_EMAIL      = "orion"
ORION_SENHA      = "orion@2021"

URL_CHAT_LOGIN   = "https://app.chatpro.com.br"
CHAT_USUARIO     = "Vívian Faria"
CHAT_SENHA       = "Orion@123"



# Indices das colunas (base 0): 0=Cod,1=Status,2=Motivo,3=Hub,4=Estab
# 5=Cliente,6=Prod,7=Desc,8=Sub,9=Serv,10=Total,11=Cadastro,12=Pronto,13=Coleta,14=Retornado,15=Concluido
IDX_STATUS=1; IDX_HUB=3; IDX_CADASTRO=11; IDX_PRONTO=12; IDX_COLETA=13; IDX_CONCLUIDO=15
def parse_dt(v):
    if not v or v.strip() in ("-", "", "--"): return None
    for f in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
        try: return datetime.strptime(v.strip(), f)
        except: pass
    return None

def diff_min(a, b):
    if a is None or b is None: return None
    return (b - a).total_seconds() / 60

def media(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v)/len(v), 2) if v else None

def parse_tempo_chatpro(s):
    if not s or s.strip() in ("-", "", "--"): return None
    try:
        partes = s.strip().split(":")
        if len(partes) == 2:
            return int(partes[0]) + int(partes[1])/60
        if len(partes) == 3:
            return int(partes[0])*60 + int(partes[1]) + int(partes[2])/60
    except: pass
    return None

def enviar_supabase(dados):
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }
    payload = {"id": 1}
    payload.update(dados)
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        headers=headers,
        json=payload,
        timeout=15,
    )
    if r.status_code in (200, 201, 204):
        print("  OK Supabase atualizado")
    else:
        print(f"  ERRO Supabase: {r.status_code} {r.text[:200]}")

def orion_login(page):
    page.goto(URL_ORION_LOGIN, wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)
    try: page.fill('input[type="email"]', ORION_EMAIL)
    except:
        try: page.fill('input[name="email"]', ORION_EMAIL)
        except:
            ins = page.query_selector_all('input')
            if ins: ins[0].fill(ORION_EMAIL)
    try: page.fill('input[type="password"]', ORION_SENHA)
    except:
        ins = page.query_selector_all('input')
        if len(ins) >= 2: ins[1].fill(ORION_SENHA)
    try: page.click('button[type="submit"]')
    except: page.click('button')
    time.sleep(4)
    print("  OK Login Orion")

def coletar_orion(page):
    try: page.goto(URL_ORION_VENDAS, wait_until="domcontentloaded", timeout=60000)
    except: pass
    time.sleep(5)
    try: page.click('button:has-text("Buscar")', timeout=5000); time.sleep(5)
    except: pass
    try: page.wait_for_selector("table tbody tr", timeout=15000)
    except: pass
    time.sleep(3)

    # Tabela 2 (pedidos): conta cancelamentos por hub DS Sion + motivo de montagem
    # Palavras que INCLUEM (erro de montagem):
    MOTIVOS_MONTAGEM = [
        "faltante","faltando","faltou","falta ","falta de item",
        "item errado","item trocado","item incorreto","item diferente",
        "produto errado","produto trocado","produto incorreto","produto diferente","produto faltando",
        "quantidade errada","quantidade incorreta","a menos","a mais","quantidade diferente",
        "pedido incompleto","incompleto","montagem","embalagem errada",
        "troca","trocado","trocaram","errado","incorreto","faltou item",
        "veio errado","veio faltando","veio a menos","veio diferente",
        "enviado errado","item a menos","item a mais","pedido errado",
    ]
    # Palavras que EXCLUEM (nao e montagem):
    MOTIVOS_EXCLUIR = [
        "entrega","motoboy","entregador","courier",
        "endereco","endereço","localizacao","localização","nao encontrou","nao encontrado",
        "pagamento","troco","dinheiro","cartao","cartão","pix","maquina","maquininha",
        "cancelado pelo cliente","desistencia","desistência","cliente cancelou","cliente desistiu",
        "demora","tempo de espera","muito tempo","demorou","prazo",
        "fechado","loja fechada","estabelecimento fechado",
        "sistema","app","aplicativo","plataforma",
    ]

    def eh_cancel_montagem(motivo, hub):
        if not motivo or not hub: return False
        hub_lower = hub.lower().strip()
        if "sion" not in hub_lower: return False
        motivo_lower = motivo.lower()
        for excluir in MOTIVOS_EXCLUIR:
            if excluir in motivo_lower: return False
        for incluir in MOTIVOS_MONTAGEM:
            if incluir in motivo_lower: return True
        return False

    cancelamentos = 0
    try:
        tabelas = page.query_selector_all("table")
        tabela_pedidos = tabelas[1] if len(tabelas) >= 2 else tabelas[0]
        todas = tabela_pedidos.query_selector_all("tbody tr")
        for linha in todas:
            try:
                cels = linha.query_selector_all("td")
                if len(cels) < 5: continue
                tx = [c.inner_text().strip() for c in cels]
                status = tx[1].lower() if len(tx) > 1 else ""
                motivo = tx[2] if len(tx) > 2 else ""
                hub    = tx[3] if len(tx) > 3 else ""
                if "cancel" in status and eh_cancel_montagem(motivo, hub):
                    cancelamentos += 1
            except: continue
        print(f"  OK Cancelamentos DS Sion montagem: {cancelamentos}")
    except Exception as e:
        print(f"  AVISO cancelamentos: {e}")

    # Tabela 2 (pedidos): filtra apenas linhas com >= 15 colunas
    montagem_ds  = []
    despacho_hub = []
    try:
        tabelas = page.query_selector_all("table")
        tabela_pedidos = tabelas[1] if len(tabelas) >= 2 else tabelas[0]
        linhas = tabela_pedidos.query_selector_all("tbody tr")
        print(f"  DEBUG Pedidos: {len(linhas)} linhas")
        if linhas:
            try:
                cels = linhas[0].query_selector_all("td")
                print(f"  DEBUG cols:{len(cels)} | {[c.inner_text().strip() for c in cels[:6]]}")
            except: pass

        for linha in linhas:
            try: cels = linha.query_selector_all("td")
            except: continue
            if len(cels) < 15: continue
            tx = [c.inner_text().strip() for c in cels]
            hub = tx[3].lower().strip() if len(tx) > 3 else ""
            dt_c = parse_dt(tx[11]) if len(tx) > 11 else None
            dt_p = parse_dt(tx[12]) if len(tx) > 12 else None
            dt_k = parse_dt(tx[13]) if len(tx) > 13 else None
            dt_x = parse_dt(tx[15]) if len(tx) > 15 else None
            if "sion" in hub and dt_c and dt_p:
                t = diff_min(dt_c, dt_p)
                if t is not None and 0 <= t < 120: montagem_ds.append(t)
            if hub in ("-", "", "none") and dt_k and dt_x:
                t = diff_min(dt_k, dt_x)
                if t is not None and 0 <= t < 120: despacho_hub.append(t)
        print(f"  OK {len(montagem_ds)} montagens DS Sion, {len(despacho_hub)} despachos")
    except Exception as e:
        print(f"  ERRO pedidos: {e}")

    return {
        "cancelamentos":  cancelamentos,
        "montagem_ds":    media(montagem_ds),
        "montagem_count": len(montagem_ds),
        "despacho_hub":   media(despacho_hub),
        "despacho_count": len(despacho_hub),
    }

def coletar_chatpro(page):
    try:
        page.goto(URL_CHAT_LOGIN, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        try: page.fill('input[type="email"]', CHAT_USUARIO)
        except:
            ins = page.query_selector_all('input')
            if ins: ins[0].fill(CHAT_USUARIO)
        try: page.fill('input[type="password"]', CHAT_SENHA)
        except:
            ins = page.query_selector_all('input')
            if len(ins) >= 2: ins[1].fill(CHAT_SENHA)
        try: page.click('button[type="submit"]')
        except: page.click('button')
        time.sleep(5)
        print("  OK Login ChatPro")

        # Navegar para relatorios
        seletores = ['a[href*="report"]','a[href*="relat"]','nav li:nth-child(5) a']
        for sel in seletores:
            try: page.click(sel, timeout=2000); break
            except: pass
        time.sleep(2)

        # Filtrar hoje
        hoje = date.today().strftime("%Y-%m-%d")
        try:
            campos = page.query_selector_all('input[type="date"]')
            if len(campos) >= 2:
                campos[0].fill(hoje)
                campos[1].fill(hoje)
                time.sleep(1)
            try: page.click('button:has-text("Filtrar"), button:has-text("Buscar"), button:has-text("Aplicar")', timeout=3000)
            except: pass
            time.sleep(3)
        except: pass

        # Coletar tempo de espera
        import re
        espera_min = None
        try:
            texto = page.inner_text('body')
            idx = texto.find("Tempo médio de espera")
            if idx >= 0:
                trecho = texto[idx:idx+80]
                matches = re.findall(r'\d{1,2}:\d{2}(?::\d{2})?', trecho)
                if matches:
                    espera_min = parse_tempo_chatpro(matches[0])
        except Exception as e:
            print(f"  AVISO ChatPro: {e}")

        print(f"  OK ChatPro espera: {espera_min} min")
        return {"espera_min": espera_min}
    except Exception as e:
        print(f"  ERRO ChatPro: {e}")
        return {"espera_min": None}

def main():
    from playwright.sync_api import sync_playwright
    print("["+datetime.now().strftime("%H:%M:%S")+"] Iniciando coleta...")

    resultado = {
        "atualizado_em":  datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "hora_coleta":    datetime.now().strftime("%H:%M"),
        "cancelamentos":  None,
        "montagem_ds":    None,
        "montagem_count": 0,
        "despacho_hub":   None,
        "despacho_count": 0,
        "espera_min":     None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage"]
        )

        page_orion = browser.new_context().new_page()
        try:
            orion_login(page_orion)
            resultado.update(coletar_orion(page_orion))
        except Exception as e:
            print(f"  ERRO Orion: {e}")
        finally:
            page_orion.close()

        page_chat = browser.new_context().new_page()
        try:
            resultado.update(coletar_chatpro(page_chat))
        except Exception as e:
            print(f"  ERRO ChatPro: {e}")
        finally:
            page_chat.close()

        browser.close()

    enviar_supabase(resultado)
    print(f"  OK Resultado: {resultado}")

if __name__ == "__main__":
    main()
