"""
Script de debug isolado — chama o Gemini diretamente e mostra o erro real,
sem o fallback silencioso que existe no main.py.
 
Rodar com: python debug_gemini.py
"""
import os
from dotenv import load_dotenv
 
load_dotenv()
 
api_key = os.environ.get("GEMINI_API_KEY")
print(f"Chave carregada: {'sim, começa com ' + api_key[:6] + '...' if api_key else 'NAO — variavel GEMINI_API_KEY nao encontrada'}")
 
if not api_key:
    print("\nO .env não está sendo lido, ou a variável tem outro nome.")
    print("Confere se o arquivo .env tem exatamente: GEMINI_API_KEY=sua_chave")
    exit(1)
 
import requests
 
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
body = {
    "system_instruction": {"parts": [{"text": "Responda em uma frase curta."}]},
    "contents": [{"role": "user", "parts": [{"text": "o que e financiamento?"}]}],
}
 
print("\nChamando a API do Gemini...")
try:
    resposta = requests.post(url, json=body, timeout=10)
    print(f"Status HTTP: {resposta.status_code}")
    print(f"Resposta bruta: {resposta.text[:1000]}")
    resposta.raise_for_status()
    dados = resposta.json()
    texto = dados["candidates"][0]["content"]["parts"][0]["text"]
    print(f"\nSUCESSO. Resposta do modelo: {texto}")
except Exception as e:
    print(f"\nERRO: {type(e).__name__}: {e}")