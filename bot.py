import os
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import io
import logging
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask
import threading

# Configurações iniciais
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Flask para manter o bot ativo
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Trend Follow está rodando!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

class TrendFollowBot:
    def __init__(self):
        self.cache = {}
        
    def calculate_hilo(self, high, low, close, period):
        """Calcula o indicador HiLo"""
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        hilo = (close - lowest_low) / (highest_high - lowest_low) * 100
        return hilo
        
    def calculate_payoff(self, data, period):
        """Calcula o payoff para um período"""
        hilo = self.calculate_hilo(data['High'], data['Low'], data['Close'], period)
        signals = hilo > 50
        returns = data['Close'].pct_change().shift(-1)
        strategy_returns = returns * signals.shift(1)
        strategy_returns = strategy_returns.dropna()
        
        if len(strategy_returns) == 0:
            return 0
            
        winning_trades = strategy_returns[strategy_returns > 0]
        losing_trades = strategy_returns[strategy_returns < 0]
        
        if len(losing_trades) == 0:
            return float('inf')
            
        avg_win = winning_trades.mean() if len(winning_trades) > 0 else 0
        avg_loss = abs(losing_trades.mean()) if len(losing_trades) > 0 else 0
        
        return avg_win / avg_loss if avg_loss != 0 else 0
        
    def find_optimal_period(self, data, asset_type):
        """Encontra o período com melhor payoff"""
        best_period = 20
        best_payoff = 0
        test_periods = range(5, 61, 5)  # Testa períodos de 5 em 5
        
        for period in test_periods:
            payoff = self.calculate_payoff(data, period)
            if asset_type == "crypto":
                if payoff >= 3 and payoff > best_payoff:
                    best_payoff = payoff
                    best_period = period
            else:
                if payoff > best_payoff:
                    best_payoff = payoff
                    best_period = period
                    
        return best_period, best_payoff
        
    def get_last_trend_change(self, data, period):
        """Identifica a última mudança de tendência"""
        hilo = self.calculate_hilo(data['High'], data['Low'], data['Close'], period)
        trend = hilo > 50
        trend_changes = trend.ne(trend.shift(1))
        last_change = trend_changes[trend_changes].index[-1] if any(trend_changes) else data.index[-1]
        return last_change
        
    def generate_chart(self, data, period, asset_name):
        """Gera o gráfico com o indicador HiLo"""
        hilo = self.calculate_hilo(data['High'], data['Low'], data['Close'], period)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
        ax1.plot(data.index, data['Close'], label='Preço', color='black', linewidth=1)
        ax1.set_title(f'{asset_name} - Período HiLo: {period}')
        ax1.legend(loc='upper left')
        ax1.grid(True)
        
        ax2.plot(data.index, hilo, label='HiLo', color='blue', linewidth=1)
        ax2.axhline(y=50, color='red', linestyle='--', linewidth=1)
        ax2.set_ylim(0, 100)
        ax2.legend(loc='upper left')
        ax2.grid(True)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf
        
    async def get_asset_data(self, symbol, asset_type):
        """Obtém dados do ativo"""
        try:
            if asset_type == "crypto":
                ticker = yf.Ticker(f"{symbol}-USD")
                data = ticker.history(period="max")
            else:
                if symbol.endswith('.SA'):
                    ticker = yf.Ticker(symbol)
                else:
                    ticker = yf.Ticker(symbol)
                data = ticker.history(period="20y")
            return data
        except Exception as e:
            logger.error(f"Erro ao obter dados: {e}")
            return None
            
    async def asset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando para analisar um ativo"""
        if not context.args:
            await update.message.reply_text("Por favor, informe o ativo. Exemplo: /ativo BTC")
            return
            
        user_input = context.args[0].upper()
        
        # Determinar tipo de ativo
        if any(crypto in user_input for crypto in ['BTC', 'ETH', 'XRP', 'USDT']):
            asset_type = "crypto"
            symbol = user_input + "USD" if not user_input.endswith('USD') else user_input
        else:
            asset_type = "stock"
            symbol = user_input + ".SA" if not (user_input.endswith('.SA') or '.' in user_input) else user_input
        
        await update.message.reply_text(f"Analisando {symbol}, aguarde...")
        
        # Obter dados
        data = await self.get_asset_data(symbol, asset_type)
        if data is None or data.empty:
            await update.message.reply_text("Não foi possível obter dados para este ativo.")
            return
            
        # Encontrar período ótimo
        optimal_period, payoff = self.find_optimal_period(data, asset_type)
        
        # Verificar payoff para criptos
        if asset_type == "crypto" and payoff < 3:
            await update.message.reply_text(f"Payoff {payoff:.2f} inferior a 3. Não é adequado para a estratégia.")
            return
            
        # Identificar última mudança de tendência
        last_change = self.get_last_trend_change(data, optimal_period)
        
        # Gerar gráfico
        chart_buffer = self.generate_chart(data, optimal_period, symbol)
        
        # Preparar mensagem
        message = (
            f"Ativo: {symbol}\n"
            f"Período HiLo ideal: {optimal_period}\n"
            f"Payoff: {payoff:.2f}\n"
            f"Última mudança de tendência: {last_change.strftime('%d/%m/%Y')}\n"
            f"Tendência atual: {'ALTA' if self.calculate_hilo(data['High'], data['Low'], data['Close'], optimal_period).iloc[-1] > 50 else 'BAIXA'}"
        )
        
        await update.message.reply_photo(photo=chart_buffer, caption=message)
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando de início"""
        await update.message.reply_text(
            "Olá! Eu sou o Trend Follow Bot.\n"
            "Use /ativo [nome do ativo] para analisar um ativo.\n"
            "Exemplos:\n"
            "/ativo BTC - Para Bitcoin\n"
            "/ativo PETR4.SA - Para Petrobras\n"
            "/ativo AAPL - Para Apple"
        )

# Função principal
async def main():
    # Iniciar Flask em thread separada
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Obter token da variável de ambiente
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("Token não encontrado. Configure a variável de ambiente TELEGRAM_TOKEN.")
        return
        
    # Criar aplicação do Telegram
    application = Application.builder().token(token).build()
    bot = TrendFollowBot()
    
    # Adicionar comandos
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("ativo", bot.asset_command))
    
    # Iniciar o bot
    await application.initialize()
    await application.start()
    logger.info("Bot iniciado com sucesso!")
    await application.updater.start_polling()
    
    # Manter executando
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
