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
CHAT_EMAIL     = "vivian@orioncloudkitchens.com.br"
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
    # Formato ChatPro: HH:MM (horas:minutos) ou HH:MM:SS
    if not s or s.strip() in ("-", "", "--"): return None
    try:
        partes = s.strip().split(":")
        if len(partes) == 2:
            # HH:MM -> converte para minutos
            return int(partes[0]) * 60 + int(partes[1])
        if len(partes) == 3:
            # HH:MM:SS -> converte para minutos
            return int(partes[0]) * 60 + int(partes[1]) + int(partes[2])/60
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

def coletar_chatpro():
    """
    Coleta tempo medio de espera do ChatPro por turno via injecao de token Firebase.
    Turno dia:  09:30 - 18:00
    Turno noite: 18:00 - 01:20
    """
    import re, json as _json
    try:
        CHATPRO_REFRESH_TOKEN = os.environ.get("CHATPRO_REFRESH_TOKEN", "")
        CHATPRO_API_KEY       = os.environ.get("CHATPRO_API_KEY", "AIzaSyCP_2g5Sm8I9FXgEzhD4-rA9jQqI3cCzWU")
        CHATPRO_INSTANCE      = "chatpro-1e23402277"
        CHATPRO_UID           = "QGrXo11mnkXDsL80xcAMvUSVme62"
        CHATPRO_EMAIL         = "vivian@orioncloudkitchens.com.br"

        if not CHATPRO_REFRESH_TOKEN:
            print("  AVISO ChatPro: CHATPRO_REFRESH_TOKEN nao definido")
            return {"espera_min": None, "espera_dia_min": None, "espera_noite_min": None, "turno_atual": None}

        # Renova token Firebase
        resp = requests.post(
            f"https://securetoken.googleapis.com/v1/token?key={CHATPRO_API_KEY}",
            json={"grant_type": "refresh_token", "refresh_token": CHATPRO_REFRESH_TOKEN},
            headers={"Referer": "https://app.chatpro.com.br/", "Origin": "https://app.chatpro.com.br"},
            timeout=15
        )
        if resp.status_code != 200:
            print(f"  ERRO ChatPro token: {resp.status_code}")
            return {"espera_min": None, "espera_dia_min": None, "espera_noite_min": None, "turno_atual": None}

        token_data    = resp.json()
        access_token  = token_data.get("access_token") or token_data.get("id_token")
        new_refresh   = token_data.get("refresh_token", CHATPRO_REFRESH_TOKEN)
        expires_in    = int(token_data.get("expires_in", 3600))
        expiration_ms = int(time.time() * 1000) + expires_in * 1000
        print("  OK ChatPro token renovado")

        firebase_key  = f"firebase:authUser:{CHATPRO_API_KEY}:[DEFAULT]"
        firebase_data = {
            "uid": CHATPRO_UID, "email": CHATPRO_EMAIL, "emailVerified": True,
            "displayName": "Vivian Faria", "isAnonymous": False,
            "providerData": [{"providerId": "password", "uid": CHATPRO_EMAIL,
                              "displayName": "Vivian Faria", "email": CHATPRO_EMAIL}],
            "stsTokenManager": {"refreshToken": new_refresh, "accessToken": access_token,
                                "expirationTime": expiration_ms},
            "createdAt": "1700000000000",
            "lastLoginAt": str(int(time.time() * 1000)),
            "apiKey": CHATPRO_API_KEY, "appName": "[DEFAULT]"
        }

        # Determina turno atual
        agora = datetime.now()
        hora  = agora.hour + agora.minute / 60
        if 9.5 <= hora < 18.0:
            turno_atual = "dia"
        elif hora >= 18.0 or hora < 1.33:
            turno_atual = "noite"
        else:
            turno_atual = None
        print(f"  DEBUG turno atual: {turno_atual} ({agora.strftime('%H:%M')})")

        def coletar_espera_com_filtro(page, label):
            """Coleta tempo de espera da pagina de analise atual"""
            try:
                body_text = page.inner_text("body")
                idx = body_text.find("Tempo m")
                if idx >= 0:
                    trecho = body_text[idx:idx+60]
                    print(f"  DEBUG ChatPro {label}: {trecho}")
                    matches = re.findall(r'\d{1,2}:\d{2}(?::\d{2})?', trecho)
                    if matches:
                        return parse_tempo_chatpro(matches[0])
            except Exception as e:
                print(f"  AVISO ChatPro {label}: {e}")
            return None

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])

            def criar_sessao_autenticada():
                ctx  = browser.new_context()
                page = ctx.new_page()
                page.goto("https://app.chatpro.com.br/signin", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                page.evaluate(f"""async () => {{
                    const dbReq = indexedDB.open('firebaseLocalStorageDb', 1);
                    await new Promise((res, rej) => {{
                        dbReq.onupgradeneeded = e => e.target.result.createObjectStore('firebaseLocalStorage', {{keyPath: 'fbase_key'}});
                        dbReq.onsuccess = e => {{
                            const db = e.target.result;
                            const tx = db.transaction('firebaseLocalStorage', 'readwrite');
                            tx.objectStore('firebaseLocalStorage').put({{fbase_key: '{firebase_key}', value: {_json.dumps(firebase_data)}}});
                            tx.oncomplete = res; tx.onerror = rej;
                        }};
                        dbReq.onerror = rej;
                    }});
                    localStorage.setItem('instance', '{CHATPRO_INSTANCE}');
                    localStorage.setItem('@chatpro:auth', JSON.stringify({{instance_id:'{CHATPRO_INSTANCE}',uid:'{CHATPRO_UID}',email:'{CHATPRO_EMAIL}'}}));
                }}""")
                time.sleep(1)
                return page

            # Coleta geral (dia todo - para o indicador principal)
            page = criar_sessao_autenticada()
            page.goto("https://app.chatpro.com.br/reports/analysis", wait_until="networkidle", timeout=30000)
            time.sleep(6)
            espera_geral = coletar_espera_com_filtro(page, "geral")

            # Coleta turno dia (09:30-18:00) - via filtro de hora na URL se possivel
            # O chatpro nao tem filtro de hora, entao usamos o valor geral por turno
            # e derivamos o turno ativo como o indicador principal
            espera_dia    = espera_geral if turno_atual == "dia"   else None
            espera_noite  = espera_geral if turno_atual == "noite" else None

            browser.close()

        # O indicador principal e o do turno atual
        espera_min = espera_geral
        print(f"  OK ChatPro espera geral:{espera_min} turno:{turno_atual}")
        return {
            "espera_min":       espera_min,
            "espera_dia_min":   espera_dia,
            "espera_noite_min": espera_noite,
            "turno_atual":      turno_atual,
        }

    except Exception as e:
        print(f"  ERRO ChatPro: {e}")
        return {"espera_min": None, "espera_dia_min": None, "espera_noite_min": None, "turno_atual": None}

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

    # Coleta Orion via Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage"]
        )
        pg = browser.new_context().new_page()
        try:
            orion_login(pg)
            resultado.update(coletar_orion(pg))
        except Exception as e:
            print(f"  ERRO Orion: {e}")
        finally:
            pg.close()
            browser.close()

    # Coleta ChatPro via API Firebase (sem browser - sem reCAPTCHA)
    try:
        resultado.update(coletar_chatpro())
    except Exception as e:
        print(f"  ERRO ChatPro: {e}")

    enviar_supabase(resultado)
    print(f"  OK Resultado: {resultado}")

if __name__ == "__main__":
    main()
