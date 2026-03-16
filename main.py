import discord
from discord import app_commands
import requests
import os
from flask import Flask
from threading import Thread

# --- Koyeb/Render 24時間稼働用設定 ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ----------------------------------

# 環境変数の読み込み
TOKEN = os.environ['DISCORD_TOKEN']
current_api_key = os.environ['HYPIXEL_KEY']
AUTHORIZED_USERS = [1278574483195559977]

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

@bot.event
async def on_ready():
    await tree.sync()
    print(f'✅ Logged in as {bot.user.name}')

@tree.command(name="stats", description="HypixelのBedwars戦績を表示します")
async def stats(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        u_res = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{mcid}")
        if u_res.status_code != 200:
            await interaction.followup.send("❌ プレイヤーが見つかりませんでした。")
            return
        uuid = u_res.json()['id']
        h_url = f"https://api.hypixel.net/v2/player?key={current_api_key}&uuid={uuid}"
        data = requests.get(h_url).json()

        if data.get("success") and data.get("player"):
            p = data["player"]
            bw = p.get("stats", {}).get("Bedwars", {})
            star = p.get("achievements", {}).get("bedwars_level", 0)
            fk = bw.get("final_kills_bedwars", 0)
            fd = bw.get("final_deaths_bedwars", 1)
            fkdr = round(fk / fd, 2)

            if fkdr < 3: impression = "伸び代あり"
            elif fkdr < 10: impression = "割とつよい"
            else: impression = "最強クラス"

            embed = discord.Embed(title=f"{mcid} の戦績", color=0x00ff00)
            embed.add_field(name="⭐ Star", value=str(star), inline=True)
            embed.add_field(name="⚔️ FKDR", value=f"**{fkdr}**", inline=True)
            embed.add_field(name="💬 感想", value=impression, inline=True)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ データの取得に失敗しました。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラー: {e}")

@tree.command(name="history", description="MCIDの変更履歴を確認します")
async def history(interaction: discord.Interaction, mcid: str):
    await interaction.response.defer()
    try:
        u_res = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{mcid}")
        if u_res.status_code != 200:
            await interaction.followup.send("❌ プレイヤーが見つかりませんでした。")
            return
        uuid = u_res.json()['id']
        h_res = requests.get(f"https://api.ashcon.app/mojang/v2/user/{uuid}")
        data = h_res.json()

        if "username_history" in data:
            history_list = data["username_history"]
            embed = discord.Embed(title=f"{mcid} の名前変更履歴", color=0x3498db)
            description = ""
            for entry in reversed(history_list):
                name = entry['username']
                if 'changed_at' in entry:
                    date = entry['changed_at'][:10].replace("-", "/")
                    description += f"• **{name}** ({date})\n"
                else:
                    description += f"• **{name}** (最初のID)\n"
            embed.description = description
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ 履歴が見つかりませんでした。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生しました: {e}")

@tree.command(name="setkey", description="APIキーを更新（管理者専用）")
async def setkey(interaction: discord.Interaction, new_key: str):
    global current_api_key
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
        return
    current_api_key = new_key
    await interaction.response.send_message("✅ 更新完了", ephemeral=True)

# サーバー起動とBot起動
keep_alive()
bot.run(TOKEN)
