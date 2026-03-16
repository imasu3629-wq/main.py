import discord
from discord import app_commands
import requests
import os
from flask import Flask
from threading import Thread

# --- 24時間稼働設定 ---
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- 環境変数 ---
TOKEN = os.environ['DISCORD_TOKEN']
current_api_key = os.environ['HYPIXEL_KEY']
AUTHORIZED_USERS = [1278574483195559977]

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    try:
        synced = await tree.sync()
        print(f"✅ {len(synced)}個のコマンドを同期しました")
    except Exception as e:
        print(f"❌ 同期エラー: {e}")
    print(f'✅ Logged in as {bot.user.name}')

# --- [NEW] スキン表示コマンド ---
@tree.command(name="skin", description="指定したMCIDのスキン画像を表示・配布します")
async def skin(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        u_res = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{mcid}")
        if u_res.status_code != 200:
            await interaction.followup.send("❌ プレイヤーが見つかりません。")
            return
        uuid = u_res.json()['id']
        
        # 3Dレンダリングと、配布用（展開図）のURL
        render_url = f"https://visage.surgeplay.com/full/384/{uuid}.png"
        raw_skin_url = f"https://visage.surgeplay.com/skin/{uuid}.png"

        embed = discord.Embed(title=f"👕 {mcid} のスキン", color=0x9b59b6)
        embed.set_image(url=render_url)
        embed.add_field(name="📥 配布用データ（展開図）", value=f"[この画像を保存してマイクラに適用]({raw_skin_url})", inline=False)
        embed.set_footer(text="画像を保存して公式サイトのスキン設定からアップロードしてください")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラー: {e}")

# --- [UPDATE] 履歴表示コマンド (最強API版) ---
@tree.command(name="history", description="MCIDの変更履歴をすべて表示します")
async def history(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        # 1. UUIDを取得
        u_res = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{mcid}")
        if u_res.status_code != 200:
            await interaction.followup.send("❌ プレイヤーが見つかりません。")
            return
        uuid = u_res.json()['id']

        # 2. 履歴取得 (LabyMod API: 非常に履歴に強く、日付データも正確です)
        h_res = requests.get(f"https://laby.net/api/v3/user/{uuid}/profile")
        data = h_res.json()

        # 履歴データの抽出
        history_data = data.get("username_history", [])
        
        if history_data:
            embed = discord.Embed(title=f"📜 {mcid} のID変更履歴", color=0x3498db)
            lines = []
            # 新しい順に並び替え
            for entry in reversed(history_data):
                name = entry['username']
                changed_at = entry.get('changed_at')
                
                if changed_at:
                    # LabyMod APIの日付形式を読みやすく(YYYY/MM/DD)
                    date = changed_at[:10].replace("-", "/")
                    lines.append(f"📅 `{date}` ➔ **{name}**")
                else:
                    lines.append(f"🌱 `最初のID` ➔ **{name}**")
            
            embed.description = "\n".join(lines)
            await interaction.followup.send(embed=embed)
        else:
            # 履歴がない（今の名前だけ）場合
            await interaction.followup.send(f"ℹ️ {mcid} の名前変更履歴は見つかりませんでした（変更していないか、データがありません）。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生しました。")

# --- 戦績表示コマンド ---
@tree.command(name="stats", description="HypixelのBedwars戦績を表示します")
async def stats(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        u_res = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{mcid}")
        uuid = u_res.json()['id']
        h_url = f"https://api.hypixel.net/v2/player?key={current_api_key}&uuid={uuid}"
        data = requests.get(h_url).json()
        if data.get("player"):
            p = data["player"]
            bw = p.get("stats", {}).get("Bedwars", {})
            star = p.get("achievements", {}).get("bedwars_level", 0)
            fk = bw.get("final_kills_bedwars", 0)
            fd = bw.get("final_deaths_bedwars", 1)
            fkdr = round(fk / fd, 2)
            embed = discord.Embed(title=f"{mcid} の戦績", color=0x00ff00)
            embed.add_field(name="⭐ Star", value=str(star), inline=True)
            embed.add_field(name="⚔️ FKDR", value=f"**{fkdr}**", inline=True)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ データがありません。")
    except:
        await interaction.followup.send("⚠️ エラー")

# --- 管理用コマンド ---
@tree.command(name="setkey", description="APIキーを更新（管理者専用）")
async def setkey(interaction: discord.Interaction, new_key: str):
    global current_api_key
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ 権限なし", ephemeral=True)
        return
    current_api_key = new_key
    await interaction.response.send_message("✅ 更新完了", ephemeral=True)

keep_alive()
bot.run(TOKEN)
