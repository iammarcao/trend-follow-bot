import os
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import io
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask
import threading

# Configurações
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Trend Follow está rodando!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

class SimpleTrendBot:
    def __init__(self):
        self.cache = {}
    
    def calculate_hilo(self, high, low, close, period):
        """Calcula o indicador HiLo de forma simplificada"""
        try:
            highest_high = high.rolling(window=period).max()
            lowest_low = low.rolling(window=period).min()
            hilo = (close - lowest_low) / (highest_high - lowest_low) * 100
            return hilo
        except:
            return None
    
    async def asset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not context.args:
                await update.message.reply_text("Por favor, informe o ativo. Exemplo: /ativo BTC")
                return
            
            symbol = context.args[0].upper()
            await update.message.reply_text(f"Analisando {symbol}, aguarde...")
            
            # Obter dados
            if any(crypto in symbol for crypto in ['BTC', 'ETH', 'XRP', 'USDT']):
                ticker_symbol = f"{symbol}-USD" if not symbol.endswith('USD') else symbol
            else:
                ticker_symbol = symbol + ".SA" if not (symbol.endswith('.SA') or '.' in symbol) else symbol
            
            ticker = yf.Ticker(ticker_symbol)
            data = ticker.history(period="6mo")
            
            if data.empty:
                await update.message.reply_text("Não foi possível obter dados para este ativo.")
                return
            
            # Calcular HiLo com período fixo para teste
            period = 20
            hilo = self.calculate_hilo(data['High'], data['Low'], data['Close'], period)
            
            if hilo is None:
                await update.message.reply_text("Erro no cálculo do indicador.")
                return
            
            # Gerar gráfico simplificado
            plt.figure(figsize=(10, 6))
            plt.plot(data.index, data['Close'], label='Preço', color='blue', linewidth=1)
            plt.title(f'{ticker_symbol} - Período HiLo: {period}')
            plt.legend()
            plt.grid(True)
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()
            
            # Enviar resultado
            current_hilo = hilo.iloc[-1] if not hilo.empty else 50
            trend = "ALTA" if current_hilo > 50 else "BAIXA"
            
            await update.message.reply_photo(
                photo=buf, 
                caption=f"{ticker_symbol}\nTendência: {trend}\nHiLo: {current_hilo:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Erro: {e}")
            await update.message.reply_text("Ocorreu um erro. Tente novamente.")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Olá! Eu sou o Trend Follow Bot.\n"
            "Use /ativo [nome do ativo] para analisar um ativo.\n"
            "Exemplos:\n"
            "/ativo BTC - Para Bitcoin\n"
            "/ativo PETR4 - Para Petrobras\n"
            "/ativo AAPL - Para Apple"
        )

# Inicialização
def main():
    # Iniciar Flask em thread separada
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Obter token
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("Token não configurado!")
        return
    
    # Criar aplicação
    application = Application.builder().token(token).build()
    bot = SimpleTrendBot()
    
    # Comandos
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("ativo", bot.asset_command))
    
    # Iniciar
    application.run_polling()

if __name__ == "__main__":
    main()
